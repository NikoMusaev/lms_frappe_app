# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Снимки мест курса — «как было» для разницы в кабинете автора.

`Why:` разница честна, только если снимок берёт ровно тот текст, что видит
автор на месте замечания: материал, поле директивы, вопрос с вариантами, блок
документа, узел карты (lms-high-time/learning-services#271).
"""

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.snapshots import снимок
from lms_frappe_app.api import authoring
from lms_frappe_app.tests.sample_data import создать_куратора


class IntegrationTestSnapshots(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		frappe.set_user(создать_куратора(f"snap-{суффикс}@example.com"))
		self.курс = authoring.create_course(title=f"Снимки {суффикс}", summary="к")["data"]["id"]
		глава = authoring.add_chapter(course=self.курс, title="Рамка")["data"]["id"]
		self.урок = authoring.add_lesson(chapter=глава, title="Первый", body="# Первый\n\nТекст.")["data"]["id"]
		authoring.set_directive(lesson=self.урок, teaching_directive="Веди", objectives="Цель один\nЦель два")
		authoring.set_course_directive(course=self.курс, teaching_directive="Тон", glossary="Риск — событие")
		authoring.add_quiz(
			lesson=self.урок,
			questions=[
				{
					"text": "Что не так?",
					"options": [{"text": "a", "correct": True, "explanation": "потому"}, {"text": "b"}],
				}
			],
		)
		self.вопрос = authoring.get_lesson(lesson=self.урок)["data"]["quiz"]["questions"][0]["id"]
		authoring.set_course_artifact(
			course=self.курс,
			artifact="register",
			title="Реестр",
			blocks=[{"key": "risks", "title": "Риски", "hint": "Пять записей", "lesson": self.урок}],
		)

	def test_снимки_мест_урока_и_курса(self):
		self.assertEqual(снимок(self.курс, self.урок, "material"), {"text": "# Первый\n\nТекст.", "mode": "text"})
		self.assertEqual(
			снимок(self.курс, self.урок, "directive.teaching_directive"), {"text": "Веди", "mode": "text"}
		)
		self.assertEqual(
			снимок(self.курс, self.урок, "directive.objectives"), {"text": "Цель один\nЦель два", "mode": "lines"}
		)
		self.assertEqual(
			снимок(self.курс, None, "course_directive.glossary"), {"text": "Риск — событие", "mode": "lines"}
		)
		вопрос = снимок(self.курс, self.урок, f"question.{self.вопрос}")
		self.assertEqual(вопрос["mode"], "lines")
		self.assertEqual(вопрос["text"].split("\n"), ["Что не так?", "✓ a — потому", "· b"])
		self.assertEqual(
			снимок(self.курс, None, "block.register/risks"), {"text": "Риски\n\nПять записей", "mode": "text"}
		)

	def test_снимок_урока_собирает_его_места(self):
		урок = снимок(self.курс, self.урок, "lesson")

		self.assertEqual(
			list(урок["places"]),
			[
				"material",
				"directive.teaching_directive",
				"directive.objectives",
				f"question.{self.вопрос}",
				"block.register/risks",
			],
		)
		self.assertEqual(урок["places"]["material"], снимок(self.курс, self.урок, "material"))

	def test_узел_карты(self):
		authoring.set_course_map(
			course=self.курс,
			levels=[{"key": "result", "title": "Результат"}, {"key": "thesis", "title": "Тезисы"}],
			nodes=[
				{"id": "R", "level": "result", "text": "Курс"},
				{"id": "T1", "level": "thesis", "text": "Тезис", "parents": ["R"], "note": "Примечание"},
			],
		)

		self.assertEqual(снимок(self.курс, None, "map.T1"), {"text": "Тезис\nПримечание", "mode": "lines"})

	def test_у_курса_и_пропавшего_места_снимка_нет(self):
		self.assertIsNone(снимок(self.курс, None, "course"))
		self.assertIsNone(снимок(self.курс, self.урок, "question.QTS-нет"))
		self.assertIsNone(снимок(self.курс, None, "block.register/нет"))
		self.assertIsNone(снимок(self.курс, None, "map.T1"))
		self.assertIsNone(снимок(self.курс, "урок-которого-нет", "material"))
