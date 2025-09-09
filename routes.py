# -*- coding: utf-8 -*-
"""
PDF元数据提取系统 - Flask API路由
专注于API接口定义，数据处理逻辑已分离到data_processor模块
"""

import os
import json
import uuid
import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from flask import Flask, request, jsonify, Response, render_template, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pandas as pd

# 导入数据处理模块
from data_processor import MetadataProcessor
from concurrent_processor import get_global_processor, ConcurrentProcessor, RateLimitConfig
from config import Config
from log_manager import log_manager, log_operation, log_file_upload, log_file_processing, log_batch_processing, log_api_call, start_upload_session, end_upload_session, update_session_mode

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

def get_sn_column_order(data):
    """动态生成SN模式的列顺序"""
    if not data:
        return []

    # 基础字段（固定顺序）
    base_columns = [
        'Number', 'Title', 'SubTitle', 'Author count', 'All author',
        'Corresponding Author', "Corresponding author's email"
    ]

    # 找出最大作者数量
    max_authors = 0
    for item in data:
        if isinstance(item, dict):
            # 统计Author N字段的数量
            author_count = 0
            for key in item.keys():
                if key.startswith('Author ') and key.replace('Author ', '').isdigit():
                    author_num = int(key.replace('Author ', ''))
                    author_count = max(author_count, author_num)
            max_authors = max(max_authors, author_count)

    # 动态生成作者和单位字段
    dynamic_columns = []
    for i in range(1, max_authors + 1):
        dynamic_columns.extend([f'Author {i}', f'Affiliation {i}'])

    return base_columns + dynamic_columns


