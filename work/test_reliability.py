import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_python_ai as ai
import code_quality as quality
from command_arguments import first_argument, argument_list
from model_transport import request_chat
import pdf_source
from question_parser import split_questions
import source_storage as storage


class ExtractionTests(unittest.TestCase):
    def test_shell_fence_does_not_capture_prose(self):
        text = '```bash\npip install numpy\n```\n运行下面代码\n```python\nimport numpy as np\nprint(np.arange(3))\n```'
        code = quality.extract_python(text)
        self.assertEqual(code, 'import numpy as np\nprint(np.arange(3))\n')

    def test_unclosed_last_block_rejects_partial_success(self):
        with self.assertRaisesRegex(quality.ExtractionError, '未闭合'):
            quality.extract_python('```python\nprint(1)\n```\n```python\nprint(2')

    def test_only_non_python_code_is_not_a_program(self):
        with self.assertRaisesRegex(quality.ExtractionError, '没有 Python'):
            quality.extract_python('```bash\necho ok\n```')

    def test_tildes_and_python3_are_supported(self):
        self.assertEqual(quality.extract_python('~~~python3\nprint(42)\n~~~'), 'print(42)\n')

    def test_empty_responses_rejected(self):
        for value in ('', '  ', None):
            with self.subTest(value=value), self.assertRaises(quality.ExtractionError):
                quality.extract_python(value)


class ValidationTests(unittest.TestCase):
    def test_missing_dependency_and_opencv_import_hint(self):
        self.assertIn('缺少模块', quality.validation_error('import nonexistent_exam_library_xyz'))
        self.assertIn('import cv2', quality.validation_error('import opencv'))

    def test_shadowing_module_filename_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'turtle.py'
            self.assertIn('遮蔽', quality.validation_error('import turtle\nturtle.done()', path))
            (Path(temp) / 'numpy.py').write_text('x=1')
            self.assertIn('遮蔽', quality.validation_error('import numpy as np\nprint(np.arange(3))', Path(temp) / 'answer.py'))

    def test_sibling_module_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'exam_helpers_xyz.py').write_text('answer=42')
            self.assertIsNone(quality.validation_error('import exam_helpers_xyz\nprint(exam_helpers_xyz.answer)', Path(temp) / 'answer.py'))

    def test_optional_dependency_and_typing_guard(self):
        code = 'try:\n    import optional_exam_xyz\nexcept ImportError:\n    optional_exam_xyz = None\n'
        self.assertIsNone(quality.validation_error(code))
        code = 'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import optional_exam_xyz\n'
        self.assertIsNone(quality.validation_error(code))

    def test_placeholder_function_and_explanation_are_rejected(self):
        for code in ('def answer():\n    pass', 'def answer():\n    ...', 'raise NotImplementedError()', '"""请补充题图"""'):
            with self.subTest(code=code):
                self.assertIsNotNone(quality.validation_error(code))

    def test_legitimate_pass_and_ellipsis_are_supported(self):
        self.assertIsNone(quality.validation_error('class MyError(Exception):\n    pass\n'))
        self.assertIsNone(quality.validation_error('import numpy as np\na=np.zeros((2,2))\nprint(a[..., 0])\n'))
        self.assertIsNone(quality.validation_error('from abc import abstractmethod\n@abstractmethod\ndef draw():\n    pass\n'))


class QuestionTests(unittest.TestCase):
    def test_chinese_numbers_and_single_fourth_question(self):
        self.assertEqual([n for n, _ in split_questions('一、平方\n二、立方\n十、排序\n十一、去重')], [1, 2, 10, 11])
        self.assertEqual(split_questions('四、请导入turtle，绘制五角星'), [(4, '请导入turtle，绘制五角星')])

    def test_preserve_subquestions_without_overwrite(self):
        parsed = split_questions('1. 矩阵统计\n1) 总和\n2) 平均\n2. 排序')
        self.assertEqual([n for n, _ in parsed], [1, 2])
        self.assertIn('2) 平均', parsed[0][1])

    def test_preserve_common_constraints_and_page_continuation(self):
        parsed = split_questions('所有结果保留两位小数\n[第 1 页]\n1. 面积\n[第 2 页]\n面积公式\n2. 体积')
        self.assertTrue(all('两位小数' in body for _, body in parsed))
        self.assertIn('面积公式', parsed[0][1])

    def test_explicit_numbers(self):
        self.assertEqual([n for n, _ in split_questions('第1题：平方\n第2题：立方')], [1, 2])

    def test_ambiguous_duplicate_numbers_stop_before_overwriting(self):
        with self.assertRaisesRegex(ValueError, '题号重复'):
            split_questions('1. 第一题\n1. 子问题\n2. 第二题')

    def test_no_number_or_decimal_not_split(self):
        self.assertEqual(split_questions('输入3.14并计算面积'), [(1, '输入3.14并计算面积')])


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.payload = dict(model='qwen3:14b', messages=[dict(role='user', content='题目')])

    def respond(self, data):
        return Mock(return_value=io.BytesIO(json.dumps(data).encode()))

    def test_valid_response(self):
        self.assertEqual(request_chat('http://localhost/api/chat', self.payload, self.respond({'message': {'content': 'print(1)'}, 'done': True, 'done_reason': 'stop'})), 'print(1)')

    def test_truncated_response_rejected_even_when_python_is_valid(self):
        with self.assertRaisesRegex(RuntimeError, '长度限制'):
            request_chat('http://localhost/api/chat', self.payload, self.respond({'message': {'content': 'import turtle'}, 'done_reason': 'length'}))

    def test_empty_error_or_malformed_response(self):
        for data in ({'message': {'content': ''}}, {}, [], {'error': 'out of memory'}):
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                request_chat('http://localhost/api/chat', self.payload, self.respond(data))

    def test_bad_json_and_timeout(self):
        for opener in (Mock(return_value=io.BytesIO(b'{')), Mock(side_effect=TimeoutError())):
            with self.assertRaises(RuntimeError):
                request_chat('http://localhost/api/chat', self.payload, opener)

    def test_input_budget_does_not_silently_cut_question(self):
        self.payload['messages'][0]['content'] = '长题目' * 5000
        opener = Mock()
        with self.assertRaisesRegex(ValueError, '上下文'):
            request_chat('http://localhost/api/chat', self.payload, opener)
        opener.assert_not_called()


