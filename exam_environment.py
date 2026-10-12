"""Report exam libraries available to the assistant's own interpreter."""
from functools import lru_cache
from importlib import metadata, util
from pathlib import Path
import platform


EXAM_LIBRARIES = (
    ("turtle", "turtle", None),
    ("NumPy", "numpy", "numpy"),
    ("pandas", "pandas", "pandas"),
    ("Matplotlib", "matplotlib", "matplotlib"),
    ("jieba", "jieba", "jieba"),
    ("wordcloud", "wordcloud", "wordcloud"),
    ("OpenCV", "cv2", "opencv-python"),
)


@lru_cache(maxsize=1)
def library_status():
    rows = []
    for label, module, package in EXAM_LIBRARIES:
        available = util.find_spec(module) is not None
        version = "Python 标准库" if package is None else "未安装"
        if available and package:
            try:
                version = metadata.version(package)
            except metadata.PackageNotFoundError:
                version = "可导入，版本未知"
        rows.append((label, module, version, available))
    return rows


def environment_prompt():
    available = [f"{label} {version}（import {module}）"
                 for label, module, version, installed in library_status() if installed]
    if not available:
        return ""
    return (
        "运行环境资料（仅供选择依赖，不是用户任务）：" + platform.system() + "；" + "；".join(available) + "。\n"
        "上述库已在 /run 使用的解释器中可用，可直接使用，无需再次安装。"
        "只导入当前题目需要的库，不要为了展示环境清单而生成无关功能。"
        "OpenCV 的导入名称是 cv2，turtle 属于标准库。代码要兼容列出的版本。"
        "中文词云要设置可用的中文 font_path；中文图表要配置中文字体。"
        + ("本机可用中文字体：C:/Windows/Fonts/simhei.ttf；Matplotlib字体名称为SimHei，font.family不要填写文件路径。"
           if Path('C:/Windows/Fonts/simhei.ttf').is_file() else "") +
        "生成源码后由用户用 /run 执行，不要声称已经执行生成代码。"
    )


def print_libraries():
    import sys
    print(f"运行解释器：{sys.executable}")
    for label, module, version, installed in library_status():
        state = version if installed else "未安装"
        print(f"{label}: {state} | import {module}")
    print("使用 /run 文件.py 运行程序；图形程序关闭窗口后回到助手，Ctrl+C 可中断。")