def get_ap_column_order(data):
    """动态生成AP模式的列顺序"""
    if not data:
        return []

    # 基础字段（固定顺序）
    base_columns = [
        '文件名', '题目', '关键词', '摘要', '第一作者姓名', '通讯作者姓名', '通讯作者邮箱'
    ]

    # 找出最大作者数量
    max_authors = 0
    for item in data:
        if isinstance(item, dict):
            # 统计作者N字段的数量
            author_count = 0
            for key in item.keys():
                if key.startswith('作者') and key.replace('作者', '').isdigit():
                    author_num = int(key.replace('作者', ''))
                    author_count = max(author_count, author_num)
            max_authors = max(max_authors, author_count)

    # 动态生成作者字段
    dynamic_columns = []
    for i in range(1, max_authors + 1):
        dynamic_columns.append(f'作者{i}')

    return base_columns + dynamic_columns

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

        # 记录上传开始
        total_input_files = len([f for f in files if f and f.filename])
        logger.info(f"开始处理 {total_input_files} 个上传文件")

        # 数量限制（前端已限制，后端再次兜底）
        if total_input_files > Config.MAX_UPLOAD_FILES:
            msg = f"超出上传数量限制：最多只能上传 {Config.MAX_UPLOAD_FILES} 个文件"
            logger.warning(msg)
            return jsonify({'success': False, 'error': msg, 'limit': Config.MAX_UPLOAD_FILES}), 400

        # 开始上传会话
        session_key = start_upload_session(total_input_files, "文件上传")

        for i, file in enumerate(files):
            if not file:
                logger.warning(f"文件 {i+1}: 空文件对象")
                continue

            if not file.filename:
                logger.warning(f"文件 {i+1}: 文件名为空")
                errors.append({'filename': '未知', 'error': '文件名为空'})
                continue

            if not allowed_file(file.filename):
                logger.warning(f"文件 {i+1}: 不支持的文件格式 - {file.filename}")
                errors.append({'filename': file.filename, 'error': '不支持的文件格式，仅支持PDF文件'})
                continue

            try:
                filename = secure_filename(file.filename)
                file_id = str(uuid.uuid4())
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")

                logger.debug(f"保存文件: {filename} -> {file_path}")
                file.save(file_path)

                # 验证文件是否成功保存
                if not os.path.exists(file_path):
                    logger.error(f"文件保存失败: {filename} - 文件不存在")
                    errors.append({'filename': filename, 'error': '文件保存失败'})
                    continue

                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    logger.error(f"文件为空: {filename}")
                    errors.append({'filename': filename, 'error': '文件为空'})
                    os.remove(file_path)  # 删除空文件
                    continue

                # 记录文件上传日志
                log_file_upload(filename, file_size)
                logger.debug(f"文件上传成功: {filename} ({file_size} bytes)")

                uploaded_files.append({
                    'file_id': file_id,
                    'filename': filename,
                    'path': file_path,
                    'size': file_size
                })

            except Exception as e:
                logger.error(f"文件处理异常: {file.filename} - {str(e)}")
                errors.append({'filename': file.filename, 'error': f'文件处理失败: {str(e)}'})

        processing_time = time.time() - start_time

        # 验证上传结果的完整性
        successful_uploads = len(uploaded_files)
        failed_uploads = len(errors)
        logger.info(f"文件上传完成: 成功 {successful_uploads}, 失败 {failed_uploads}, 总计 {total_input_files}")

        if successful_uploads + failed_uploads != total_input_files:
            logger.error(f"❌ 文件上传计数不匹配！输入: {total_input_files}, 成功: {successful_uploads}, 失败: {failed_uploads}")

        # 结束上传会话（不再返回日志文件名）
        end_upload_session(successful_uploads, failed_uploads)

        if not uploaded_files and errors:
            return jsonify({
                'success': False,
                'error': '所有文件上传失败',
                'errors': errors
            }), 400

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
            # 从文件名中提取真实文件名（去掉UUID前缀和.pdf扩展名）
            full_filename = file_path.name
            if '_' in full_filename:
                # 格式：UUID_真实文件名.pdf
                real_filename = '_'.join(full_filename.split('_')[1:])
            else:
                real_filename = full_filename

            # 去掉.pdf扩展名
            if real_filename.lower().endswith('.pdf'):
                real_filename = real_filename[:-4]

            files.append({
                'filename': real_filename,  # 返回去掉.pdf扩展名的真实文件名
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
        # 始终使用并发处理，无论文件数量多少

        if not file_paths:
            return jsonify({'error': '没有指定文件路径'}), 400

        # 数量限制（后端兜底）
        if len(file_paths) > Config.MAX_UPLOAD_FILES:
            return jsonify({'success': False, 'error': f'超出上传数量限制：最多处理 {Config.MAX_UPLOAD_FILES} 个文件', 'limit': Config.MAX_UPLOAD_FILES}), 400

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

        # 记录处理前的文件数量
        input_file_count = len(valid_files)
        logger.info(f"开始处理 {input_file_count} 个有效文件，模式: {mode}")

        # 更新现有会话的处理模式，而不是创建新会话
        mode_names = {
            'sn': 'SN期刊信息提取',
            'ap': 'AP信息表收集',
            'ieee': 'IEEE格式处理',
            'funding': '基金信息提取'
        }
        session_key = update_session_mode(mode_names.get(mode, f'{mode}模式处理'))

        # 统一使用并发处理（无论文件数量多少）
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

        # 验证处理结果的完整性
        output_result_count = len(results)
        logger.info(f"处理完成，输入文件数: {input_file_count}, 输出结果数: {output_result_count}")

        if input_file_count != output_result_count:
            logger.error(f"❌ 文件处理不完整！丢失了 {input_file_count - output_result_count} 个文件")

            # 找出丢失的文件
            input_files = set(valid_files)
            output_files = set(r.get('file', '') for r in results if isinstance(r, dict))
            missing_files = input_files - output_files

            if missing_files:
                logger.error(f"丢失的文件: {list(missing_files)}")
        else:
            logger.info("✓ 所有文件都已正确处理")

        # 统计处理结果
        successful_results = [r for r in results if r.get('status') != 'failed' and 'error' not in r]
        failed_results = [r for r in results if r.get('status') == 'failed' or 'error' in r]

        # 结束处理会话（不再返回日志文件名）
        end_upload_session(len(successful_results), len(failed_results))

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
            'results': [{k: v for k, v in r.items() if k != 'tokens_used'} for r in all_results],
            'count': len(all_results),
            'successful': successful_count,
            'failed': len(all_results) - successful_count,
            'concurrent_used': True  # 始终使用并发处理
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/batch', methods=['POST'])
def extract_batch_optimized():
    """专门的批量处理端点（优化大文件处理）"""
    try:
        data = request.get_json()
        file_paths = data.get('file_paths', [])
        mode = data.get('mode', 'sn')

        if mode not in ['sn', 'ieee', 'funding', 'ap']:
            return jsonify({'error': f'不支持的模式: {mode}'}), 400

        if not file_paths:
            return jsonify({'error': '没有指定文件路径'}), 400

        # 数量限制（后端兜底）
        if len(file_paths) > Config.MAX_UPLOAD_FILES:
            return jsonify({'success': False, 'error': f'超出上传数量限制：最多处理 {Config.MAX_UPLOAD_FILES} 个文件', 'limit': Config.MAX_UPLOAD_FILES}), 400

        # 原先移除限制，这里恢复为受控并发

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
            'results': [{k: v for k, v in r.items() if k != 'tokens_used'} for r in results],
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

@app.route('/api/extract/batch_multi', methods=['POST'])
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
            'results': {m: [{k: v for k, v in r.items() if k != 'tokens_used'} for r in res] for m, res in results.items()},
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
                        # 获取tokens使用量（仅用于日志，不对外返回）
                        tokens_used = result.get('tokens_used', 0)
                        # 记录成功处理日志
                        log_file_processing(real_filename, mode, file_processing_time, "success", None, tokens_used)

                        # 去除对外不展示的内部字段
                        public_result = {k: v for k, v in result.items() if k != 'tokens_used'}

                        yield json.dumps({
                            'type': 'data_row',
                            'data': public_result
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
            'funding': ['文件名', '论文英文题目', '第一作者姓名', '第一作者单位', '通讯作者姓名', '通讯作者单位',
                       '通讯作者邮箱', '关键词', '摘要', '致谢']
        }

        # 获取当前模式的字段顺序
        if mode == 'sn':
            # SN模式使用动态列顺序
            column_order = get_sn_column_order(cleaned_results)
        elif mode == 'ap':
            # AP模式使用动态列顺序
            column_order = get_ap_column_order(cleaned_results)
        elif mode in column_orders:
            column_order = column_orders[mode]
        else:
            column_order = None

        if column_order:
            # 按指定顺序重新组织数据
            ordered_results = []
            for item in cleaned_results:
                ordered_item = {}
                # 先按指定顺序添加字段
                for col in column_order:
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
            'funding': ['文件名', '论文英文题目', '第一作者姓名', '第一作者单位', '通讯作者姓名', '通讯作者单位',
                       '通讯作者邮箱', '关键词', '摘要', '致谢']
        }

        # 按指定顺序重新组织数据
        if mode == 'sn':
            # SN模式使用动态列顺序
            column_order = get_sn_column_order(cleaned_results)
        elif mode == 'ap':
            # AP模式使用动态列顺序
            column_order = get_ap_column_order(cleaned_results)
        elif mode in column_orders:
            column_order = column_orders[mode]
        else:
            column_order = None

        if column_order:
            ordered_results = []
            for item in cleaned_results:
                ordered_item = {}
                # 先按指定顺序添加字段
                for col in column_order:
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
    print("🌐 访问地址: http://localhost:6666")
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

    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