class StorageTests(unittest.TestCase):
    def test_each_previous_version_is_backed_up(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.py'
            storage.save_source(path, 'print(1)', None)
            storage.save_source(path, 'print(2)', path.read_bytes())
            storage.save_source(path, 'print(3)', path.read_bytes())
            self.assertEqual(path.with_suffix('.py.bak').read_text(), 'print(2)')
            archived = [x.read_text() for x in path.parent.glob('a.py.*.bak')]
            self.assertCountEqual(archived, ['print(1)', 'print(2)'])

    def test_edit_during_generation_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.py'
            path.write_text('old')
            expected = storage.snapshot(path)
            path.write_text('manual edit')
            with self.assertRaisesRegex(ValueError, '已被其他窗口修改'):
                storage.save_source(path, 'generated', expected)
            self.assertEqual(path.read_text(), 'manual edit')

    def test_replace_failure_keeps_original_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.py'
            path.write_text('original')
            with patch.object(storage.os, 'replace', side_effect=OSError('locked')):
                with self.assertRaises(OSError):
                    storage.atomic_write(path, 'new')
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual([x.name for x in path.parent.iterdir()], ['a.py'])


class BatchAndCliTests(unittest.TestCase):
    def test_failed_first_question_does_not_skip_later_questions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(ai, 'ROOT', root), patch.object(ai, 'extract_document', return_value='1. 平方\n2. 立方'), \
                 patch.object(ai, 'ask', side_effect=[RuntimeError('超时'), 'print(8)', 'print(8)']), \
                 contextlib.redirect_stdout(io.StringIO()):
                paths = pdf_source.generate_pdf_sources(ai, root / 'exam.pdf', '完成题目')
            self.assertEqual([p.name for p in paths], ['02_answer.py'])
            report = json.loads((paths[0].parent / 'validation.json').read_text())
            self.assertEqual([row['status'] for row in report], ['failed', 'saved'])

    def test_same_named_pdfs_from_other_folders_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(ai, 'ROOT', root), patch.object(ai, 'extract_document', return_value='平方'), \
                 patch.object(ai, 'ask', return_value='print(1)'), contextlib.redirect_stdout(io.StringIO()):
                first = pdf_source.generate_pdf_sources(ai, root / 'a' / 'exam.pdf', '完成题目')
                second = pdf_source.generate_pdf_sources(ai, root / 'b' / 'exam.pdf', '完成题目')
            self.assertNotEqual(first[0].parent, second[0].parent)
            self.assertTrue(first[0].exists() and second[0].exists())

    def test_command_quotes_spaces_and_backslashes(self):
        self.assertEqual(first_argument('"C:\\my folder\\a.py" 画星星'), ('C:\\my folder\\a.py', '画星星'))
        self.assertEqual(argument_list("'a b' C:\\data\\file.csv"), ['a b', 'C:\\data\\file.csv'])
        with self.assertRaisesRegex(ValueError, '未闭合'):
            first_argument('"unclosed')

    def test_check_command_detects_missing_import_without_running(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'a b.py').write_text('turtle.done()')
            output = io.StringIO()
            with patch.object(ai, 'ROOT', root), patch('builtins.input', side_effect=['/check "a b.py"', '/quit']), \
                 patch.object(ai, 'ask', side_effect=AssertionError('No model call')), contextlib.redirect_stdout(output):
                self.assertEqual(ai.main(), 0)
            self.assertIn("undefined name 'turtle'", output.getvalue())

    def test_write_command_preserves_quoted_filename_and_full_task(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ai, 'ROOT', Path(temp)), \
             patch('builtins.input', side_effect=['/生成 "绘图 答案.py" 用 turtle 画星星', '/quit']), \
             patch.object(ai, 'save_generated_file') as save, contextlib.redirect_stdout(io.StringIO()):
            ai.main()
            self.assertEqual(save.call_args.args[0].name, '绘图 答案.py')
            self.assertEqual(save.call_args.args[1], '用 turtle 画星星')

    def test_run_rejects_bad_source_before_starting_child(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'broken.py').write_text('turtle.done()')
            output = io.StringIO()
            with patch.object(ai, 'ROOT', root), patch('builtins.input', side_effect=['/run broken.py', '/quit']), \
                 patch.object(ai.subprocess, 'run') as run, contextlib.redirect_stdout(output):
                ai.main()
            run.assert_not_called()
            self.assertIn('运行前检查未通过', output.getvalue())

    def test_run_keeps_input_and_gui_stdio_attached(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'input test.py'
            path.write_text('n=int(input())\nprint(n*n)')
            with patch.object(ai, 'ROOT', root), \
                 patch('builtins.input', side_effect=['/run "input test.py" "arg with spaces"', '/quit']), \
                 patch.object(ai.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                ai.main()
            self.assertEqual(run.call_args.args[0], [sys.executable, '-u', str(path), 'arg with spaces'])
            self.assertNotIn('capture_output', run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs['cwd'], root)


if __name__ == '__main__':
    unittest.main()
