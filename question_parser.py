"""Recognize top-level question numbers without reusing subquestion numbers."""
import re


CHINESE = '零一二三四五六七八九十百'


def number_value(token):
    if token.isdigit():
        return int(token)
    values = {ch: n for n, ch in enumerate('零一二三四五六七八九')}
    total = current = 0
    for ch in token:
        if ch in values:
            current = values[ch]
        else:
            total += (current or 1) * {'十': 10, '百': 100}[ch]
            current = 0
    return total + current


def split_questions(text):
    text = re.sub(r'\[第 \d+ 页\]', '', text)
    pattern = re.compile(
        rf'(?m)^(?P<indent>[ \t]*)(?:第(?P<explicit>[0-9{CHINESE}]+)题[、.．:：]?|'
        rf'(?P<cn>[{CHINESE}]+)[、.．:：]|(?P<arabic>\d{{1,3}})(?P<sep>[.．、)）])(?!\d))[ \t]*')
    matches = list(pattern.finditer(text))
    if not matches:
        return [(1, text.strip())]
    def kind(match):
        if match['explicit']: return 'explicit'
        if match['cn']: return 'chinese'
        return 'dot' if match['sep'] in '.．' else 'list' if match['sep'] == '、' else 'paren'
    # A different style inside a heading belongs to that question, rather
    # than creating a second 01_answer.py that overwrites the first.
    chosen = next(group for group in ('explicit', 'chinese', 'dot', 'list', 'paren')
                  if any(kind(m) == group for m in matches))
    candidates = [m for m in matches if kind(m) == chosen]
    indent = min(len(m['indent'].expandtabs(4)) for m in candidates)
    headings = [m for m in candidates if len(m['indent'].expandtabs(4)) == indent]
    numbers = [number_value(m['explicit'] or m['cn'] or m['arabic']) for m in headings]
    if any(number < 1 for number in numbers) or any(b <= a for a, b in zip(numbers, numbers[1:])):
        raise ValueError('题号重复或顺序有歧义，不能可靠拆题；请把大题题号统一为一、二、三或1.、2.、3.')
    preamble = text[:headings[0].start()].strip()
    questions = []
    for index, match in enumerate(headings):
        body = text[match.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)].strip()
        if not body:
            raise ValueError(f'第 {numbers[index]} 题没有提取到题目内容')
        if preamble:
            body = '题目前的公共说明：\n' + preamble + '\n\n本题：\n' + body
        questions.append((numbers[index], body))
    return questions
