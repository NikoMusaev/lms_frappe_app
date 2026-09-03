# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import json

from frappe.tests import UnitTestCase

from lms_frappe_app.agent_learning.normalizer import нормализовать


def editorjs(*блоки) -> str:
	return json.dumps({"blocks": list(блоки)})


class TestNormalizer(UnitTestCase):
	"""Нормализатор: оба формата урока, медиа, сегменты, устойчивость."""

	def нормализовать_блоки(self, *блоки, **kwargs):
		return нормализовать(title="Урок", content=editorjs(*блоки), **kwargs)

	# --- EditorJS ---

	def test_заголовок_и_абзац_превращаются_в_markdown(self):
		урок = self.нормализовать_блоки(
			{"type": "header", "data": {"text": "Циклы", "level": 2}},
			{"type": "paragraph", "data": {"text": "Цикл повторяет действие."}},
		)
		self.assertEqual(урок.сегмент(1), "## Циклы\n\nЦикл повторяет действие.")

	def test_разметка_внутри_абзаца_убирается(self):
		# EditorJS хранит текст с html-тегами; агенту нужен чистый текст.
		урок = self.нормализовать_блоки(
			{"type": "paragraph", "data": {"text": "Это <b>важно</b> помнить"}}
		)
		self.assertEqual(урок.сегмент(1), "Это важно помнить")

	def test_списки_нумерованный_и_маркированный(self):
		урок = self.нормализовать_блоки(
			{"type": "list", "data": {"style": "ordered", "items": ["раз", "два"]}},
			{"type": "list", "data": {"style": "unordered", "items": [{"content": "три"}]}},
		)
		self.assertIn("1. раз\n2. два", урок.сегмент(1))
		self.assertIn("- три", урок.сегмент(1))

	def test_код_оборачивается_в_блок(self):
		урок = self.нормализовать_блоки({"type": "code", "data": {"code": "print(1)"}})
		self.assertIn("```\nprint(1)\n```", урок.сегмент(1))

	def test_видео_уходит_в_медиа_и_остаётся_ссылкой(self):
		урок = self.нормализовать_блоки(
			{
				"type": "embed",
				"data": {"service": "youtube", "source": "https://youtu.be/abc", "caption": "Разбор"},
			}
		)
		self.assertEqual(len(урок.media), 1)
		self.assertEqual(урок.media[0].kind, "video")
		self.assertIn("[Разбор](https://youtu.be/abc)", урок.сегмент(1))

	def test_загруженный_файл_различается_по_расширению(self):
		урок = self.нормализовать_блоки(
			{"type": "upload", "data": {"file_url": "/files/lecture.mp4", "file_type": "mp4"}},
			{"type": "upload", "data": {"file_url": "/files/scheme.png"}},
		)
		self.assertEqual([м.kind for м in урок.media], ["video", "image"])

	def test_блок_квиза_становится_пометкой_без_вопросов(self):
		урок = self.нормализовать_блоки({"type": "quiz", "data": {"quiz": "quiz-1"}})
		self.assertIn("проверка знаний", урок.сегмент(1))
		self.assertNotIn("quiz-1", урок.сегмент(1))

	def test_незнакомый_блок_пропускается_молча(self):
		# Состав блоков задаёт Frappe Learning и меняет его без нашего ведома.
		урок = self.нормализовать_блоки(
			{"type": "чего-то-новое", "data": {"text": "?"}},
			{"type": "paragraph", "data": {"text": "Дальше по плану"}},
		)
		self.assertEqual(урок.сегмент(1), "Дальше по плану")

	def test_битый_json_не_роняет_разбор(self):
		# Урок, отредактированный из Desk, законно содержит не-JSON.
		урок = нормализовать(title="Урок", content="просто текст", body="Материал из body")
		self.assertEqual(урок.сегмент(1), "Материал из body")

	# --- markdown с макросами ---

	def test_макрос_видео_превращается_в_медиа(self):
		урок = нормализовать(title="Урок", body="Смотрим: {{ YouTubeVideo(abc123) }}")
		self.assertEqual(урок.media[0].url, "https://www.youtube.com/watch?v=abc123")
		self.assertNotIn("{{", урок.сегмент(1))

	def test_неизвестный_макрос_вырезается(self):
		# Иначе агент зачитает ученику «{{ Something(x) }}» как часть урока.
		урок = нормализовать(title="Урок", body="Текст {{ Something(x) }} дальше")
		self.assertNotIn("{{", урок.сегмент(1))
		self.assertNotIn("Something", урок.сегмент(1))

	# --- сегментация ---

	def test_короткий_урок_остаётся_одним_сегментом(self):
		урок = нормализовать(title="Урок", body="Коротко и ясно")
		self.assertEqual(урок.total_segments, 1)

	def test_длинный_урок_режется_по_заголовкам(self):
		части = [f"## Часть {i}\n\n" + "текст. " * 400 for i in range(4)]
		урок = нормализовать(title="Урок", body="\n\n".join(части))
		self.assertGreater(урок.total_segments, 1)
		self.assertTrue(урок.сегмент(1).lstrip().startswith("## Часть 0"))

	def test_номер_сегмента_за_границами_не_роняет_выдачу(self):
		урок = нормализовать(title="Урок", body="Один сегмент")
		self.assertEqual(урок.сегмент(99), урок.сегмент(1))

	def test_пустой_урок_даёт_ноль_сегментов(self):
		урок = нормализовать(title="Урок", content=None, body=None)
		self.assertEqual(урок.total_segments, 0)
		self.assertEqual(урок.сегмент(1), "")
