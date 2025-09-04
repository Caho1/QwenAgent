# -*- coding: utf-8 -*-
"""
metadata.py — 基于 PyMuPDF get_text("words") 的作者切分与排序（修复“整行一个span导致排序错乱”）

修复点：
1) 不再依赖 span；改用 page.get_text("words")，按 (block_no, line_no) 精确还原“行”。
2) 在单行中按分隔符（"," ";" "and" "&"）将作者序列切分为候选“姓名盒”(bbox)。
3) 绑定 LLM 输出姓名 → 候选盒；然后按“行从上到下、行内从左到右”排序，无需判断单双栏。
4) 绑定不足时回退，但去除了会引入错序的 n==5 特例；回退仅保持原顺序。
5) API Key 改为环境变量 DASHSCOPE_API_KEY。

对外接口保持：
- extract_first_page(pdf_path) → PaperMeta
- extract_first_page_llm(pdf_path) → PaperMeta (async)
- fix_author_order_precise(authors, pdf_path) 内部改用行聚类+行内排序。
"""

import os
import re
import json
import difflib
import asyncio
import aiohttp
from statistics import median
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple

import pymupdf as fitz
import regex as reg
from config import Config

# =========================
# 工具
# =========================

def norm(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s.strip())


def join_lines(lines: List[str]) -> str:
    return norm(" ".join([l.strip() for l in lines if l and l.strip()]))


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
# LLM API
# =========================

# 使用config.py中的配置
API_KEY = Config.LLM_API_KEY
API_ENDPOINT = Config.LLM_API_ENDPOINT

LLM_PROMPT_TEMPLATE = """
你是一个专业的学术论文信息提取专家。请从以下PDF第一页的文本内容中提取论文的元数据信息。

请严格按照以下JSON格式输出，不要添加任何解释性文字：
{{
  "title": "论文标题",
  "authors": [
    {{
      "name": "作者姓名",
      "order": 作者顺序号（从1开始），
      "affiliation": "作者单位",
      "is_first_author": true/false,
      "is_corresponding_author": true/false,
      "email": "邮箱地址（如果有）"
    }}
  ],
  "abstract": "摘要内容",
  "keywords": ["关键词1", "关键词2"],
  "emails": ["邮箱1"],
  "confidence": 0.95
}}

注意：作者顺序必须与视觉阅读顺序一致：行从上到下，行内从左到右。

关于关键词：论文中可能为"Keyword"/"Keywords", 如果不是"Keyword"/"Keywords",则关键词留空,关键词有可能是缩写,请不要忽略,比如“Gp” “LLM”等。


以下是PDF第一页的文本内容：
{text_content}
"""


