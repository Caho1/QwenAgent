# -*- coding: utf-8 -*-
"""
数据处理模块 - PDF元数据提取系统
专注于数据处理逻辑，支持不同模式的分支处理
"""

import os
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import asdict

# 导入现有的元数据提取模块
from Metadata import extract_first_page_llm, PaperMeta, extract_acknowledgment_from_last_pages


class BaseProcessor:
    """基础处理器 - 包含通用的数据处理方法"""
    
    def __init__(self):
        pass
    
    def _extract_real_filename(self, file_path: str) -> str:
        """从文件路径中提取真实的文件名（去掉UUID前缀和.pdf扩展名）"""
        filename = os.path.basename(file_path)
        if '_' in filename:
            # 检查第一部分是否是UUID格式（8-4-4-4-12个字符）
            parts = filename.split('_', 1)
            if len(parts) == 2:
                potential_uuid = parts[0]
                # 简单的UUID格式检查：长度为36且包含4个连字符
                if len(potential_uuid) == 36 and potential_uuid.count('-') == 4:
                    # 格式：UUID_真实文件名.pdf
                    filename = parts[1]

        # 去掉.pdf扩展名
        if filename.lower().endswith('.pdf'):
            filename = filename[:-4]

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

    def _get_author_affiliation(self, author, affiliations) -> str:
        """获取作者单位"""
        if not author or not author.affiliation_ids:
            return ''
        
        for aff_id in author.affiliation_ids:
            aff = next((aff for aff in affiliations if aff.id == aff_id), None)
            if aff:
                return aff.name
        return ''


class ComplexProcessor(BaseProcessor):
    """复杂处理器 - 用于IEEE和FUNDING模式，保持现有的复杂双栏判定处理逻辑"""
    
    async def process_file(self, file_path: str, mode: str) -> Dict[str, Any]:
        """处理单个PDF文件 - 复杂模式（IEEE/FUNDING）"""
        try:
            # 调用现有的元数据提取函数，传递mode参数以使用对应的提示词
            meta = await extract_first_page_llm(file_path, mode)
            
            # 根据模式转换数据格式
            if mode == 'ieee':
                return self._format_ieee_data(meta, file_path)
            elif mode == 'funding':
                return self._format_funding_data(meta, file_path)
            else:
                raise ValueError(f"ComplexProcessor不支持的模式: {mode}")
                
        except Exception as e:
            filename = self._extract_real_filename(file_path)
            return {
                'error': str(e),
                'file': file_path,
                'filename': filename,
                # 根据模式添加对应的文件名字段
                '文件名': filename,  # 资助信息模式
                '订单号': filename,  # IEEE模式
                'status': 'failed'
            }
    
    def _format_ieee_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化IEEE模式数据 - 保持复杂处理逻辑"""
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

        # 获取去掉.pdf扩展名的文件名
        filename = self._extract_real_filename(file_path)

        # 按照指定顺序返回字段
        return {
            '订单号': filename,
            '英文题目': meta.title,
            '英文副标': '',  # 需要从标题中分离
            '作者姓名': all_authors,
            '第一作者邮箱': first_author_email,
            'filename': filename  # 添加通用filename字段（用于内部处理）
        }
    
    def _format_funding_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化资助信息模式数据 - 保持复杂处理逻辑"""
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


