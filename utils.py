"""
公共工具函数模块
提供 safe_truncate 等通用函数，消除多处重复定义
"""
import re


def safe_truncate(text, max_chars):
    """安全截断：在句号处断开，避免切断中文句子"""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    truncated = text[-max_chars:]
    for sep in ["。", "！", "？", ".", "!", "?", "\n"]:
        pos = truncated.find(sep)
        if 0 < pos < len(truncated) - 1:
            return truncated[pos + 1:].strip()
    return truncated


def tokenize_chinese(text):
    """中文分词：按中文标点、空格、英文单词边界分割为词组
    
    返回词列表，用于记忆检索的 Relevance 计算。
    避免 set(text) 按字符拆分导致 Relevance 几乎始终为 0 的问题。
    """
    if not text:
        return []
    
    tokens = []
    current = []
    
    for ch in text:
        if ch in "，。！？；：""''（）【】《》\n\r\t \-/\\,.;:!?\"'()[]{}":
            if current:
                tokens.append("".join(current))
                current = []
            tokens.append(ch)
        elif ch.isspace():
            if current:
                tokens.append("".join(current))
                current = []
        elif '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            if current:
                has_non_cjk = any(not ('\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf') for c in current)
                if has_non_cjk:
                    tokens.append("".join(current))
                    current = []
            current.append(ch)
        else:
            if current:
                all_cjk = all('\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf' for c in current)
                if all_cjk:
                    tokens.append("".join(current))
                    current = []
            current.append(ch)
    if current:
        tokens.append("".join(current))
    
    return [t for t in tokens if t.strip()]