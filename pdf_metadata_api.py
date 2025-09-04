# -*- coding: utf-8 -*-
"""
PDF元数据提取系统 - Flask API后端
轻量化设计，集成所有功能模块
"""

import os
import json
import uuid
import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import asdict
from pathlib import Path

from flask import Flask, request, jsonify, Response, render_template, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pandas as pd

# 导入现有的元数据提取模块
from Metadata import extract_first_page_llm, PaperMeta, extract_acknowledgment_from_last_pages
from concurrent_processor import get_global_processor, ConcurrentProcessor, RateLimitConfig
from config import Config
from log_manager import log_manager, log_operation, log_file_upload, log_file_processing, log_batch_processing, log_api_call

# =========================
# 配置初始化
# =========================

# =========================
# 数据处理器类
# =========================
class MetadataProcessor:
    """元数据处理器 - 核心业务逻辑"""
    
    def __init__(self):
        self.processing_tasks = {}
    
    def _extract_real_filename(self, file_path: str) -> str:
        """从文件路径中提取真实的文件名（去掉UUID前缀），保留扩展名"""
        filename = os.path.basename(file_path)
        if '_' in filename:
            # 检查第一部分是否是UUID格式（8-4-4-4-12个字符）
            parts = filename.split('_', 1)
            if len(parts) == 2:
                potential_uuid = parts[0]
                # 简单的UUID格式检查：长度为36且包含4个连字符
                if len(potential_uuid) == 36 and potential_uuid.count('-') == 4:
                    # 格式：UUID_真实文件名.pdf
                    return parts[1]

        # 如果没有UUID前缀，直接返回文件名
        return filename

    def _clean_export_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清理导出数据，移除内部处理字段"""
        # 需要移除的内部字段
        internal_fields = {
            '_original_index',
            '_upload_order',
            'attempt',
            'processing_time',
            'filename',  # 移除通用filename字段
            'file',      # 移除文件路径字段
            'status'     # 移除状态字段（仅保留有错误的记录中的error字段）
        }

        cleaned_data = []
        for item in data:
            # 跳过有错误的记录
            if item.get('error') or item.get('status') == 'failed':
                continue

            # 创建清理后的记录
            cleaned_item = {}
            for key, value in item.items():
                if key not in internal_fields:
                    cleaned_item[key] = value

            cleaned_data.append(cleaned_item)

        return cleaned_data

    async def process_file(self, file_path: str, mode: str) -> Dict[str, Any]:
        """处理单个PDF文件"""
        try:
            # 调用现有的元数据提取函数
            meta = await extract_first_page_llm(file_path)
            
            # 根据模式转换数据格式
            if mode == 'sn':
                return self._format_sn_data(meta, file_path)
            elif mode == 'ieee':
                return self._format_ieee_data(meta, file_path)
            elif mode == 'funding':
                return self._format_funding_data(meta, file_path)
            elif mode == 'ap':
                return self._format_ap_data(meta, file_path)
            else:
                raise ValueError(f"不支持的模式: {mode}")
                
        except Exception as e:
            filename = self._extract_real_filename(file_path)

            # 为IEEE模式的订单号去除.pdf扩展名
            order_number = filename
            if mode == 'ieee' and order_number.lower().endswith('.pdf'):
                order_number = order_number[:-4]

            return {
                'error': str(e),
                'file': file_path,
                'filename': filename,
                # 根据模式添加对应的文件名字段
                '文件名': filename,  # 资助信息和AP模式
                'Number': filename,  # SN模式
                '订单号': order_number,  # IEEE模式（去除.pdf扩展名）
                'status': 'failed'
            }
    
    def _format_sn_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化SN模式数据"""
        filename = self._extract_real_filename(file_path)
        result = {
            'Number': filename,
            'Title': meta.title,
            'SubTitle': '',  # 需要从标题中分离副标题
            'Corresponding Author': '',
            "Corresponding author's email": '',
            'filename': filename  # 添加通用filename字段
        }
        
        # 处理作者信息
        for i, author in enumerate(meta.authors[:5], 1):
            result[f'Author {i}'] = author.name
            result[f'Affiliation {i}'] = next(
                (aff.name for aff in meta.affiliations if aff.id in author.affiliation_ids),
                ''
            )
            
            # 识别通讯作者
            if author.is_corresponding_author:
                result['Corresponding Author'] = author.name
                result["Corresponding author's email"] = author.email or ''
        
        # 如果没有标记通讯作者，使用第一作者
        if not result['Corresponding Author'] and meta.authors:
            result['Corresponding Author'] = meta.authors[0].name
            result["Corresponding author's email"] = meta.authors[0].email or ''
        
        return result
    
    def _format_ieee_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化IEEE模式数据"""
        # 提取所有作者姓名，去除上标
        all_authors = ', '.join([author.name for author in meta.authors])

        # 获取第一作者邮箱，如果没有则取通讯作者邮箱
        first_author_email = ''
        if meta.authors:
            first_author_email = meta.authors[0].email or ''
            if not first_author_email:
                # 查找通讯作者邮箱
                for author in meta.authors:
                    if author.is_corresponding_author and author.email:
                        first_author_email = author.email
                        break

        filename = self._extract_real_filename(file_path)
        # 对于订单号字段，去除.pdf扩展名
        order_number = filename
        if order_number.lower().endswith('.pdf'):
            order_number = order_number[:-4]

        # 按照指定顺序返回字段
        return {
            '订单号': order_number,
            '英文题目': meta.title,
            '英文副标': '',  # 需要从标题中分离
            '作者姓名': all_authors,
            '第一作者邮箱': first_author_email,
            'filename': filename  # 添加通用filename字段（用于内部处理）
        }
    
    def _format_funding_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化资助信息模式数据"""
        first_author = meta.authors[0] if meta.authors else None
        corresponding_author = next(
            (author for author in meta.authors if author.is_corresponding_author),
            first_author
        )

        # 提取致谢信息
        acknowledgment = ""
        try:
            acknowledgment = extract_acknowledgment_from_last_pages(file_path)
        except Exception as e:
            print(f"致谢信息提取失败: {e}")

        filename = self._extract_real_filename(file_path)
        return {
            '文件名': filename,
            '论文英文题目': meta.title,
            '第一作者姓名': first_author.name if first_author else '',
            '第一作者单位': self._get_author_affiliation(first_author, meta.affiliations) if first_author else '',
            '通讯作者姓名': corresponding_author.name if corresponding_author else '',
            '通讯作者单位': self._get_author_affiliation(corresponding_author, meta.affiliations) if corresponding_author else '',
            '通讯作者邮箱': corresponding_author.email if corresponding_author else '',
            '关键词': ', '.join(meta.keywords),
            '摘要': meta.abstract or '',
            '致谢': acknowledgment,
            'filename': filename  # 添加通用filename字段
        }
    
    def _format_ap_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化AP模式数据"""
        first_author = meta.authors[0] if meta.authors else None
        corresponding_author = next(
            (author for author in meta.authors if author.is_corresponding_author),
            None
        )
        
        filename = self._extract_real_filename(file_path)
        result = {
            '题目': meta.title,
            '关键词': ', '.join(meta.keywords),
            '摘要': meta.abstract or '',
            '文件名': filename,
            'filename': filename  # 添加通用filename字段
        }
        
        # 第一作者姓名分解
        if first_author:
            name_parts = first_author.name.split()
            result['第一作者姓'] = name_parts[-1] if name_parts else ''
            result['第一作者名'] = ' '.join(name_parts[:-1]) if len(name_parts) > 1 else ''
        
        # 通讯作者姓名分解（仅当通讯作者非第一作者时）
        if corresponding_author and corresponding_author != first_author:
            name_parts = corresponding_author.name.split()
            result['通讯作者姓'] = name_parts[-1] if name_parts else ''
            result['通讯作者名'] = ' '.join(name_parts[:-1]) if len(name_parts) > 1 else ''
        
        return result
    
    def _get_author_affiliation(self, author, affiliations) -> str:
        """获取作者单位"""
        if not author or not author.affiliation_ids:
            return ''
        
        for aff_id in author.affiliation_ids:
            aff = next((aff for aff in affiliations if aff.id == aff_id), None)
            if aff:
                return aff.name
        return ''

# =========================
# Flask应用初始化
# =========================
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# 初始化组件
Config.init_app(app)
processor = MetadataProcessor()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf_extraction.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def allowed_file(filename):
    """检查文件扩展名"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# =========================