class SimpleProcessor(BaseProcessor):
    """简化处理器 - 用于SN和AP模式，不需要复杂的双栏判定功能"""
    
    async def process_file(self, file_path: str, mode: str) -> Dict[str, Any]:
        """处理单个PDF文件 - 简化模式（SN/AP）"""
        try:
            # 调用现有的元数据提取函数，传递mode参数以使用对应的提示词
            meta = await extract_first_page_llm(file_path, mode)
            
            # 根据模式转换数据格式
            if mode == 'sn':
                return self._format_sn_data(meta, file_path)
            elif mode == 'ap':
                return self._format_ap_data(meta, file_path)
            else:
                raise ValueError(f"SimpleProcessor不支持的模式: {mode}")
                
        except Exception as e:
            filename = self._extract_real_filename(file_path)
            return {
                'error': str(e),
                'file': file_path,
                'filename': filename,
                # 根据模式添加对应的文件名字段
                '文件名': filename,  # AP模式
                'Number': filename,  # SN模式
                'status': 'failed'
            }
    
    def _format_sn_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化SN模式数据 - 支持动态作者数量的简化处理逻辑"""
        filename = self._extract_real_filename(file_path)

        # 基础字段（固定顺序）
        result = {
            'Number': filename,
            'Title': meta.title,
            'SubTitle': '',  # 需要从标题中分离副标题
            'Author count': len(meta.authors),
            'All author': ', '.join([author.name for author in meta.authors]),
            'Corresponding Author': '',
            "Corresponding author's email": '',
            'filename': filename  # 添加通用filename字段
        }

        # 动态生成作者和单位字段
        for i, author in enumerate(meta.authors, 1):
            result[f'Author {i}'] = author.name

            # 为每个作者生成对应的单位字段
            affiliation_name = ''
            if author.affiliation_ids:
                # 获取第一个匹配的单位
                for aff_id in author.affiliation_ids:
                    aff = next((aff for aff in meta.affiliations if aff.id == aff_id), None)
                    if aff:
                        affiliation_name = aff.name
                        break

            result[f'Affiliation {i}'] = affiliation_name

            # 识别通讯作者
            if author.is_corresponding_author:
                result['Corresponding Author'] = author.name
                result["Corresponding author's email"] = author.email or ''

        # 如果没有标记通讯作者，使用第一作者
        if not result['Corresponding Author'] and meta.authors:
            result['Corresponding Author'] = meta.authors[0].name
            result["Corresponding author's email"] = meta.authors[0].email or ''

        return result
    
    def _format_ap_data(self, meta: PaperMeta, file_path: str) -> Dict[str, Any]:
        """格式化AP模式数据 - 简化处理逻辑"""
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

        # 第一作者完整姓名
        if first_author:
            result['第一作者姓名'] = first_author.name
        else:
            result['第一作者姓名'] = ''

        # 通讯作者完整姓名
        if corresponding_author:
            result['通讯作者姓名'] = corresponding_author.name
        else:
            result['通讯作者姓名'] = ''

        # 全部作者姓名（用逗号分隔）
        if meta.authors:
            all_authors = ', '.join([author.name for author in meta.authors])
            result['全部作者姓名'] = all_authors
        else:
            result['全部作者姓名'] = ''

        return result


class MetadataProcessor:
    """元数据处理器 - 统一的处理接口，根据模式选择不同的处理器"""
    
    def __init__(self):
        self.complex_processor = ComplexProcessor()  # IEEE和FUNDING模式
        self.simple_processor = SimpleProcessor()    # SN和AP模式
        self.processing_tasks = {}
    
    async def process_file(self, file_path: str, mode: str) -> Dict[str, Any]:
        """处理单个PDF文件 - 根据模式选择处理器"""
        if mode in ['ieee', 'funding']:
            # 使用复杂处理器（保持现有的复杂双栏判定处理逻辑）
            return await self.complex_processor.process_file(file_path, mode)
        elif mode in ['sn', 'ap']:
            # 使用简化处理器（不需要复杂的双栏判定功能）
            return await self.simple_processor.process_file(file_path, mode)
        else:
            raise ValueError(f"不支持的模式: {mode}")
    
    def _clean_export_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清理导出数据，移除内部处理字段"""
        return self.complex_processor._clean_export_data(data)
    
    def _extract_real_filename(self, file_path: str) -> str:
        """从文件路径中提取真实的文件名"""
        return self.complex_processor._extract_real_filename(file_path)
