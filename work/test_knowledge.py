import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistant_knowledge as knowledge
import local_python_ai as ai
import natural_codegen as intent
from generation_pipeline import generate_checked_source
import pdf_source


class KnowledgeTests(unittest.TestCase):
    def test_rings_aliases_and_color_layout(self):
        for query in ('画奥运五环', '画奥运五坏', '奧運五環是什麼樣子', 'draw OLYMPIC RINGS'):
            entries = knowledge.search_entries(query)
            self.assertEqual(entries[0].filename, 'olympic_rings.py')
            notes = knowledge.reference_notes(query)
            for fact in ('上排为蓝、黑、红', '下排为黄、绿', '空心', '交替', '五种颜色不各自固定代表某个大洲'):
                self.assertIn(fact, notes)

    def test_no_unrelated_matches_or_partial_english_words(self):
        for query in ('求三个数的最大值', 'turtleish', 'mypandashelper', 'superopencv'):
            self.assertEqual(knowledge.reference_notes(query), '')
        self.assertTrue(knowledge.reference_notes('用TURTLE库画圆'))
        self.assertNotIn('奥运五环', knowledge.reference_notes('用turtle画圆'))

    def test_prompt_budget_keeps_complete_entries(self):
        text = knowledge.reference_notes('奥运五环 turtle numpy pandas matplotlib jieba wordcloud cv2')
        self.assertLessEqual(len(text), knowledge.PROMPT_LIMIT)
        self.assertEqual(len(text.splitlines()[2:]), 3)
        for line in text.splitlines()[2:]:
            row = json.loads(line)
            self.assertTrue(row['content'])
        self.assertEqual(knowledge.reference_notes('奥运五环', limit=20), '')

    def test_edited_knowledge_reloads_and_bad_entries_do_not_block_valid_ones(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'custom.json'
            row = dict(title='自定义图案', keywords=['测试图案'], content='三个圆')
            path.write_text(json.dumps([row]), encoding='utf-8-sig')
            self.assertIn('三个圆', knowledge.reference_notes('测试图案', root))
            row['content'] = '四个圆'
            path.write_text(json.dumps([row, {}, dict(row, filename='../bad.py')]), encoding='utf-8')
            (root / 'broken.json').write_text('{')
            (root / 'large.json').write_bytes(b' ' * (knowledge.MAX_FILE_BYTES + 1))
            with self.assertWarns(UserWarning):
                entries = knowledge.search_entries('测试图案', root)
            self.assertEqual([entry.content for entry in entries], ['四个圆'])

    def test_task_scope_ignores_candidate_topics_and_resets_on_error(self):
        with self.assertRaises(RuntimeError):
            with knowledge.task_knowledge('求整数之和'):
                self.assertEqual(knowledge.knowledge_for_prompt('候选代码里写奥运五环'), '')
                raise RuntimeError('interrupted')
        self.assertIn('奥运五环', knowledge.knowledge_for_prompt('奥运五环'))

    def test_chat_and_explicit_variant_keep_the_original_request(self):
        with patch.object(ai, 'request_chat', return_value='回答') as request:
            ai.ask('奥运五环的颜色是什么')
            self.assertIn('上排为蓝、黑、红', request.call_args.args[1]['messages'][0]['content'])
            ai.ask('用matplotlib把奥运五环全改为紫色')
        messages = request.call_args.args[1]['messages']
        self.assertEqual(messages[-1]['content'], '用matplotlib把奥运五环全改为紫色')
        self.assertIn('当前题目的明确变体要求优先', messages[0]['content'])

    def test_local_extension_adds_a_new_drawable_object(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'custom.json').write_text(json.dumps([dict(title='等边三角形', keywords=['等边三角形'],
                content='三边相等', kind='drawing', filename='triangle.py')]), encoding='utf-8')
            with patch.object(knowledge, 'KNOWLEDGE_DIR', root):
                self.assertTrue(intent.is_coding_request('画等边三角形'))
                self.assertEqual(intent.new_default_path(root, '画等边三角形').name, 'triangle.py')

    def test_same_original_task_facts_reach_draft_review_and_repair(self):
        calls = []
        answers = iter(['# 美国队长盾牌\nprint(missing)', 'print(missing)', 'print(5)'])
        def request(url, payload, opener):
            calls.append(payload)
            return next(answers)
        with patch.object(ai, 'request_chat', side_effect=request):
            code = generate_checked_source(ai.ask, '用turtle画奥运五坏', '用turtle画奥运五坏', '', Path('rings.py'))
        self.assertEqual(code.strip(), 'print(5)')
        self.assertEqual(len(calls), 3)
        for call in calls:
            system = call['messages'][0]['content']
            self.assertIn('上排为蓝、黑、红', system)
            self.assertIn('turtle 圆心', system)
            self.assertNotIn('经典圆盾', system)
        self.assertEqual(calls[0]['messages'][-1]['content'], '用turtle画奥运五坏')

    def test_pdf_generation_retrieves_question_facts(self):
        calls = []
        def request(url, payload, opener):
            calls.append(payload)
            return 'print(5)'
        with tempfile.TemporaryDirectory() as temp, patch.object(ai, 'ROOT', Path(temp)), \
             patch.object(ai, 'extract_document', return_value='1. 用matplotlib绘制奥运五环'), \
             patch.object(ai, 'request_chat', side_effect=request), contextlib.redirect_stdout(io.StringIO()):
            saved = pdf_source.generate_pdf_sources(ai, Path(temp) / 'exam.pdf', '完成题目')
            self.assertEqual(len(saved), 1)
        for call in calls:
            self.assertIn('上排为蓝、黑、红', call['messages'][0]['content'])

    def test_knowledge_command_needs_no_model(self):
        output = io.StringIO()
        with patch('builtins.input', side_effect=['/知识库', '/knowledge 奥运五坏', '/知识库 不存在的条目', '/quit']), \
             patch.object(ai, 'ask', side_effect=AssertionError('no model call')), contextlib.redirect_stdout(output):
            ai.main()
        self.assertIn('上排为蓝、黑、红', output.getvalue())
        self.assertIn('没有匹配的本地条目', output.getvalue())

    def test_drawing_tasks_save_but_factual_questions_do_not(self):
        for text in ('画一个奥运五环', '让他调用库去画一个奥运五坏', '用turtle画奥运五环，生成py文件给我',
                     '畫一個奧運五環', 'draw olympic rings', '画一个红绿灯'):
            self.assertTrue(intent.is_coding_request(text), text)
            self.assertFalse(intent.is_save_followup(text), text)
        for text in ('奥运五环是什么样子', '怎么画奥运五环', '解释奥运五环怎么画', '奧運五環是什麼樣子', '只解释，不要生成'):
            self.assertFalse(intent.is_coding_request(text), text)
        self.assertTrue(intent.is_save_followup('生成py文件给我'))
        with tempfile.TemporaryDirectory() as temp:
            first = intent.new_default_path(temp, '画奥运五坏')
            first.write_text('print(5)')
            self.assertEqual(first.name, 'olympic_rings.py')
            self.assertEqual(intent.new_default_path(temp, '画奥运五环').name, 'olympic_rings_2.py')

    def test_new_drawing_with_save_request_does_not_save_previous_code(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ai, 'ROOT', Path(temp)), \
             patch('builtins.input', side_effect=['画奥运五坏，生成py文件给我', '/quit']), \
             patch.object(ai, 'ask', return_value='print(5)') as ask, contextlib.redirect_stdout(io.StringIO()):
            ai.main()
            self.assertTrue((Path(temp) / 'olympic_rings.py').exists())
            self.assertEqual(ask.call_count, 2)


if __name__ == '__main__':
    unittest.main()
