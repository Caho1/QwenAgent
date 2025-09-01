# -*- coding: utf-8 -*-
"""
测试作者顺序修正功能
"""

import asyncio
from Metadata import extract_first_page_llm

async def test_specific_file():
    """测试特定文件的作者顺序"""
    file_path = "IEEE+资助论文收集测试文件/224101115330045576.pdf"

    print("测试文件:", file_path)
    print("期望的作者顺序: Honghua Zhao, Keyuan Zhang, Qianqian Tian, Wenguang Ren, Sai Zhang, Jin Yu")
    print("=" * 80)
    
    try:
        # 提取元数据
        meta = await extract_first_page_llm(file_path)
        
        print("提取到的作者信息:")
        for i, author in enumerate(meta.authors, 1):
            corresponding = " [通讯作者]" if author.is_corresponding_author else ""
            print(f"  {i}. {author.name} (order: {author.order}){corresponding}")
        
        print("\n作者顺序验证:")
        expected_order = ["Honghua Zhao", "Keyuan Zhang", "Qianqian Tian", "Wenguang Ren", "Sai Zhang", "Jin Yu"]
        actual_order = [author.name for author in meta.authors[:6]]  # 只看前6个
        
        print(f"期望顺序: {expected_order}")
        print(f"实际顺序: {actual_order}")
        
        if actual_order == expected_order:
            print("✅ 作者顺序正确！")
        else:
            print("❌ 作者顺序不正确")
            
            # 分析差异
            for i, (expected, actual) in enumerate(zip(expected_order, actual_order)):
                if expected != actual:
                    print(f"   位置{i+1}: 期望'{expected}', 实际'{actual}'")
        
    except Exception as e:
        print(f"❌ 提取失败: {e}")

if __name__ == '__main__':
    asyncio.run(test_specific_file())
