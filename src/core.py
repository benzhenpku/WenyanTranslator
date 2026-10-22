#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心翻译逻辑：提示词构造、接口地址规范化、HTTP 调用与响应解析。"""

import json
import urllib.error
import urllib.request


STYLES = {
    "浅易文言": "贴近现代语感，清楚易懂，少用生僻字。",
    "典雅文言": "措辞雅洁，结构工整，略带古典韵致。",
    "庄重文言": "语气庄重，句法谨严，适合正式场合。",
    "艰深古奥": "极度仿古，风格晦涩，使用生僻字、古字、异体字和艰深典故，追求先秦两汉到六朝古文的艰涩气韵；但仍需保持句子结构可断读，不使用现代汉语词汇。",
}

SYSTEM_PROMPT = """你是一名精通古今汉语转换的中文编辑。你的唯一任务是把用户提供的现代汉语翻译成流畅自然的文言文。
要求：
1. 只返回译文，不要返回原文、解释、注释、标题、引号、代码块或任何多余前缀。
2. 保留人名、地名、书名、数字、引号、标点等关键信息；专有名词不要随意意译。
3. 保留原文的分段与换行结构，不要合并或重排段落。
4. 根据用户指定的文风调整表达。
5. 对难以直译的现代概念，选择贴合语境的文言表达，必要时可保留原词或用约定俗成的音译。
"""


class TranslationError(Exception):
    """翻译过程中可向用户解释的错误。"""
    pass


def normalize_endpoint(api_url):
    """将用户输入的接口地址补全为完整的 Chat Completions 地址。"""
    api_url = api_url.strip().rstrip("/")
    if api_url.endswith("/chat/completions"):
        return api_url
    return api_url + "/chat/completions"


def request_translation(api_url, model, api_key, style, requirements, source_text):
    """调用 OpenAI 兼容接口完成翻译，返回译文字符串。"""
    endpoint = normalize_endpoint(api_url)
    style_description = STYLES[style]

    user_prompt = f"""文风：{style}
文风说明：{style_description}
补充要求：{requirements or "无"}

现代文原文：
<original_text>
{source_text}
</original_text>
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "stream": False,
        "reasoning_effort": "high",
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8")
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", error_body)
        except Exception:
            error_message = ""
        raise TranslationError(f"HTTP {exc.code}：{error_message or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise TranslationError("无法连接接口，请检查网络或接口地址。") from exc
    except TimeoutError as exc:
        raise TranslationError("请求超时，请稍后重试。") from exc

    try:
        response_data = json.loads(response_body)
        content = response_data["choices"][0]["message"]["content"].strip()
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise TranslationError("接口返回格式不正确。") from exc

    if not content:
        raise TranslationError("接口返回了空译文。")

    return content
