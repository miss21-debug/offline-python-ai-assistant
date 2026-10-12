"""Small command parser that preserves Windows backslashes and quoted spaces."""
import re


def first_argument(text):
    text = text.lstrip()
    if not text:
        raise ValueError('缺少文件路径')
    pairs = {'"': '"', "'": "'", '“': '”', '‘': '’'}
    if text[0] in pairs:
        end = text.find(pairs[text[0]], 1)
        if end < 0:
            raise ValueError('文件路径的引号未闭合')
        if text[end + 1:] and not text[end + 1].isspace():
            raise ValueError('带引号的路径后请加空格')
        return text[1:end], text[end + 1:].lstrip()
    match = re.match(r'\S+', text)
    return match[0], text[match.end():].lstrip()


def argument_list(text):
    args = []
    while text.strip():
        value, text = first_argument(text)
        args.append(value)
    return args
