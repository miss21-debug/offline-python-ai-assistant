import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import code_quality as quality
import local_python_ai as ai
import pdf_source
import quality_upgrade


MISSING = 'pen = turtle.Turtle()\npen.forward(200)\nturtle.done()\n'
VALID = 'import turtle\n' + MISSING
BLOCKS = '先导入库：\n```python\nimport turtle\n```\n再绘图：\n```python\n' + MISSING + '```'


class CodeQualityTests(unittest.TestCase):
    def test_split_import_block_is_preserved_in_all_extractors(self):
        for extract in (quality.extract_python, ai.code_only, pdf_source.source_code):
            with self.subTest(extract=extract):
                code = extract(BLOCKS)
                self.assertTrue(code.startswith('import turtle\n'))
                self.assertIn('pen = turtle.Turtle()', code)
                self.assertIsNone(quality.validation_error(code))

    def test_compile_alone_accepts_missing_import_checker_rejects_it(self):
        compile(MISSING, '<fixture>', 'exec')
        self.assertIn("undefined name 'turtle'", quality.validation_error(MISSING))
        self.assertIsNone(quality.validation_error(VALID))

    def test_aliases_and_local_names(self):
        self.assertIn("undefined name 'np'", quality.validation_error('print(np.zeros(3))'))
        code = 'import numpy as np\nprint(np.zeros(3))\n'
        self.assertIsNone(quality.validation_error(code))
        self.assertIsNone(quality.validation_error('def draw(turtle):\n    turtle.forward(30)\n'))
        self.assertIsNone(quality.validation_error('from turtle import Turtle\npen = Turtle()\n'))

    def test_unused_import_and_literal_names_are_not_errors(self):
        self.assertIsNone(quality.validation_error('import turtle\nprint("turtle")\n'))
        self.assertIsNone(quality.validation_error('print("turtle.forward(20)")\n'))

    def test_checks_do_not_execute_the_code(self):
        code = 'raise RuntimeError("should not run")\n'
        self.assertIsNone(quality.validation_error(code))

    def test_missing_checker_cannot_be_reported_as_pass(self):
        with patch.dict(sys.modules, {'pyflakes.checker': None}):
            with self.assertRaisesRegex(RuntimeError, 'pyflakes'):
                quality.validation_error('print(1)')

    def test_single_file_repair_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'star.py'
            path.write_text('print("original")\n', encoding='utf-8')
            with patch.object(ai, 'ROOT', Path(temp)), \
                 patch.object(ai, 'ask', side_effect=[MISSING, MISSING, VALID]) as ask, \
                 contextlib.redirect_stdout(io.StringIO()):
                ai.save_generated_file(path, '用turtle绘制五角星')
            self.assertEqual(ask.call_count, 3)
            self.assertIn("undefined name 'turtle'", ask.call_args.args[0])
            self.assertEqual(path.read_text(encoding='utf-8'), VALID)
            self.assertEqual(path.with_suffix('.py.bak').read_text(encoding='utf-8'), 'print("original")\n')

    def test_bad_repair_does_not_overwrite_or_create_source(self):
        for exists in (True, False):
            with self.subTest(exists=exists), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'star.py'
                if exists:
                    path.write_text('print(1)\n', encoding='utf-8')
                with patch.object(ai, 'ROOT', Path(temp)), \
                     patch.object(ai, 'ask', side_effect=[MISSING] * 3):
                    with self.assertRaisesRegex(ValueError, '未生成或覆盖'):
                        ai.save_generated_file(path, '绘图')
                self.assertEqual(path.exists(), exists)
                if exists:
                    self.assertEqual(path.read_text(), 'print(1)\n')
                self.assertTrue(path.with_suffix('.py.failed.txt').exists())

    def test_pdf_missing_import_goes_through_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'question.pdf'
            with patch.object(ai, 'ROOT', root), \
                 patch.object(ai, 'extract_document', return_value='用turtle绘制五角星'), \
                 patch.object(ai, 'ask', side_effect=[MISSING, MISSING, VALID]), \
                 contextlib.redirect_stdout(io.StringIO()):
                saved = pdf_source.generate_pdf_sources(ai, source, '完成题目')
            self.assertEqual(saved[0].read_text(), VALID)
            report = json.loads((saved[0].parent / 'validation.json').read_text())
            self.assertIsNone(report[0]['validation_error'])
            self.assertFalse(report[0]['executed'])

    def test_document_invalid_import_never_saved_as_python(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'question.docx'
            with patch.object(ai, 'ROOT', root), \
                 patch.object(ai, 'extract_document', return_value='用turtle绘制五角星'), \
                 patch.object(ai, 'ask', side_effect=[MISSING] * 3), \
                 patch.object(ai, 'append_docx_result') as export, \
                 contextlib.redirect_stdout(io.StringIO()):
                quality_upgrade.generate_document(ai, source, '完成题目')
            folder = root / 'question_AI完成'
            self.assertFalse((folder / '01_answer.py').exists())
            report = json.loads((folder / 'validation.json').read_text())
            self.assertIsNone(report[0]['syntax_error'])
            self.assertIn('turtle', report[0]['validation_error'])
            self.assertNotIn('```python', export.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
