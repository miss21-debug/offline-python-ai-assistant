# Offline Python AI Assistant · 中文离线编程助手

通过本机 Ollama 使用 Qwen 模型，支持中文编程问答、生成 Python 源文件、截图识题、文档文字处理和代码风格参考。安装模型及依赖后，模型推理不需要联网。

这是一个轻量 Python 命令行助手，VS Code 通过独立的 Continue 配置连接 Ollama。项目不是 Aider 的发行版，也不包含模型权重。

## 功能

- Qwen3 14B（质量优先）与 Qwen2.5-Coder 3B / 7B：手动选择，或按关键词和请求长度自动选择。3B 较快，7B 通常更适合复杂代码。
- 自然语言生成 `.py` 文件、修改和审查代码，覆盖时备份为 `.bak`。
- 本地截图通过 Qwen2.5-VL 3B 转写题目，再交给代码模型生成文件。
- PDF 题目直接逐题生成独立 `.py` 源码文件；Word/PPT 仍生成带回答的副本。
- 保存前检查 Python 语法和未定义名称（pyflakes），检查失败会尝试修复一次；仍失败时仅保存错误详情，保留原源码。静态检查通过不代表所有运行与逻辑问题都已排除。
- 使用通用课堂代码风格，也可参考本机的 `5.py` 和 `15.py` 两个简短示例。
- 提供机器学习和深度学习科研提示词模板。

## 安装

