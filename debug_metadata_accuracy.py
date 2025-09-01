# -*- coding: utf-8 -*-
"""
简单的 Metadata.py 调试脚本
选择文件夹和文件范围，输出提取结果
"""

import os
import asyncio
from Metadata import extract_first_page_llm, extract_acknowledgment_from_last_pages

class SimpleDebugger:
    def __init__(self):
        self.folders = [
            "IEEE+资助论文收集测试文件",
            "SN收集测试文件",
            "AP测试文件"
        ]

    def get_files_in_folder(self, folder_index: int) -> list:
        """获取指定文件夹中的所有PDF文件"""
        if folder_index < 0 or folder_index >= len(self.folders):
            return []

        folder = self.folders[folder_index]
        if not os.path.exists(folder):
            return []

        files = [f for f in os.listdir(folder) if f.lower().endswith('.pdf')]
        files.sort()  # 按文件名排序
        return [os.path.join(folder, f) for f in files]

    async def extract_and_print(self, file_path: str, index: int):
        """提取并打印单个文件的元数据"""
        filename = os.path.basename(file_path)
        print(f"\n{'='*80}")
        print(f"文件 {index}: {filename}")
        print(f"{'='*80}")

        try:
            # 提取元数据
            meta = await extract_first_page_llm(file_path)
            acknowledgment = extract_acknowledgment_from_last_pages(file_path)

            # 输出结果
            print(f"标题: {meta.title}")
            print(f"摘要: {meta.abstract}")
            print(f"关键词: {', '.join(meta.keywords) if meta.keywords else '无'}")

            print(f"\n作者信息:")
            for i, author in enumerate(meta.authors, 1):
                corresponding = " [通讯作者]" if author.is_corresponding_author else ""
                print(f"  {i}. {author.name} ({author.email}){corresponding}")

            print(f"\n单位信息:")
            for i, affiliation in enumerate(meta.affiliations, 1):
                print(f"  {i}. {affiliation}")

            print(f"\n致谢信息:")
            if acknowledgment and acknowledgment.strip():
                print(f"  {acknowledgment}")
            else:
                print(f"  无")

        except Exception as e:
            print(f"❌ 提取失败: {e}")

    async def run(self):
        """运行调试"""
        print("简单调试工具")
        print("=" * 50)

        # 显示文件夹选项
        print("可用文件夹:")
        for i, folder in enumerate(self.folders):
            if os.path.exists(folder):
                file_count = len([f for f in os.listdir(folder) if f.endswith('.pdf')])
                print(f"  {i+1}. {folder} ({file_count} 个文件)")

        # 选择文件夹
        folder_choice = int(input("选择文件夹 (1-3): ")) - 1
        files = self.get_files_in_folder(folder_choice)

        if not files:
            print("文件夹为空或不存在")
            return

        print(f"\n文件夹中有 {len(files)} 个PDF文件")

        # 选择文件范围
        start = int(input(f"开始文件序号 (1-{len(files)}): ")) - 1
        end = int(input(f"结束文件序号 (1-{len(files)}): ")) - 1

        if start < 0 or end >= len(files) or start > end:
            print("文件序号范围无效")
            return

        # 处理选定的文件
        selected_files = files[start:end+1]
        print(f"\n将处理 {len(selected_files)} 个文件")

        for i, file_path in enumerate(selected_files, start+1):
            await self.extract_and_print(file_path, i)

async def main():
    debugger = SimpleDebugger()
    await debugger.run()

if __name__ == '__main__':
    asyncio.run(main())