# API路由定义
# =========================

@app.route('/')
def index():
    """主页 - 返回前端界面"""
    return render_template('PDF.html')

@app.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """文件上传接口"""
    start_time = time.time()
    try:
        files = request.files.getlist('files')
        if not files or all(not file for file in files):
            log_operation("文件上传", {"error": "没有上传文件"}, time.time() - start_time, "error")
            return jsonify({'error': '没有上传文件'}), 400

        uploaded_files = []
        errors = []

        for file in files:
            if not file:
                continue

            if not file.filename:
                errors.append({'filename': '未知', 'error': '文件名为空'})
                continue

            if not allowed_file(file.filename):
                errors.append({'filename': file.filename, 'error': '不支持的文件格式，仅支持PDF文件'})
                continue

            try:
                filename = secure_filename(file.filename)
                file_id = str(uuid.uuid4())
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")
                file.save(file_path)

                # 验证文件是否成功保存
                if not os.path.exists(file_path):
                    errors.append({'filename': filename, 'error': '文件保存失败'})
                    continue

                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    errors.append({'filename': filename, 'error': '文件为空'})
                    os.remove(file_path)  # 删除空文件
                    continue

                # 记录文件上传日志
                log_file_upload(filename, file_size)

                uploaded_files.append({
                    'file_id': file_id,
                    'filename': filename,
                    'path': file_path,
                    'size': file_size
                })

            except Exception as e:
                errors.append({'filename': file.filename, 'error': f'文件处理失败: {str(e)}'})

        processing_time = time.time() - start_time
        
        if not uploaded_files and errors:
            log_operation("文件上传", {"error": "所有文件上传失败", "errors": errors}, processing_time, "error")
            return jsonify({
                'success': False,
                'error': '所有文件上传失败',
                'errors': errors
            }), 400

        # 记录批量上传成功日志
        log_batch_processing(len(uploaded_files), "文件上传", processing_time, len(uploaded_files), len(errors))
        
        return jsonify({
            'success': True,
            'files': uploaded_files,
            'count': len(uploaded_files),
            'errors': errors if errors else None
        })

    except Exception as e:
        processing_time = time.time() - start_time
        log_operation("文件上传", {"error": f"服务器内部错误: {str(e)}"}, processing_time, "error")
        logging.error(f"文件上传处理失败: {e}")
        return jsonify({'error': f'服务器内部错误: {str(e)}'}), 500

