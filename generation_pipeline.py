"""Use one validation and repair path for images, PDFs and individual files."""
from code_quality import ExtractionError, extract_python, validation_error
from assistant_knowledge import task_knowledge


class GenerationError(ValueError):
    def __init__(self, error, code=''):
        super().__init__(error)
        self.code = code


def generate_checked_source(ask, prompt, task, system, path):
    # Match only the original task: candidate code cannot add unrelated topics.
    with task_knowledge(task):
        return _generate_checked_source(ask, prompt, task, system, path)


def _generate_checked_source(ask, prompt, task, system, path):
    draft = ask(prompt, system)
    response = ask(
        '逐条复核题目约束、算法、输入输出、边界和依赖。结合本地参考核对图案的颜色、数量、位置和相扣关系。补齐import、函数实现和所需调用入口。'
        '只输出一个完整Python程序，不要给多个替代版本，不要声称已经运行。\n'
        f'题目：{task}\n候选答案：\n{draft}', system)
    for attempt in range(2):
        try:
            code = extract_python(response)
            error = validation_error(code, path)
        except ExtractionError as exc:
            code, error = response, str(exc)
        if not error:
            return code
        if attempt == 0:
            response = ask(
                f'修复下面检查发现的问题，满足题目要求。必须返回完整Python源码，包括所有import；'
                f'不能只给出补丁或未完成的代码。\n题目：{task}\n检查结果：{error}\n候选源码：\n{code}', system)
    raise GenerationError(error, code)
