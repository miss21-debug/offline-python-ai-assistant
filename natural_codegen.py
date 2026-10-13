"""Recognize concrete coding requests and save-only follow-ups locally."""
import re
from pathlib import Path
from assistant_knowledge import drawing_entry

LIBRARIES = r'(?<![A-Za-z0-9_])(?:turtle|numpy|pandas|matplotlib|jieba|wordcloud|opencv|cv2|python)(?![A-Za-z0-9_])'
ACTION = r'绘制|绘图|画|生成|计算|统计|读取|处理|分析|分词|排序|识别|转换|实现|写|编写|创建|保存|输出'
QUESTION = r'为什么|为何|什么|怎么|怎样|如何|解释|介绍|区别|能不能|可以吗|為什麼|什麼|怎麼|怎樣|解釋|介紹'
FILE_NAME = r'(?:[A-Za-z0-9_\-\u4e00-\u9fff]+\.py)'


def is_drawing_request(text):
    return bool(re.search(r'绘制|绘图|画|繪製|繪圖|畫|\bdraw\b', text, re.I) and drawing_entry(text))


def named_file(text):
    quoted = re.search(r'["“\x27]([^"”\x27\r\n]+\.py)["”\x27]', text, re.I)
    if quoted:
        return quoted[1]
    explicit = re.search(r'(?:保存为|另存为|命名为|文件名(?:叫|为|是)?|叫作)\s*(' + FILE_NAME + r')', text, re.I)
    if explicit:
        return explicit[1]
    match = re.search(r'(?<![\w])(' + FILE_NAME + r')(?![\w])', text, re.I)
    return match[1] if match else None


def is_save_followup(text):
    """A request to save previous code must never become a fresh model prompt."""
    compact = text.lower().strip()
    if re.search(r'\.(?:pdf|docx|pptx|png|jpe?g|webp)\b', compact):
        return False
    if re.search(r'不要(?:生成|保存)|只(?:解释|说明)|' + QUESTION, compact):
        return False
    # Remove file destinations so a quoted name is not mistaken for a task.
    compact = re.sub(r'["“\x27][^"”\x27]+["”\x27]', '', compact)
    compact = re.sub(FILE_NAME, '', compact, flags=re.I)
    has_save = re.search(r'保存|存到|放到|写入|生成.*(?:py|python|源码|代码).*文件|给我.*(?:py|python|源码).*文件', compact)
    if not has_save:
        return False
    if is_drawing_request(compact):
        return False
    if re.search(r'写一个|写一份|帮我写|请写|编写|实现|创建|开发', compact):
        return False
    # A full task such as "保存用turtle画星星的代码" still needs generation.
    if re.search(LIBRARIES + r'\s*库?', compact, re.I) and re.search(r'绘制|绘图|画|计算|统计|分词|排序|实现', compact):
        return False
    if re.search(r'绘制|绘图|计算|统计|分词|排序|计算器|五角星|词云', compact):
        return False
    return True


def is_coding_request(text):
    if re.search(r'不要(?:生成|保存)|只(?:解释|说明)|' + QUESTION, text, re.I):
        return False
    if is_drawing_request(text):
        return True
    if re.search(LIBRARIES, text, re.I) and re.search(ACTION, text):
        return True
    return bool(re.search(r'写|编写|生成|创建|实现|开发|保存|存到', text) and
                re.search(r'代码|源码|程序|脚本|(?:python|py)\s*文件|\.py', text, re.I))


def new_default_path(root, task):
    lower = task.lower()
    drawing = drawing_entry(task)
    if drawing and drawing.filename and not ('turtle' in lower and re.search('五角星|星星', task)):
        stem = Path(drawing.filename).stem
    elif 'turtle' in lower:
        stem = 'turtle_star' if re.search('五角星|星星', task) else 'turtle_drawing'
    else:
        module = re.search(LIBRARIES, lower)
        stem = (module[0] + '_example') if module and module[0] != 'python' else 'generated_program'
    path = Path(root) / (stem + '.py')
    index = 2
    while path.exists():
        path = Path(root) / f'{stem}_{index}.py'
        index += 1
    return path