@app.route('/api/files', methods=['GET'])
def list_files():
    """获取已上传文件列表"""
    try:
        files = []
        upload_dir = Path(app.config['UPLOAD_FOLDER'])

        for file_path in upload_dir.glob('*.pdf'):
            stat = file_path.stat()
            # 从文件名中提取真实文件名（去掉UUID前缀）
            full_filename = file_path.name
            if '_' in full_filename:
                # 格式：UUID_真实文件名.pdf
                real_filename = '_'.join(full_filename.split('_')[1:])
            else:
                real_filename = full_filename
            
            files.append({
                'filename': real_filename,  # 返回真实文件名
                'full_filename': full_filename,  # 保留完整文件名用于删除等操作
                'size': stat.st_size,
                'upload_time': datetime.fromtimestamp(stat.st_ctime).isoformat()
            })

        return jsonify({
            'files': files,
            'count': len(files)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    """删除指定文件"""
    try:
        upload_dir = Path(app.config['UPLOAD_FOLDER'])
        file_pattern = f"{file_id}_*"

        deleted = False
        for file_path in upload_dir.glob(file_pattern):
            file_path.unlink()
            deleted = True

        if deleted:
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            return jsonify({'error': '文件不存在'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/<mode>', methods=['POST'])
def extract_metadata(mode):
    """单模式元数据提取接口（支持并发处理）"""
    try:
        if mode not in ['sn', 'ieee', 'funding', 'ap']:
            return jsonify({'error': f'不支持的模式: {mode}'}), 400

        data = request.get_json()
        file_paths = data.get('file_paths', [])
        use_concurrent = data.get('use_concurrent', len(file_paths) > 5)  # 超过5个文件自动启用并发

        if not file_paths:
            return jsonify({'error': '没有指定文件路径'}), 400

        # 检查文件是否存在
        valid_files = []
        invalid_files = []
        for file_path in file_paths:
            if os.path.exists(file_path):
                valid_files.append(file_path)
            else:
                invalid_files.append({
                    'file': file_path,
                    'error': '文件不存在',
                    'status': 'failed'
                })

        if not valid_files:
            return jsonify({
                'success': False,
                'error': '没有有效的文件路径',
                'results': invalid_files
            }), 400

        # 选择处理方式
        if use_concurrent and len(valid_files) > 1:
            # 并发处理
            concurrent_processor = get_global_processor()

            async def process_wrapper(file_path: str, mode: str):
                return await processor.process_file(file_path, mode)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(
                    concurrent_processor.process_batch(valid_files, process_wrapper, mode)
                )
                # 并发处理器内部已经按原始索引排序，无需额外排序
            finally:
                loop.close()
        else:
            # 串行处理
            results = []
            for file_path in valid_files:
                try:
                    # 在Flask线程中创建新的事件循环
                    import concurrent.futures

                    def run_async_in_thread():
                        """在新线程中运行异步函数"""
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(processor.process_file(file_path, mode))
                        finally:
                            loop.close()
                    
                    # 使用线程池执行异步函数
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(run_async_in_thread)
                        result = future.result(timeout=300)  # 5分钟超时
                    
                    results.append(result)
                except Exception as e:
                    logger.error(f"串行处理文件失败: {file_path} - {str(e)}")
                    results.append({
                        'file': file_path,
                        'filename': processor._extract_real_filename(file_path),
                        'error': str(e),
                        'status': 'failed'
                    })

        # 合并无效文件结果，并按照原始文件路径顺序排序
        all_results = results + invalid_files
        
        # 创建一个映射来保持原始顺序
        file_order_map = {file_path: i for i, file_path in enumerate(file_paths)}
        
        # 按照原始文件路径顺序排序所有结果
        def get_original_order(result):
            file_path = result.get('file', '')
            return file_order_map.get(file_path, 999999)  # 无效文件排在最后
        
        all_results.sort(key=get_original_order)
        
        successful_count = len([r for r in results if r.get('status') != 'failed' and 'error' not in r])

        return jsonify({
            'success': True,
            'mode': mode,
            'results': all_results,
            'count': len(all_results),
            'successful': successful_count,
            'failed': len(all_results) - successful_count,
            'concurrent_used': use_concurrent and len(valid_files) > 1
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/batch', methods=['POST'])
def extract_batch():
    """专门的批量处理端点（优化大文件处理）"""
    try:
        data = request.get_json()
        file_paths = data.get('file_paths', [])
        mode = data.get('mode', 'sn')

        if mode not in ['sn', 'ieee', 'funding', 'ap']:
            return jsonify({'error': f'不支持的模式: {mode}'}), 400

        if not file_paths:
            return jsonify({'error': '没有指定文件路径'}), 400

        if len(file_paths) > 200:
            return jsonify({'error': '单次最多处理200个文件'}), 400

        # 检查文件是否存在
        valid_files = [f for f in file_paths if os.path.exists(f)]
        invalid_count = len(file_paths) - len(valid_files)

        if not valid_files:
            return jsonify({'error': '没有有效的文件路径'}), 400

        # 使用并发处理器
        concurrent_processor = get_global_processor()

        async def process_wrapper(file_path: str, mode: str):
            return await processor.process_file(file_path, mode)

        # 进度跟踪
        progress_info = {'current': 0, 'total': len(valid_files), 'message': '准备中...'}

        async def progress_callback(progress: float, message: str):
            progress_info['current'] = int(progress * len(valid_files) / 100)
            progress_info['message'] = message

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            start_time = time.time()
            results = loop.run_until_complete(
                concurrent_processor.process_batch(valid_files, process_wrapper, mode, progress_callback)
            )
            processing_time = time.time() - start_time

            # 并发处理器内部已经按原始索引排序，无需额外排序
            
        finally:
            loop.close()

        # 统计结果
        successful_count = len([r for r in results if r.get('status') != 'failed' and 'error' not in r])
        failed_count = len(results) - successful_count

        # 获取处理统计
        stats = concurrent_processor.get_processing_stats()

        return jsonify({
            'success': True,
            'mode': mode,
            'results': results,
            'statistics': {
                'total_files': len(file_paths),
                'valid_files': len(valid_files),
                'invalid_files': invalid_count,
                'successful': successful_count,
                'failed': failed_count,
                'success_rate': (successful_count / len(valid_files)) * 100 if valid_files else 0,
                'processing_time': round(processing_time, 2),
                'avg_time_per_file': round(processing_time / len(valid_files), 2) if valid_files else 0
            },
            'rate_limit_stats': stats
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/processing/stats', methods=['GET'])
def get_processing_stats():
    """获取当前处理统计信息"""
    try:
        concurrent_processor = get_global_processor()
        stats = concurrent_processor.get_processing_stats()

        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': time.time()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/batch', methods=['POST'])
def batch_extract():
    """批量处理多种模式"""
    try:
        data = request.get_json()
        file_paths = data.get('file_paths', [])
        modes = data.get('modes', ['sn'])

        if not file_paths:
            return jsonify({'error': '没有指定文件路径'}), 400

        results = {}
        for mode in modes:
            if mode not in ['sn', 'ieee', 'funding', 'ap']:
                continue

            mode_results = []
            for file_path in file_paths:
                if not os.path.exists(file_path):
                    mode_results.append({
                        'file': file_path,
                        'error': '文件不存在',
                        'status': 'failed'
                    })
                    continue

                # 异步处理文件
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(processor.process_file(file_path, mode))
                    mode_results.append(result)
                finally:
                    loop.close()

            results[mode] = mode_results

        return jsonify({
            'success': True,
            'results': results,
            'processed_modes': list(results.keys())
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process', methods=['POST'])
def process_files():
    """处理PDF文件的主接口（流式响应）"""
    start_time = time.time()
    
    def generate():
        try:
            # 获取上传的文件和模式
            files = request.files.getlist('files')
            mode = request.form.get('mode', 'sn')

            if not files:
                log_operation("文件处理", {"error": "没有上传文件"}, time.time() - start_time, "error")
                yield json.dumps({'type': 'error', 'message': '没有上传文件'}) + '\n'
                return

            # 记录开始处理日志
            log_operation("文件处理", {"file_count": len(files), "mode": mode})

            yield json.dumps({
                'type': 'status',
                'message': f'开始处理 {len(files)} 个文件，模式: {mode}'
            }) + '\n'

            # 保存上传的文件
            saved_files = []
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_id = str(uuid.uuid4())
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")
                    file.save(file_path)
                    saved_files.append(file_path)

            yield json.dumps({
                'type': 'info',
                'message': f'成功保存 {len(saved_files)} 个文件'
            }) + '\n'

            # 处理每个文件
            success_count = 0
            failed_count = 0
            
            for i, file_path in enumerate(saved_files, 1):
                file_start_time = time.time()
                # 提取真实文件名（去掉UUID前缀）
                real_filename = processor._extract_real_filename(file_path)
                
                yield json.dumps({
                    'type': 'status',
                    'message': f'正在处理第 {i}/{len(saved_files)} 个文件: {real_filename}'
                }) + '\n'

                # 异步处理文件
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(processor.process_file(file_path, mode))
                    file_processing_time = time.time() - file_start_time

                    if 'error' not in result:
                        success_count += 1
                        # 记录成功处理日志
                        log_file_processing(real_filename, mode, file_processing_time, "success")
                        
                        yield json.dumps({
                            'type': 'data_row',
                            'data': result
                        }) + '\n'

                        yield json.dumps({
                            'type': 'success',
                            'message': f'✅ {real_filename} 处理完成'
                        }) + '\n'
                    else:
                        failed_count += 1
                        # 记录失败处理日志
                        log_file_processing(real_filename, mode, file_processing_time, "error", result["error"])
                        
                        yield json.dumps({
                            'type': 'error',
                            'message': f'❌ {real_filename} 处理失败: {result["error"]}'
                        }) + '\n'

                finally:
                    loop.close()

            # 记录批量处理完成日志
            total_time = time.time() - start_time
            log_batch_processing(len(saved_files), mode, total_time, success_count, failed_count)
            
            yield json.dumps({
                'type': 'status',
                'message': '所有文件处理完成'
            }) + '\n'

        except Exception as e:
            processing_time = time.time() - start_time
            log_operation("文件处理", {"error": str(e)}, processing_time, "error")
            yield json.dumps({
                'type': 'error',
                'message': f'处理过程中发生错误: {str(e)}'
            }) + '\n'

    return Response(generate(), mimetype='text/plain')

@app.route('/api/export/excel', methods=['POST'])
def export_excel():
    """导出Excel格式结果"""
    try:
        data = request.get_json()
        results = data.get('results', [])
        mode = data.get('mode', 'sn')

        if not results:
            return jsonify({'error': '没有数据可导出'}), 400

        # 清理数据，移除内部处理字段
        cleaned_results = processor._clean_export_data(results)

        if not cleaned_results:
            return jsonify({'error': '没有有效数据可导出'}), 400

        # 根据模式定义字段顺序
        column_orders = {
            'ieee': ['订单号', '英文题目', '英文副标', '作者姓名', '第一作者邮箱'],
            'sn': ['Number', 'Title', 'SubTitle', 'Author 1', 'Affiliation 1', 'Author 2', 'Affiliation 2',
                   'Author 3', 'Affiliation 3', 'Author 4', 'Affiliation 4', 'Author 5', 'Affiliation 5',
                   'Corresponding Author', "Corresponding author's email"],
            'funding': ['文件名', '论文英文题目', '第一作者姓名', '第一作者单位', '通讯作者姓名', '通讯作者单位',
                       '通讯作者邮箱', '关键词', '摘要', '致谢'],
            'ap': ['文件名', '题目', '关键词', '摘要', '第一作者姓', '第一作者名', '通讯作者姓', '通讯作者名']
        }

        # 获取当前模式的字段顺序
        if mode in column_orders:
            # 按指定顺序重新组织数据
            ordered_results = []
            for item in cleaned_results:
                ordered_item = {}
                # 先按指定顺序添加字段
                for col in column_orders[mode]:
                    if col in item:
                        ordered_item[col] = item[col]
                # 再添加其他字段（如果有的话）
                for key, value in item.items():
                    if key not in ordered_item:
                        ordered_item[key] = value
                ordered_results.append(ordered_item)
            cleaned_results = ordered_results

        # 创建DataFrame
        df = pd.DataFrame(cleaned_results)

        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{mode}_metadata_{timestamp}.xlsx"
        file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)

        # 保存Excel文件
        df.to_excel(file_path, index=False, engine='openpyxl')

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/json', methods=['POST'])
def export_json():
    """导出JSON格式结果"""
    try:
        data = request.get_json()
        results = data.get('results', [])
        mode = data.get('mode', 'sn')

        if not results:
            return jsonify({'error': '没有数据可导出'}), 400

        # 清理数据，移除内部处理字段
        cleaned_results = processor._clean_export_data(results)

        if not cleaned_results:
            return jsonify({'error': '没有有效数据可导出'}), 400

        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{mode}_metadata_{timestamp}.json"
        file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)

        # 保存JSON文件
        export_data = {
            'mode': mode,
            'export_time': datetime.now().isoformat(),
            'count': len(cleaned_results),
            'results': cleaned_results
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/json'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/excel', methods=['POST'])
def download_excel():
    """直接下载Excel文件接口"""
    try:
        data = request.get_json()
        results = data.get('results', [])
        mode = data.get('mode', 'sn')

        if not results:
            return jsonify({'error': '没有数据可下载'}), 400

        # 清理数据，移除内部处理字段
        cleaned_results = processor._clean_export_data(results)

        if not cleaned_results:
            return jsonify({'error': '没有有效数据可下载'}), 400

        # 根据模式定义字段顺序
        column_orders = {
            'ieee': ['订单号', '英文题目', '英文副标', '作者姓名', '第一作者邮箱'],
            'sn': ['Number', 'Title', 'SubTitle', 'Author 1', 'Affiliation 1', 'Author 2', 'Affiliation 2',
                   'Author 3', 'Affiliation 3', 'Author 4', 'Affiliation 4', 'Author 5', 'Affiliation 5',
                   'Corresponding Author', "Corresponding author's email"],
            'funding': ['文件名', '论文英文题目', '第一作者姓名', '第一作者单位', '通讯作者姓名', '通讯作者单位',
                       '通讯作者邮箱', '关键词', '摘要', '致谢'],
            'ap': ['文件名', '题目', '关键词', '摘要', '第一作者姓', '第一作者名', '通讯作者姓', '通讯作者名']
        }

        # 按指定顺序重新组织数据
        if mode in column_orders:
            ordered_results = []
            for item in cleaned_results:
                ordered_item = {}
                # 先按指定顺序添加字段
                for col in column_orders[mode]:
                    if col in item:
                        ordered_item[col] = item[col]
                # 再添加其他字段（如果有的话）
                for key, value in item.items():
                    if key not in ordered_item:
                        ordered_item[key] = value
                ordered_results.append(ordered_item)
            cleaned_results = ordered_results

        # 创建DataFrame，明确指定列顺序
        if mode in column_orders and cleaned_results:
            # 获取实际存在的列
            all_columns = set()
            for item in cleaned_results:
                all_columns.update(item.keys())

            # 按预定义顺序排列列，然后添加其他列
            ordered_columns = []
            for col in column_orders[mode]:
                if col in all_columns:
                    ordered_columns.append(col)
                    all_columns.remove(col)

            # 添加剩余列
            ordered_columns.extend(sorted(all_columns))

            # 创建DataFrame并指定列顺序
            df = pd.DataFrame(cleaned_results, columns=ordered_columns)
        else:
            df = pd.DataFrame(cleaned_results)

        # 生成文件名
        mode_names = {
            'sn': 'sn_papers_metadata',
            'ieee': 'ieee_papers_metadata',
            'funding': 'funding_papers_metadata',
            'ap': 'ap_papers_metadata'
        }
        filename = f"{mode_names.get(mode, 'papers_metadata')}.xlsx"
        file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)

        # 保存Excel文件
        df.to_excel(file_path, index=False, engine='openpyxl')

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    """获取处理进度"""
    try:
        task_info = processor.processing_tasks.get(task_id)
        if not task_info:
            return jsonify({'error': '任务不存在'}), 404

        return jsonify(task_info)

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# =========================
# 错误处理
# =========================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '接口不存在'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': '服务器内部错误'}), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({'error': '文件过大'}), 413

# =========================
# 应用启动
# =========================
if __name__ == '__main__':
    print("🚀 PDF元数据提取系统启动中...")
    print("📊 支持的提取模式: SN, IEEE, 资助信息, AP")
    print("🌐 访问地址: http://localhost:5000")
    print("📁 上传目录:", app.config['UPLOAD_FOLDER'])
    print("📁 结果目录:", app.config['RESULTS_FOLDER'])
    print("\n🔗 API接口列表:")
    print("  GET  /                     - 主页界面")
    print("  GET  /api/health           - 健康检查")
    print("  POST /api/upload           - 文件上传")
    print("  GET  /api/files            - 文件列表")
    print("  DEL  /api/files/<id>       - 删除文件")
    print("  POST /api/extract/<mode>   - 单模式提取")
    print("  POST /api/extract/batch    - 批量提取")
    print("  POST /api/export/excel     - 导出Excel")
    print("  POST /api/export/json      - 导出JSON")
    print("  POST /api/download/excel   - 直接下载Excel")
    print("  POST /process              - 流式处理")
    print("\n📝 日志系统已启用，日志文件保存在 log/ 目录")
    print("✨ 系统就绪，等待请求...")

    app.run(debug=True, host='0.0.0.0', port=5000)
