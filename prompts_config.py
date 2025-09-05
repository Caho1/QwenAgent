#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示词配置文件
为每个模式单独定义LLM提示词，便于针对性调整
"""

class PromptsConfig:
    """各模式的提示词配置"""

    # 基础通用提示词模板
    BASE_PROMPT = """你是一个专业的学术论文信息提取专家。请从以下PDF第一页的文本内容中提取论文的元数据信息。

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

以下是PDF第一页的文本内容：
{text_content}"""

    # SN模式专用提示词
    SN_PROMPT = """你是一个专业的学术论文信息提取专家，专门为SN期刊信息收集进行优化。请从以下PDF第一页的文本内容中提取论文的元数据信息。

特别注意SN模式的要求：
1. 准确识别前5位作者及其单位信息
2. 精确定位通讯作者（通常标有*或corresponding author标记）
3. 提取通讯作者的邮箱地址
4. 标题可能需要分离主标题和副标题

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

注意：
- 作者顺序必须与视觉阅读顺序一致：行从上到下，行内从左到右
- 重点关注通讯作者的识别和邮箱提取
- 单位信息要完整准确

以下是PDF第一页的文本内容：
{text_content}"""

    # IEEE模式专用提示词
    IEEE_PROMPT = """你是一个专业的学术论文信息提取专家，专门为IEEE期刊信息收集进行优化。请从以下PDF第一页的文本内容中提取论文的元数据信息。

特别注意IEEE模式的要求：
1. 提取完整的英文标题（可能包含主标题和副标题）
2. 收集所有作者姓名，合并为一个字符串
3. 重点关注第一作者的邮箱地址
4. IEEE论文通常有标准的格式，注意识别

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

注意：
- 作者顺序必须与视觉阅读顺序一致：行从上到下，行内从左到右
- 重点关注第一作者邮箱的准确提取
- 标题要完整，包含可能的副标题

以下是PDF第一页的文本内容：
{text_content}"""

    # 资助信息模式专用提示词
    FUNDING_PROMPT = """你是一个专业的学术论文信息提取专家，专门为资助信息提取进行优化。请从以下PDF第一页的文本内容中提取论文的元数据信息。

特别注意资助信息模式的要求：
1. 提取完整的英文论文标题
2. 准确识别第一作者和通讯作者的姓名、单位
3. 重点关注通讯作者的邮箱地址
4. 提取关键词和摘要信息
5. 特别注意致谢信息（Acknowledgments），其中通常包含资助信息

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

注意：
- 作者顺序必须与视觉阅读顺序一致：行从上到下，行内从左到右
- 重点关注第一作者和通讯作者的单位信息
- 通讯作者邮箱要准确提取
- 关键词和摘要要完整

以下是PDF第一页的文本内容：
{text_content}"""

    # AP模式专用提示词
    AP_PROMPT = """你是一个专业的学术论文信息提取专家，专门为AP信息表收集进行优化。请从以下PDF第一页的文本内容中提取论文的元数据信息。

特别注意AP模式的要求：
1. 提取完整的论文标题（中文或英文）
2. 准确识别第一作者和通讯作者：
   - 第一作者：作者列表的第一位为第一作者，标记为 order=1。
   - 通讯作者：一般在姓名后带有“*”或其他角标标识，有时在文末注明“Corresponding author”或“通讯作者”，请优先根据这些规则判断。
   - 作者姓名输出时不应包含任何角标符号（如 *, ¹, ², a, b, a*等），只保留纯净的姓名，根据邮箱判断当前的角标是“a”还是“a*”，如邮箱为a*2338745276@qq.com，则角标应该为a*，同样的如果是b23387845276@qq.com的类似邮箱，则角标应该是b。
   - **角标识别增强规则**：
     * 文本中可能出现 [SUPERSCRIPT:a*] 这样的标记，表示独立的角标，不应包含在姓名中
     * 区分独立角标和嵌入姓名的字符：
       - "Xinquan Yuan [SUPERSCRIPT:a*]" → 姓名是 "Xinquan Yuan"，a*是独立角标
       - "Xinquan Yuana*" → 如果a*直接连在姓名后，需要判断是否为姓名的一部分
     * 优先识别独立的角标标记，避免将角标字符误认为姓名的一部分
3. 提取完整的关键词列表
4. 提取完整的摘要内容
5. 作者姓名保持完整，不需要分离姓和名
6. 提取所有作者的姓名，用于生成全部作者姓名字段

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

额外规则：
- **重要**：作者顺序必须严格按照文档中的出现顺序，不要重新排列！
- 作者顺序必须与视觉阅读顺序一致：行从上到下，行内从左到右
- 第一作者是作者列表中的第一个，必须标记 is_first_author=true
- 例如：如果文档中作者顺序是"A, B, C, D"，那么A的order=1，B的order=2，C的order=3，D的order=4
- 关键词要完整提取，包括可能的缩写（如 "Gp"、"LLM" 等）
- 摘要要完整准确
- 若未在文中出现 "Keyword"/"Keywords"，则关键词留空
- 邮箱要与对应的作者匹配，如果无法匹配则统一放入 "emails" 列表

以下是PDF第一页的文本内容：
{text_content}"""


    @classmethod
    def get_prompt_for_mode(cls, mode: str) -> str:
        """根据模式获取对应的提示词"""
        mode_prompts = {
            'sn': cls.SN_PROMPT,
            'ieee': cls.IEEE_PROMPT,
            'funding': cls.FUNDING_PROMPT,
            'ap': cls.AP_PROMPT
        }

        return mode_prompts.get(mode, cls.BASE_PROMPT)

    @classmethod
    def get_all_modes(cls) -> list:
        """获取所有支持的模式"""
        return ['sn', 'ieee', 'funding', 'ap']

    @classmethod
    def get_mode_description(cls, mode: str) -> str:
        """获取模式描述"""
        descriptions = {
            'sn': 'SN信息表收集 - 专注于前5位作者信息和通讯作者邮箱',
            'ieee': 'IEEE信息表收集 - 专注于标题处理和第一作者邮箱',
            'funding': '资助信息提取 - 专注于作者单位和致谢信息',
            'ap': 'AP信息表收集 - 专注于完整姓名和关键词摘要'
        }
        return descriptions.get(mode, '未知模式')