async def call_llm_api(text_content: str) -> dict:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": Config.LLM_MODEL,
        "max_tokens": Config.LLM_MAX_TOKENS,
        "temperature": Config.LLM_TEMPERATURE,
        "messages": [{"role": "user", "content": LLM_PROMPT_TEMPLATE.format(text_content=text_content)}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_ENDPOINT, json=payload, headers=headers, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    i, j = content.find("{"), content.rfind("}")
                    if i != -1 and j != -1:
                        return json.loads(content[i:j+1])
                    raise ValueError("LLM返回缺少有效JSON")
                else:
                    raise RuntimeError(f"API {resp.status}: {await resp.text()}")
    except Exception as e:
        print("LLM API调用失败:", e)
        return None


# =========================
# PDF 抽取
# =========================

def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            text = doc[0].get_text("text")
            doc.close()
            return text
        doc.close()
        return ""
    except Exception as e:
        print("PDF文本提取失败:", e)
        return ""


def extract_acknowledgment_from_last_pages(pdf_path: str) -> str:
    try:
        doc = fitz.open(pdf_path)
        n = len(doc)
        if n == 0:
            doc.close(); return ""
        pages = [n-2, n-1] if n >= 2 else [n-1]
        ak = ["ACKNOWLEDGMENT","ACKNOWLEDGMENTS","ACKNOWLEDGEMENT","ACKNOWLEDGEMENTS","致谢","谢辞"]
        rk = ["REFERENCES","REFERENCE","参考文献"]
        out = ""
        for p in pages:
            page_text = doc[p].get_text("text")
            pos = -1; kw = ""
            for k in ak:
                q = page_text.upper().find(k.upper())
                if q != -1: pos, kw = q, k; break
            if pos != -1:
                end = len(page_text)
                for r in rk:
                    q = page_text.upper().find(r.upper(), pos)
                    if q != -1: end = q; break
                lines = [ln.strip() for ln in page_text[pos:end].split("\n") if ln.strip()]
                if lines:
                    if len(lines[0].replace(kw, "").strip()) < 10: lines = lines[1:]
                out = " ".join(lines).strip(); break
        doc.close()
        if out and len(out) >= 20:
            out = re.sub(r"\d+\s*$", "", out)
            out = re.sub(r"\s+", " ", out).strip()
            return out[:1000] + ("..." if len(out) > 1000 else "")
        return ""
    except Exception as e:
        print("致谢信息提取失败:", e)
        return ""


# =========================
# 作者定位与排序（基于 words ）
# =========================

BAD_AFFIL_KW = {
    'university','institute','department','school','college','laboratory','lab','company',
    'inc.','co.','co.,ltd','co.ltd','ltd','center','centre','academy','hospital','research'
}
SEPS = {',',';'}
SEP_WORDS = {'and','&'}


def _match_score(a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    s1 = difflib.SequenceMatcher(None, a, b).ratio()
    pa, pb = a.split(), b.split()
    s2 = difflib.SequenceMatcher(None, " ".join(reversed(pa)), " ".join(reversed(pb))).ratio()
    # 中文姓名轻微加权
    try:
        if reg.match(r"^\p{Han}{2,4}$", a):
            s1 += 0.05; s2 += 0.05
    except Exception:
        pass
    return max(s1, s2)


def _words_top_region(page, top_ratio=0.8) -> List[Tuple[float,float,float,float,str,int,int,int]]:
    """获取上方区域的 words 列表。返回 (x0,y0,x1,y1,txt,block,line,word)"""
    H = page.rect.height
    w = [w for w in page.get_text("words") if w[1] <= H*top_ratio]
    # 过滤明显无意义的词
    out = []
    for x0,y0,x1,y1,txt,blk,ln,wd in w:
        t = txt.strip()
        if not t: continue
        # 过滤只含标点/数字
        letters = sum(c.isalpha() for c in t)
        if letters < max(1, int(0.5*len(t))):
            # 但是如果就是分隔符，也保留（用于切分）
            if t.lower() not in SEP_WORDS and t not in SEPS:
                continue
        out.append((x0,y0,x1,y1,t,blk,ln,wd))
    return out


def _group_lines(words):
    """按 (block,line) 分组，得到有序的“行”。每行内按 x0 升序。"""
    lines: Dict[Tuple[int,int], List[tuple]] = {}
    for w in words:
        key = (w[5], w[6])
        lines.setdefault(key, []).append(w)
    # 按 y0 排序行，再行内按 x0
    ordered = []
    for key, ws in lines.items():
        ws.sort(key=lambda z: z[0])
        y_mean = sum(z[1] for z in ws)/len(ws)
        ordered.append((y_mean, ws))
    ordered.sort(key=lambda p: p[0])
    return [ws for _, ws in ordered]


def _split_authors_on_line(ws):
    """在一行内，基于分隔符把作者序列切成若干“姓名盒”。"""
    groups = []
    cur_tokens = []
    for x0,y0,x1,y1,txt,blk,ln,wd in ws:
        low = txt.lower()
        if txt in SEPS or low in SEP_WORDS:
            # 碰到分隔符，收束一次
            if cur_tokens:
                groups.append(cur_tokens); cur_tokens = []
        else:
            cur_tokens.append((x0,y0,x1,y1,txt))
    if cur_tokens:
        groups.append(cur_tokens)

    boxes = []
    for toks in groups:
        text = " ".join(t[4] for t in toks).strip()
        if not text: continue
        tl = text.lower()
        if any(k in tl for k in BAD_AFFIL_KW):
            # 跳过明显是单位的片段
            continue
        x0 = min(t[0] for t in toks); y0 = min(t[1] for t in toks)
        x1 = max(t[2] for t in toks); y1 = max(t[3] for t in toks)
        boxes.append({
            "text": text,
            "bbox": (x0,y0,x1,y1),
            "cx": 0.5*(x0+x1),
            "cy": 0.5*(y0+y1),
            "h": (y1-y0)
        })
    return boxes


def _collect_author_boxes(page) -> List[Dict[str,Any]]:
    """主函数：基于 words 提取“姓名盒”。兼容单行、单栏多行、双栏、多栏。"""
    words = _words_top_region(page)
    if not words:
        return []
    lines = _group_lines(words)
    boxes = []
    for ws in lines:
        boxes.extend(_split_authors_on_line(ws))
    return boxes


def _bind_names_to_boxes(author_names: List[str], boxes: List[Dict[str,Any]]):
    used = set(); bound = []
    for name in author_names:
        best, best_i, best_sc = None, -1, 0.0
        for i, b in enumerate(boxes):
            if i in used: continue
            sc = _match_score(name, b["text"])
            if sc > best_sc: best, best_i, best_sc = b, i, sc
        if best is not None and best_sc >= 0.55:
            used.add(best_i); bound.append({"name": name, **best, "score": best_sc})
        else:
            bound.append({"name": name, "bbox": None, "cx": None, "cy": None, "h": None, "score": 0.0})
    return bound


def _cluster_rows_by_y(bound_points: List[Dict[str,Any]]):
    pts = [p for p in bound_points if p["cx"] is not None]
    if not pts: return []
    pts.sort(key=lambda x: x["cy"])  # 先按 y
    hs = [p["h"] for p in pts if p["h"]]
    h_med = median(hs) if hs else 12.0
    tau = max(h_med*0.6, 4.0)
    rows = []; cur = [pts[0]]; cur_cy = pts[0]["cy"]
    for p in pts[1:]:
        if abs(p["cy"] - cur_cy) <= tau:
            cur.append(p); cur_cy = median([q["cy"] for q in cur])
        else:
            rows.append(cur); cur = [p]; cur_cy = p["cy"]
    if cur: rows.append(cur)
    for r in rows: r.sort(key=lambda x: x["cx"])  # 行内左→右
    rows.sort(key=lambda r: median([p["cy"] for p in r]))
    return rows


def reorder_authors_by_rows(pdf_path: str, authors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(authors) <= 1:
        return authors
    try:
        doc = fitz.open(pdf_path); page = doc[0]
        boxes = _collect_author_boxes(page)
        if not boxes:
            doc.close(); return authors  # 不再做会破坏顺序的启发式
        names = [a.get("name", "") for a in authors]
        bound = _bind_names_to_boxes(names, boxes)
        ok = [b for b in bound if b["cx"] is not None]
        if len(ok) < max(2, int(0.7*len(authors))):
            doc.close(); return authors
        rows = _cluster_rows_by_y(ok)
        ordered_names = [p["name"] for row in rows for p in row]
        name2idx = {a.get("name"," "): i for i,a in enumerate(authors)}
        used=set(); reordered=[]
        for nm in ordered_names:
            i=name2idx.get(nm)
            if i is not None and i not in used:
                reordered.append(authors[i]); used.add(i)
        for i,a in enumerate(authors):
            if i not in used: reordered.append(a)
        for i,a in enumerate(reordered,1): a["order"]=i
        doc.close(); return reordered
    except Exception as e:
        print("按行排序失败:", e)
        return authors


def fix_author_order_precise(authors: List[Dict[str, Any]], pdf_path: str) -> List[Dict[str, Any]]:
    return reorder_authors_by_rows(pdf_path, authors)


# =========================
# 主流程
# =========================

async def extract_first_page_llm(pdf_path: str) -> PaperMeta:
    text_content = extract_text_from_pdf(pdf_path)
    if not text_content:
        return PaperMeta(title="", abstract=None, keywords=[], authors=[], affiliations=[], emails=[], confidence=0.0)
    llm_result = await call_llm_api(text_content)
    if not llm_result:
        return PaperMeta(title="", abstract=None, keywords=[], authors=[], affiliations=[], emails=[], confidence=0.0)

    # 修正作者顺序
    author_list = llm_result.get('authors', []) or []
    corrected_authors = fix_author_order_precise(author_list, pdf_path)

    # 单位去重映射
    affiliations: List[Affiliation] = []
    aff_map: Dict[str, str] = {}
    def _get_aff_id(name: str) -> Optional[str]:
        if not name: return None
        key = name.strip()
        if key in aff_map: return aff_map[key]
        idx = str(len(affiliations) + 1)
        affiliations.append(Affiliation(id=idx, name=key, raw=key))
        aff_map[key] = idx
        return idx

    authors: List[Author] = []
    for a in corrected_authors:
        aff_id = _get_aff_id(a.get('affiliation','') or '')
        authors.append(Author(
            order=a.get('order',0),
            name=a.get('name',''),
            superscripts=[],
            affiliation_ids=[aff_id] if aff_id else [],
            email=a.get('email'),
            is_first_author=a.get('is_first_author', False),
            is_corresponding_author=a.get('is_corresponding_author', False)
        ))

    meta = PaperMeta(
        title=llm_result.get('title',''),
        abstract=llm_result.get('abstract'),
        keywords=llm_result.get('keywords', []) or [],
        authors=authors,
        affiliations=affiliations,
        emails=llm_result.get('emails', []) or [],
        confidence=float(llm_result.get('confidence', 0.0) or 0.0)
    )
    return meta


def extract_first_page(pdf_path: str) -> PaperMeta:
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(extract_first_page_llm(pdf_path))
    finally:
        loop.close()


if __name__ == "__main__":
    path = "IEEE+资助论文收集测试文件/224081610535175325.pdf"
    meta = extract_first_page(path)
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