需要 Windows 10/11、Python 3.10+、[Ollama](https://ollama.com/)。在仓库目录执行：

```powershell
python -m pip install -r requirements.txt
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-coder:7b
ollama pull qwen3:14b
ollama pull qwen2.5vl:3b
```

7B 在 CPU 上响应较慢且需要更多内存；可只安装并固定使用 3B。截图功能需要视觉模型。首次下载需要联网。

## 启动和保存

双击 `start_local_python_ai.cmd`。脚本会启动并等待本地 Ollama 服务，然后打开中文助手。也可以在 Ollama 已运行时执行 `python local_python_ai.py`。

```text
请写一个 Python 计算器，并保存为 calculator.py
请写一个统计整数中偶数个数的程序，把代码保存到桌面，文件名叫 answer.py
"C:\Users\YOUR_USER\Pictures\question.png" 帮我把这道题的代码保存到桌面
```

默认输出到当前用户主目录下的 `OfflinePythonAI`，明确指定“桌面”时保存到桌面。程序默认生成文件，不自动执行生成的代码。

```text
/model 3b
/model 7b
/model 14b
/model auto
/fix calculator.py 修复除零错误
/review calculator.py
/check "calculator.py"
/run calculator.py
/files
/help
/quit
```

自动路由使用简单规则，可能需要手动调整；不是模型能力评测。`/run` 会执行本机代码，运行前请检查内容。

## 本地配置

将 `local-ai.config.example.json` 复制为 `local-ai.config.json`，按需修改输出目录和风格参考目录。该文件被 Git 忽略。JSON 中 Windows 反斜杠写成 `\\`，也可以使用正斜杠。

```json
{
  "output_dir": "~/OfflinePythonAI",
  "style_reference": "~/PythonStyleExamples"
}
```

也可设置环境变量 `LOCAL_AI_ROOT`、`LOCAL_AI_STYLE_REFERENCE`、`LOCAL_AI_MODEL` 或 `LOCAL_AI_MODEL_MODE`，它们优先于默认配置。旧版本的输出目录内 `local-ai-style-path.txt` 仍可使用；不指定风格目录时仅使用通用规则。项目不自动加载 `.env`。

```text
查看我的代码风格
关闭代码风格模仿
按我的代码风格写
```

风格通过提示词和少量示例引导，不是微调；题目格式和本次明确要求优先。

## VS Code

安装 [Continue](https://github.com/continuedev/continue) 和 Python 扩展。将 `work/continue-config.yaml` 合并到用户目录的 `.continue/config.yaml`（先备份已有配置），重新加载 VS Code。可手动选 3B、7B 或视觉模型。命令行的模型/风格开关不控制 Continue；编辑文件需要使用 Continue 的 Edit/Apply 功能。

## 文档与说明书

把题目 PDF 放在输出目录，输入 `/文档 题目.pdf 完成题目`，或直接粘贴/拖入 PDF 路径。助手会按题号保存到 `题目_源码` 文件夹中的 `01_answer.py`、`02_answer.py` 等文件，并生成 `validation.json`；不会生成带代码的 `_AI完成.pdf`。PDF 是扫描件、题图或文字提取不到时，需要先用截图识题。Word/PPT 仍生成带回答的副本。

- [中文新手说明书](outputs/本地Python_AI助手新手说明书.md)
- [科研提示词模板](科研研究提示词模板.md)
- 运行 `python work/create_manual_docx.py` 在桌面生成 Word 说明书。

## 验证

以下测试不需要联网或个人风格文件：

```powershell
python -m py_compile local_python_ai.py
python -m unittest discover -s work -p "test_*.py"
python work/verify_style_result.py
```

## 隐私与许可

仓库不包含个人截图、实验代码、报告、账号凭据、本机配置、模型权重或安装包。本地示例仅读取，不执行；默认请求地址为 `127.0.0.1:11434`。修改 `OLLAMA_URL` 后，请求会发送到你配置的地址。生成程序的联网行为取决于其代码。

本项目代码使用 [MIT License](LICENSE)。[Ollama](https://github.com/ollama/ollama)、Continue 和 [Qwen2.5-Coder](https://github.com/QwenLM/Qwen2.5-Coder) / [Qwen2.5-VL](https://github.com/QwenLM/Qwen2.5-VL) 各自遵循其许可证。

## 本次升级

- 自动路由：简单任务7B，复杂任务14B；启动脚本默认14B。14B需要较多显存，可用 `/model 7b` 切换。
- PDF 文档按编号逐题生成并复核，每题只保存独立 `.py` 源码和 `validation.json`，不会再把代码写回 PDF。支持一、二、第三题、1.、1）等题号；题号存在歧义时会提示整理后重试。
- 单文件生成增加第二次模型复核；语法通过不代表逻辑正确，生成代码不会自动执行。
- PDF使用Windows黑体，自动换行分页，不再按字符数截断；图片和扫描内容仍需单独转写。
- 当前便携启动入口依赖 `.venv/Scripts/python.exe` 和 `.runtime/ollama/ollama.exe`，也可在已安装Ollama的环境直接运行 `python local_python_ai.py`。
- 默认请求参数为8192上下文、温度0.1、4096输出token，Qwen3关闭思考输出。

### 导入完整性检查

模型把 import 和主体代码分成多个代码块时，所有 Python 代码块按顺序保留。PDF、截图、单文件和文档代码统一检查未定义名称，例如漏写 `import turtle`；生成的程序不会被自动执行。检查依赖 `pyflakes` 已列入 `requirements.txt`。

### 生成与保存可靠性

- 代码块按起止标记解析，忽略安装命令等非 Python 块；未闭合代码块、模型空响应和输出达到长度上限会报错，不能当作完整答案保存。
- 保存前检查语法、未定义名称、缺少依赖和未完成的函数；例如 `import opencv` 会提示实际导入名是 `cv2`。`turtle.py`、`numpy.py` 等遮蔽库的文件名会提示重命名。
- 多题 PDF 的每题状态写入 `validation.json`：`pending`、`saved`、`failed` 或 `interrupted`。某题失败后继续处理其余题；失败详情单独保存。
- 保存采用临时文件替换，并保留带时间的备份。生成期间若原文件被编辑器修改，会停止覆盖。同名但来源不同的 PDF 会使用不同输出目录。
- `/check "文件.py"` 仅执行静态检查；`/run "文件.py"` 在运行前做同样检查，程序运行后可正常接收输入或打开图形窗口。路径有空格时请加引号。

检查通过不等于所有算法和运行条件都正确。题目精度、样例、输入范围、图片内容和数据文件仍需验证；依赖探测不会执行生成代码或导入这些库，无法替代真实运行测试。

### 直接生成和保存源码

“用turtle库，并绘制五角星图案”“用numpy计算平均值”等具体任务会自动生成独立 `.py` 文件。未指定文件名时会选择可用的新文件名，避免覆盖上一题。

随后说“生成py文件给我”“把刚才代码保存下来”或“保存为 star.py”，会保存当前窗口上一段代码，不重新调用模型生成别的题目。没有上文代码时会提示先输入完整题目。`/read "文件.py"` 可以选择已有源码，`/new` 清空当前窗口代码上下文；此上下文不跨窗口重启保留。

已安装库及中文字体作为系统环境资料提供，不改变用户题目；仅使用题目需要的库。
