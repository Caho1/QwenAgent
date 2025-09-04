#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试AP模式的作者姓名合并修改
验证字段从分离的姓名改为完整姓名
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_metadata_api import MetadataProcessor
from Metadata import PaperMeta, Author, Affiliation

def test_ap_mode_format():
    """测试AP模式的数据格式化"""
    processor = MetadataProcessor()
    
    # 创建测试数据
    authors = [
        Author(
            order=1,
            name="张三",
            superscripts=[],
            affiliation_ids=["1"],
            email="zhangsan@example.com",
            is_first_author=True,
            is_corresponding_author=False
        ),
        Author(
            order=2,
            name="李四",
            superscripts=[],
            affiliation_ids=["2"],
            email="lisi@example.com",
            is_first_author=False,
            is_corresponding_author=True
        )
    ]
    
    affiliations = [
        Affiliation(id="1", name="北京大学", raw="北京大学"),
        Affiliation(id="2", name="清华大学", raw="清华大学")
    ]
    
    meta = PaperMeta(
        title="测试论文标题",
        abstract="这是一个测试摘要",
        keywords=["关键词1", "关键词2", "关键词3"],
        authors=authors,
        affiliations=affiliations,
        emails=["zhangsan@example.com", "lisi@example.com"],
        confidence=0.95
    )
    
    # 测试AP模式格式化
    result = processor._format_ap_data(meta, "test_document.pdf")
    
    print("AP模式数据格式化测试:")
    print("=" * 60)
    
    # 期望的字段
    expected_fields = ['文件名', '题目', '关键词', '摘要', '第一作者姓名', '通讯作者姓名', 'filename']
    
    # 检查字段是否存在
    all_fields_present = True
    for field in expected_fields:
        if field in result:
            print(f"✅ {field}: {result[field]}")
        else:
            print(f"❌ 缺少字段: {field}")
            all_fields_present = False
    
    # 检查不应该存在的旧字段
    old_fields = ['第一作者姓', '第一作者名', '通讯作者姓', '通讯作者名']
    no_old_fields = True
    for field in old_fields:
        if field in result:
            print(f"❌ 不应该存在的旧字段: {field} = {result[field]}")
            no_old_fields = False
    
    if no_old_fields:
        print("✅ 没有发现旧的分离姓名字段")
    
    # 验证具体值
    print("\n字段值验证:")
    print("-" * 40)
    
    tests = [
        ("文件名", "test_document", result.get('文件名')),
        ("题目", "测试论文标题", result.get('题目')),
        ("第一作者姓名", "张三", result.get('第一作者姓名')),
        ("通讯作者姓名", "李四", result.get('通讯作者姓名')),
    ]
    
    all_values_correct = True
    for field_name, expected, actual in tests:
        if actual == expected:
            print(f"✅ {field_name}: {actual}")
        else:
            print(f"❌ {field_name}: 期望 '{expected}', 实际 '{actual}'")
            all_values_correct = False
    
    print("=" * 60)
    
    overall_success = all_fields_present and no_old_fields and all_values_correct
    if overall_success:
        print("🎉 AP模式修改测试通过！")
    else:
        print("❌ AP模式修改测试失败！")
    
    return overall_success

def test_ap_mode_edge_cases():
    """测试AP模式的边界情况"""
    processor = MetadataProcessor()
    
    print("\nAP模式边界情况测试:")
    print("=" * 60)
    
    # 测试1: 没有作者
    meta_no_authors = PaperMeta(
        title="无作者论文",
        abstract="测试摘要",
        keywords=["测试"],
        authors=[],
        affiliations=[],
        emails=[],
        confidence=0.8
    )
    
    result1 = processor._format_ap_data(meta_no_authors, "no_authors.pdf")
    
    test1_pass = (
        result1.get('第一作者姓名') == '' and
        result1.get('通讯作者姓名') == ''
    )
    
    print(f"{'✅' if test1_pass else '❌'} 无作者情况: 第一作者姓名='{result1.get('第一作者姓名')}', 通讯作者姓名='{result1.get('通讯作者姓名')}'")
    
    # 测试2: 只有第一作者，没有通讯作者
    authors_only_first = [
        Author(
            order=1,
            name="王五",
            superscripts=[],
            affiliation_ids=[],
            email="wangwu@example.com",
            is_first_author=True,
            is_corresponding_author=False
        )
    ]
    
    meta_only_first = PaperMeta(
        title="只有第一作者",
        abstract="测试摘要",
        keywords=["测试"],
        authors=authors_only_first,
        affiliations=[],
        emails=[],
        confidence=0.8
    )
    
    result2 = processor._format_ap_data(meta_only_first, "only_first.pdf")
    
    test2_pass = (
        result2.get('第一作者姓名') == '王五' and
        result2.get('通讯作者姓名') == ''
    )
    
    print(f"{'✅' if test2_pass else '❌'} 只有第一作者: 第一作者姓名='{result2.get('第一作者姓名')}', 通讯作者姓名='{result2.get('通讯作者姓名')}'")
    
    # 测试3: 第一作者同时是通讯作者
    authors_same = [
        Author(
            order=1,
            name="赵六",
            superscripts=[],
            affiliation_ids=[],
            email="zhaoliu@example.com",
            is_first_author=True,
            is_corresponding_author=True
        )
    ]
    
    meta_same = PaperMeta(
        title="第一作者是通讯作者",
        abstract="测试摘要",
        keywords=["测试"],
        authors=authors_same,
        affiliations=[],
        emails=[],
        confidence=0.8
    )
    
    result3 = processor._format_ap_data(meta_same, "same_author.pdf")
    
    test3_pass = (
        result3.get('第一作者姓名') == '赵六' and
        result3.get('通讯作者姓名') == '赵六'
    )
    
    print(f"{'✅' if test3_pass else '❌'} 第一作者是通讯作者: 第一作者姓名='{result3.get('第一作者姓名')}', 通讯作者姓名='{result3.get('通讯作者姓名')}'")
    
    print("=" * 60)
    
    all_edge_cases_pass = test1_pass and test2_pass and test3_pass
    if all_edge_cases_pass:
        print("🎉 边界情况测试通过！")
    else:
        print("❌ 边界情况测试失败！")
    
    return all_edge_cases_pass

def main():
    """运行所有测试"""
    print("开始测试AP模式的作者姓名合并修改")
    print("=" * 80)
    
    test1_passed = test_ap_mode_format()
    test2_passed = test_ap_mode_edge_cases()
    
    print("\n" + "=" * 80)
    if test1_passed and test2_passed:
        print("🎉 所有AP模式测试都通过了！修改成功。")
        return 0
    else:
        print("❌ 有测试失败，请检查代码。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
