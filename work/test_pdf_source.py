import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_python_ai as ai
import pdf_source
import quality_upgrade


class PdfSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "generated"
        self.root.mkdir()
        self.source = Path(self.temp.name) / "输入 题目.PDF"
        self.source.write_bytes(b"original PDF bytes")

    def generate(self, text, responses):
        with patch.object(ai, "ROOT", self.root), \
             patch.object(ai, "extract_document", return_value=text), \
             patch.object(ai, "ask", side_effect=responses), \
             patch.object(quality_upgrade, "append_pdf", side_effect=AssertionError("PDF output is forbidden")), \
             contextlib.redirect_stdout(io.StringIO()):
            return quality_upgrade.generate_document(ai, self.source, "完成题目")

    def test_paths_and_commands(self):
        cases = [
            ('题目.pdf', self.root / '题目.pdf'),
            ('实验 题目.pdf', self.root / '实验 题目.pdf'),
            ('/文档 "实验 题目.pdf" 完成题目', self.root / '实验 题目.pdf'),
            (f'"{self.source}"', self.source),
            (f"& '{self.source}'", self.source),
            (f'/文档 "{self.source}" 完成题目', self.source),
            (f'请读取 "{self.source}" 生成源码', self.source),
            ('读取题目.pdf 完成题目', self.root / '题目.pdf'),
            ('打开题目.pdf', self.root / '题目.pdf'),
        ]
        for request, expected in cases:
            with self.subTest(request=request):
                actual, instruction = pdf_source.parse_document_request(request, self.root)
                self.assertEqual(actual, expected.resolve())
                self.assertTrue(instruction)
        self.assertIsNone(pdf_source.parse_document_request('请画一个圆', self.root))
        self.assertIsNone(pdf_source.parse_document_request('plot.py', self.root))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows absolute paths')
    def test_unquoted_absolute_path_with_spaces(self):
        request = r'请完成 C:\Downloads\期末 题目.pdf 并生成源码'
        path, instruction = pdf_source.parse_document_request(request, self.root)
        self.assertEqual(path, Path(r'C:\Downloads\期末 题目.pdf'))
        self.assertIn('生成源码', instruction)

    def test_multiple_questions_create_only_python_and_report(self):
        text = '[第 1 页]\n实验题目\n1. 输入整数输出平方。\n2. 输出固定结果。'
        code1 = 'n = int(input())\nprint(n*n)\n'
        code2 = 'print("第二题")\n'
        paths = self.generate(text, [code1, code1, code2, code2])
        self.assertEqual([p.name for p in paths], ['01_answer.py', '02_answer.py'])
        self.assertEqual(paths[0].read_text(encoding='utf-8'), code1)
        result = subprocess.run([sys.executable, str(paths[0])], input='3\n', capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), '9')
        self.assertEqual(self.source.read_bytes(), b'original PDF bytes')
        files = sorted(path.name for path in paths[0].parent.iterdir())
        self.assertEqual(files, ['01_answer.py', '02_answer.py', 'validation.json'])
        report = json.loads((paths[0].parent / 'validation.json').read_text(encoding='utf-8'))
        self.assertTrue(all(row['syntax_error'] is None and row['executed'] is False for row in report))
        self.assertFalse(list(self.root.rglob('*.pdf')))
        self.assertFalse(self.source.with_name(self.source.stem + '_AI完成.PDF').exists())

    def test_single_question_and_multiple_python_blocks(self):
        draft = '```python\ndef square(n):\n    return n*n\n```\n调用：\n```python\nprint(square(3))\n```'
        paths = self.generate('计算平方。', [draft, draft])
        code = paths[0].read_text(encoding='utf-8')
        self.assertIn('def square', code)
        self.assertIn('print(square(3))', code)
        self.assertNotIn('```', code)
        self.assertIsNone(pdf_source.source_error(code))

    def test_undefined_name_is_rejected(self):
        code = 'pen = turtle.Turtle()\nturtle.done()\n'
        self.assertIn('undefined name', pdf_source.source_error(code))
        self.assertIsNone(pdf_source.source_error('import turtle\npen = turtle.Turtle()\n'))

    def test_invalid_response_preserves_previous_source(self):
        folder = self.root / (self.source.stem + '_源码')
        folder.mkdir()
        existing = folder / '01_answer.py'
        existing.write_text('print("旧答案")\n', encoding='utf-8')
        paths = self.generate('输出结果。', ['if', 'if', 'if'])
        self.assertEqual(paths, [])
        self.assertEqual(existing.read_text(encoding='utf-8'), 'print("旧答案")\n')
        self.assertTrue((folder / '01_未通过检查.txt').is_file())
        report = json.loads((folder / 'validation.json').read_text(encoding='utf-8'))
        self.assertIsNotNone(report[0]['syntax_error'])
        self.assertIsNone(report[0]['source'])

    def test_successful_regeneration_backs_up_actual_content(self):
        paths = self.generate('输出结果。', ['print(1)', 'print(1)'])
        paths[0].write_text('print("手工修改")\n', encoding='utf-8')
        self.generate('输出结果。', ['print(2)', 'print(2)'])
        self.assertEqual(paths[0].with_suffix('.py.bak').read_text(encoding='utf-8'), 'print("手工修改")\n')

    def test_empty_scanned_pdf_does_not_create_output(self):
        with self.assertRaisesRegex(ValueError, '没有可提取'):
            self.generate('[第 1 页]\n\n[第 2 页]', [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_repair_invalid_python(self):
        paths = self.generate('输出数字。', ['if', 'if', 'print(42)'])
        self.assertEqual(paths[0].read_text(encoding='utf-8'), 'print(42)\n')

    def test_empty_or_top_level_return_is_not_valid_program(self):
        for code in ['', '# 无题目', 'return 1']:
            with self.subTest(code=code):
                self.assertIsNotNone(pdf_source.source_error(code))

    def test_cli_bare_pdf_and_document_command(self):
        for command in [f'"{self.source}"', f'/文档 "{self.source}" 完成题目']:
            with self.subTest(command=command), patch.object(ai, 'ROOT', self.root), \
                 patch('builtins.input', side_effect=[command, '/quit']), \
                 patch.object(ai, 'save_document_result') as save, \
                 patch.object(ai, 'ask', side_effect=AssertionError('Must route to PDF source generation')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ai.main(), 0)
                self.assertEqual(save.call_args.args[0], self.source.resolve())
                self.assertEqual(save.call_count, 1)


if __name__ == '__main__':
    unittest.main()
