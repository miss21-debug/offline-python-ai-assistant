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
import natural_codegen as intent

STAR = 'import turtle\npen=turtle.Turtle()\nfor i in range(5):\n    pen.forward(200)\n    pen.right(144)\nturtle.done()\n'


class NaturalCodeTests(unittest.TestCase):
    def test_library_tasks_trigger_generation(self):
        for text in ('用turtle库，并绘制五角星图案', '用numpy计算平均值', '用pandas读取CSV文件',
                     '用matplotlib绘图', '用jieba进行分词', '用wordcloud生成词云', '用opencv读取图片',
                     '生成py文件，用turtle画五角星'):
            with self.subTest(text=text):
                self.assertTrue(intent.is_coding_request(text))
                self.assertFalse(intent.is_save_followup(text))

    def test_questions_do_not_trigger_generation(self):
        for text in ('turtle是什么', '为什么numpy不能用', '如何安装pandas', '只解释turtle代码，不要生成文件'):
            self.assertFalse(intent.is_coding_request(text))
            self.assertFalse(intent.is_save_followup(text))

    def test_new_attachments_are_not_mistaken_for_save_previous(self):
        for text in ('"C:/题目.png" 保存到桌面', '"exam.pdf" 生成py文件给我', '截图 C:/题目.jpg 保存代码'):
            with self.subTest(text=text):
                self.assertFalse(intent.is_save_followup(text))

    def test_save_only_phrases(self):
        for text in ('生成py文件给我', '生成Python文件给我', '把刚才的代码保存下来', '保存为 star.py',
                     '给我py文件', '保存到桌面'):
            with self.subTest(text=text):
                self.assertTrue(intent.is_save_followup(text))

    def test_exact_screenshot_sequence_creates_star_and_does_not_regenerate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(ai, 'ROOT', root), patch('builtins.input', side_effect=[
                '用turtle库，并绘制五角星图案', '生成py文件给我', '/quit']), \
                patch.object(ai, 'ask', side_effect=[STAR, STAR]) as ask, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ai.main(), 0)
            files = list(root.glob('*.py'))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, 'turtle_star.py')
            self.assertEqual(files[0].read_text(), STAR)
            self.assertEqual(ask.call_count, 2)

    def test_chat_code_followup_saves_without_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(ai, 'ROOT', root), patch('builtins.input', side_effect=[
                '解释一下五角星写法并给示例', '生成py文件给我', '/quit']), \
                patch.object(ai, 'ask', return_value='```python\n' + STAR + '```') as ask, \
                contextlib.redirect_stdout(io.StringIO()):
                ai.main()
            self.assertEqual(ask.call_count, 1)
            self.assertEqual((root / 'generated_program.py').read_text(), STAR)

    def test_save_without_prior_code_asks_for_task(self):
        output = io.StringIO()
        with patch('builtins.input', side_effect=['生成py文件给我', '/quit']), \
             patch.object(ai, 'ask', side_effect=AssertionError('Should not generate unrelated code')), \
             contextlib.redirect_stdout(output):
            ai.main()
        self.assertIn('还没有可保存的代码', output.getvalue())

    def test_new_task_does_not_overwrite_last_program(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ai, 'ROOT', Path(temp)):
            path, _ = ai.natural_file_request('用turtle画五角星')
            path.write_text(STAR)
            other, _ = ai.natural_file_request('用turtle画五角星')
            self.assertNotEqual(path, other)

    def test_save_uses_latest_editor_contents(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ai, 'ROOT', Path(temp)):
            old = Path(temp) / 'old.py'
            old.write_text('print(42)')
            with contextlib.redirect_stdout(io.StringIO()):
                dest, code = ai.save_previous_code('保存为 new.py', 'print(1)', old)
            self.assertEqual(code, 'print(42)')
            self.assertEqual(dest.read_text(), 'print(42)')

    def test_environment_is_not_appended_to_user_request(self):
        captured = []
        def opener(request, timeout):
            captured.append(json.loads(request.data))
            return io.BytesIO(json.dumps({'message': {'content': 'ok'}}).encode())
        with patch.object(ai.urllib.request, 'urlopen', side_effect=opener):
            ai.ask('用turtle绘制五角星')
        user = captured[0]['messages'][-1]['content']
        self.assertEqual(user, '用turtle绘制五角星')
        self.assertIn('不是用户任务', captured[0]['messages'][0]['content'])


if __name__ == '__main__':
    unittest.main()
