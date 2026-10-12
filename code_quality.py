"""Extract and statically check generated source without executing it."""
import ast
import importlib.util
import re
import sys
from pathlib import Path


class ExtractionError(ValueError):
    pass


def extract_python(text):
    if not isinstance(text, str) or not text.strip():
        raise ExtractionError("模型返回空内容")
    # Parse opening and closing fences as pairs: a shell closing fence must
    # never be mistaken for the start of an unlabelled Python block.
    blocks, current = [], []
    fence = None
    language = ""
    saw_fence = False
    for line in text.splitlines():
        marker = re.fullmatch(r"[ \t]*(`{3,}|~{3,})([^`~]*)", line)
        if fence is None:
            if marker:
                fence, language = marker.group(1), marker.group(2).strip().lower()
                current = []
                saw_fence = True
        elif marker and not marker.group(2).strip() and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
            if language in ("", "python", "py", "python3"):
                blocks.append("\n".join(current).strip())
            fence = None
        else:
            current.append(line)
    if fence is not None:
        raise ExtractionError("代码块未闭合，回答可能被截断；需要重新生成完整源码")
    if saw_fence and not blocks:
        raise ExtractionError("回答中没有 Python 代码块")
    source = "\n\n".join(block for block in blocks if block) if saw_fence else text
    return source.strip() + "\n"


def syntax_error(code):
    if not code.strip() or not any(line.strip() and not line.lstrip().startswith("#") for line in code.splitlines()):
        return "源码为空或只有注释"
    try:
        compile(code, "<生成源码>", "exec")
    except (SyntaxError, ValueError) as exc:
        return str(exc)
    tree = ast.parse(code)
    if all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
           for node in tree.body):
        return '源码只有说明字符串，没有程序实现'
    return None


def undefined_names(code):
    try:
        from pyflakes.checker import Checker
        from pyflakes.messages import UndefinedLocal, UndefinedName
    except ImportError as exc:
        raise RuntimeError("缺少代码检查依赖 pyflakes，请使用小助手的 Python 安装 requirements.txt。") from exc
    checker = Checker(ast.parse(code), filename="<生成源码>")
    errors = [message for message in checker.messages
              if isinstance(message, (UndefinedName, UndefinedLocal))]
    # Unused imports and style suggestions should not reject a runnable answer.
    return "\n".join(str(message) for message in sorted(errors, key=lambda m: (m.lineno, m.col))) or None


def dependency_errors(code, path=None):
    """Probe top-level imports only; never execute generated code or imports."""
    tree = ast.parse(code)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    modules = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        # Optional/typing-only imports are permitted to be unavailable.
        parent = parents.get(node)
        optional = False
        while parent is not None:
            if isinstance(parent, ast.Try) and any(
                handler.type is None or any(isinstance(n, ast.Name) and n.id in ("ImportError", "ModuleNotFoundError", "Exception")
                                           for n in ast.walk(handler.type)) for handler in parent.handlers
            ):
                optional = True
            if isinstance(parent, ast.If) and any(
                isinstance(n, ast.Name) and n.id == "TYPE_CHECKING" or isinstance(n, ast.Attribute) and n.attr == "TYPE_CHECKING"
                for n in ast.walk(parent.test)
            ):
                optional = True
            parent = parents.get(parent)
        if optional:
            continue
        if isinstance(node, ast.Import):
            modules.update(alias.name.split('.')[0] for alias in node.names)
        elif not node.level and node.module:
            modules.add(node.module.split('.')[0])
    errors = []
    directory = Path(path).parent if path else None
    for module in sorted(modules):
        try:
            installed = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            installed = False
        standard = module in sys.stdlib_module_names
        local = directory and ((directory / (module + '.py')).exists() or (directory / module / '__init__.py').exists())
        shadows = directory and ((Path(path).stem == module) or local) and (installed or standard)
        if shadows:
            errors.append(f"本地文件名 {module}.py 或同名目录会遮蔽已安装的 {module} 模块，请重命名")
        elif not installed and not standard and not local:
            hint = "；OpenCV 应写 import cv2" if module in ("opencv", "opencv_python") else ""
            errors.append(f"当前 Python 环境缺少模块 {module}{hint}")
    return "\n".join(errors) or None


def validation_error(code, path=None):
    return syntax_error(code) or undefined_names(code) or incomplete_implementation(code) or dependency_errors(code, path)


def incomplete_implementation(code):
    tree = ast.parse(code)
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                body = body[1:]
            # Abstract methods intentionally omit implementation.
            if any(isinstance(d, ast.Name) and d.id == 'abstractmethod' or isinstance(d, ast.Attribute) and d.attr == 'abstractmethod'
                   for d in node.decorator_list):
                continue
            if body and all(isinstance(item, ast.Pass) or
                            isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and item.value.value is Ellipsis
                            for item in body):
                errors.append(f'函数 {node.name} 仅有 pass 或省略号，缺少实现')
        if isinstance(node, ast.Raise):
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(target, ast.Name) and target.id == 'NotImplementedError':
                errors.append(f'第 {node.lineno} 行仍抛出 NotImplementedError，程序尚未完成')
    return '\n'.join(errors) or None
