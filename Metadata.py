# -*- coding: utf-8 -*-
import re, json, math
import regex as reg
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import fitz
import aiohttp
import asyncio

# =========================
# 工具函数
# =========================
def norm(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s.strip())

def join_lines(lines: List[str]) -> str:
    return norm(" ".join([l.strip() for l in lines if l and l.strip()]))

def in_top_region(bbox, page_h, ratio=0.45):
    x0, y0, x1, y1 = bbox
    return (y0 / page_h) < ratio

EMDASH = "\u2014"  # — 

# =========================
# 数据结构
# =========================
@dataclass
class Affiliation:
    id: str
    name: str
    raw: str

@dataclass
class Author:
    order: int
    name: str
    superscripts: List[str]
    affiliation_ids: List[str]
    email: Optional[str] = None
    is_first_author: bool = False
    is_corresponding_author: bool = False

@dataclass
class PaperMeta:
    title: str
    abstract: Optional[str]
    keywords: List[str]
    authors: List[Author]
    affiliations: List[Affiliation]
    emails: List[str]
    confidence: float

# =========================
# LLM API 配置
# =========================
API_KEY = 'sk-bd884acabfc8420fb852bbdd86fa276a'  # 百炼API
API_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# LLM Prompt 模板
LLM_PROMPT_TEMPLATE = """
你是一个专业的学术论文信息提取专家。请从以下PDF第一页的文本内容中提取论文的元数据信息。

请严格按照以下JSON格式输出，不要添加任何解释性文字：

{{
  "title": "论文标题",
  "authors": [
    {{
      "name": "作者姓名",
      "order": 作者顺序号,
      "affiliation": "作者单位",
      "is_first_author": true/false,
      "is_corresponding_author": true/false,
      "email": "邮箱地址（如果有）"
    }}
  ],
  "abstract": "摘要内容",
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "emails": ["邮箱1", "邮箱2"],
  "confidence": 0.95
}}

提取规则：
1. 标题：通常是页面顶部最大字号的文本
2. 作者：按顺序提取所有作者姓名，识别通讯作者标记（*、†、‡等）
3. 单位：提取每个作者对应的机构名称
4. 摘要：从"Abstract"或"摘要"开始到"Keywords"或"关键词"结束
5. 关键词：提取关键词列表，用逗号或分号分隔
6. 邮箱：提取所有邮箱地址
7. 置信度：根据提取质量给出0-1之间的评分

以下是PDF第一页的文本内容：
{text_content}
"""

async def call_llm_api(text_content: str) -> dict:
    """调用LLM API进行智能解析"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen-flash",
        "max_tokens": 4000,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user", 
                "content": LLM_PROMPT_TEMPLATE.format(text_content=text_content)
            }
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_ENDPOINT, json=payload, headers=headers, timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result['choices'][0]['message']['content']
                    
                    # 提取JSON内容
                    json_start = content.find('{')
                    json_end = content.rfind('}')
                    if json_start != -1 and json_end != -1:
                        json_str = content[json_start:json_end + 1]
                        return json.loads(json_str)
                    else:
                        raise ValueError("LLM返回的内容中没有找到有效的JSON")
                else:
                    error_text = await response.text()
                    raise Exception(f"API请求失败: {response.status}, {error_text}")
    except Exception as e:
        print(f"LLM API调用失败: {e}")
        return None

def extract_text_from_pdf(pdf_path: str) -> str:
    """从PDF第一页提取纯文本内容"""
    try:
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            page = doc[0]
            text = page.get_text("text")
            doc.close()
            return text
        doc.close()
        return ""
    except Exception as e:
        print(f"PDF文本提取失败: {e}")
        return ""

# =========================
# 主流程
# =========================
async def extract_first_page_llm(pdf_path: str) -> PaperMeta:
    """使用LLM API提取PDF第一页信息"""
    # 1. 提取PDF文本
    text_content = extract_text_from_pdf(pdf_path)
    if not text_content:
        return PaperMeta(
            title="",
            abstract=None,
            keywords=[],
            authors=[],
            affiliations=[],
            emails=[],
            confidence=0.0
        )
    
    # 2. 调用LLM API
    llm_result = await call_llm_api(text_content)
    if not llm_result:
        return PaperMeta(
            title="",
            abstract=None,
            keywords=[],
            authors=[],
            affiliations=[],
            emails=[],
            confidence=0.0
        )
    
    # 3. 转换LLM结果到PaperMeta格式
    authors = []
    affiliations = []
    
    # 处理作者信息
    for author_data in llm_result.get('authors', []):
        author = Author(
            order=author_data.get('order', 0),
            name=author_data.get('name', ''),
            superscripts=[],
            affiliation_ids=[],
            email=author_data.get('email'),
            is_first_author=author_data.get('is_first_author', False),
            is_corresponding_author=author_data.get('is_corresponding_author', False)
        )
        authors.append(author)
        
        # 处理单位信息
        affiliation_name = author_data.get('affiliation', '')
        if affiliation_name:
            aff_id = str(len(affiliations) + 1)
            affiliation = Affiliation(
                id=aff_id,
                name=affiliation_name,
                raw=affiliation_name
            )
            affiliations.append(affiliation)
            author.affiliation_ids = [aff_id]
    
    # 4. 创建PaperMeta对象
    meta = PaperMeta(
        title=llm_result.get('title', ''),
        abstract=llm_result.get('abstract'),
        keywords=llm_result.get('keywords', []),
        authors=authors,
        affiliations=affiliations,
        emails=llm_result.get('emails', []),
        confidence=llm_result.get('confidence', 0.0)
    )
    
    return meta

# 保持原有的同步接口，用于向后兼容
def extract_first_page(pdf_path: str) -> PaperMeta:
    """同步版本的提取函数，内部调用异步版本"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(extract_first_page_llm(pdf_path))
    finally:
        loop.close()

# =========================
# 演示
# =========================
if __name__ == "__main__":
    path = "sample.pdf"  # 换成你的 PDF 路径
    meta = extract_first_page(path)
    # 序列化 dataclass
    output = {
        "title": meta.title,
        "abstract": meta.abstract,
        "keywords": meta.keywords,
        "authors": [asdict(a) for a in meta.authors],
        "affiliations": [asdict(aff) for aff in meta.affiliations],
        "emails": meta.emails,
        "confidence": meta.confidence
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
