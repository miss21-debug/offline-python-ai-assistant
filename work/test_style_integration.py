import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_python_ai as ai


class StyleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.reference = tempfile.TemporaryDirectory()
        self.addCleanup(self.reference.cleanup)
        sample_dir = Path(self.reference.name)
        (sample_dir / "5.py").write_text('number = int(input("请输入整数："))\nprint(number)\n', encoding="utf-8")
        (sample_dir / "15.py").write_text('#统计总和\ntotal = 0\nfor number in range(5):\n    total += number\nprint(total)\n', encoding="utf-8")
        reference_patch = patch.object(ai, "STYLE_REFERENCE", sample_dir)
        reference_patch.start()
        self.addCleanup(reference_patch.stop)
        self.calls = []
        self.mode = ai.MODEL_MODE
        self.enabled = ai.STYLE_ENABLED
        ai.MODEL_MODE = "auto"
        ai.STYLE_ENABLED = True

    def tearDown(self):
        ai.MODEL_MODE = self.mode
        ai.STYLE_ENABLED = self.enabled

    def response(self, request, timeout):
        self.calls.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"message": {"content": 'print("你好")'}}).encode())

    def test_style_does_not_change_routing(self):
        with patch.object(ai.urllib.request, "urlopen", side_effect=self.response):
            ai.ask("写一个统计偶数的程序", style_examples=True)
            ai.ask("写 PyTorch 训练代码", style_examples=True)
            ai.MODEL_MODE = "7b"
            ai.ask("打印你好", style_examples=True)
        self.assertEqual([c["model"] for c in self.calls],
                         [ai.MODEL_NAMES["7b"], ai.MODEL_NAMES["14b"], ai.MODEL_NAMES["7b"]])
        for call in self.calls:
            system = call["messages"][0]["content"]
            self.assertIn("<style_examples>", system)
            self.assertIn("输入输出格式优先", system)
            self.assertIn("main()", system)
            self.assertLess(len(system), 2200)

    def test_controls_and_missing_examples(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(ai.handle_style_request("关闭代码风格模仿"))
        self.assertEqual(ai.style_instructions(True), "")
        with patch.object(ai.urllib.request, "urlopen", side_effect=self.response):
            ai.ask("打印你好", style_examples=True)
        self.assertEqual(self.calls[0]["messages"][-1]["content"], "打印你好")
        self.assertNotIn("用户偏好的 Python 代码风格", self.calls[0]["messages"][0]["content"])
        self.assertIn("不是用户任务", self.calls[0]["messages"][0]["content"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(ai.handle_style_request("按我的代码风格写"))
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(ai, "STYLE_REFERENCE", Path(temp) / "missing"):
                self.assertIn("英文 snake_case", ai.style_instructions(True))
                self.assertNotIn("<style_examples>", ai.style_instructions(True))
        self.assertFalse(ai.handle_style_request("按我的代码风格写一个统计程序"))

    def test_natural_save_and_repair_both_receive_style(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = 'print("旧文件")\n'
            path = root / "style_check.py"
            path.write_text(original, encoding="utf-8")
            answers = iter(['print("缺少括号"', 'print("你好")\n'])

            def response(request, timeout):
                self.calls.append(json.loads(request.data))
                return io.BytesIO(json.dumps({"message": {"content": next(answers)}}).encode())

            with patch.object(ai, "ROOT", root), patch.object(ai.urllib.request, "urlopen", side_effect=response):
                request = ai.natural_file_request("请按我的风格写一个 Python 问候程序，保存为 style_check.py")
                self.assertEqual(request[0], path)
                with contextlib.redirect_stdout(io.StringIO()):
                    ai.save_generated_file(*request, old=original)
                self.assertIsNone(ai.syntax_error(path))
            self.assertEqual(path.with_suffix(".py.bak").read_text(encoding="utf-8"), original)
            self.assertEqual(len(self.calls), 2)
            for call in self.calls:
                self.assertIn("<style_examples>", call["messages"][0]["content"])
                self.assertNotIn(str(root), call["messages"][0]["content"])
            self.assertIn("你好", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
