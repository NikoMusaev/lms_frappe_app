# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Курс, собранный агентом куратора, против трактовки Frappe Learning.

`Why:` авторинг пишет ровно те структуры, чтение которых уже трижды ломалось —
строки порядка глав и уроков. Курс, собранный нашими методами, обязан читаться
самой платформой так же, как собранный руками в интерфейсе; иначе ученик пойдёт
по одной последовательности, а куратор будет видеть другую.
"""

import frappe
from frappe.tests import IntegrationTestCase

from lms_agent.agent_learning.sample_data import создать_куратора, создать_ученика
from lms_agent.agent_learning.structure import уроки_главы
from lms_agent.api import authoring


class IntegrationTestAuthoring(IntegrationTestCase):
	def setUp(self):
		суффикс = frappe.generate_hash(length=6)
		self.куратор = создать_куратора(f"curator-{суффикс}@example.com")
		frappe.set_user(self.куратор)

		self.курс = authoring.create_course(title=f"Курс {суффикс}", summary="Собран агентом")["data"]["id"]
		self.глава = authoring.add_chapter(course=self.курс, title="Глава")["data"]["id"]
		self.уроки = [
			authoring.add_lesson(chapter=self.глава, title=f"Урок {б}", body=f"# {б}")["data"]["id"]
			for б in "ABC"
		]

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_собранный_курс_читается_frappe_learning(self):
		from lms.lms.utils import get_chapters, get_lessons

		self.assertEqual([у["name"] for у in get_lessons(self.курс)], self.уроки)
		self.assertEqual([г["name"] for г in get_chapters(self.курс)], [self.глава])

	def test_перестановка_видна_frappe_learning(self):
		from lms.lms.utils import get_lessons

		новый = [self.уроки[2], self.уроки[0], self.уроки[1]]
		authoring.reorder_lessons(chapter=self.глава, lessons=новый)

		self.assertEqual(уроки_главы(self.глава), новый)
		self.assertEqual([у["name"] for у in get_lessons(self.курс)], новый)

	def test_неполный_список_отклоняется(self):
		"""Агент, забывший урок, иначе молча выкинул бы его из программы."""
		ответ = authoring.reorder_lessons(chapter=self.глава, lessons=self.уроки[:2])

		self.assertEqual(ответ["error"]["code"], "order_mismatch")
		self.assertEqual(уроки_главы(self.глава), self.уроки)

	def test_публикация_блокируется_пока_курс_не_готов(self):
		authoring.update_lesson(lesson=self.уроки[0], body="")

		ответ = authoring.publish_course(course=self.курс)

		self.assertEqual(ответ["error"]["code"], "course_not_ready")
		self.assertIn("empty_lesson", [п["code"] for п in ответ["error"]["problems"]])
		self.assertFalse(frappe.db.get_value("LMS Course", self.курс, "published"))

	def test_кривой_вопрос_не_оставляет_мусора(self):
		"""Отказ отменяет только вопросы этого квиза, но отменяет их все."""
		было = frappe.db.count("LMS Question")

		ответ = authoring.add_quiz(
			lesson=self.уроки[0],
			questions=[
				{"text": "Верный есть", "options": [{"text": "a", "correct": True}, {"text": "b"}]},
				{"text": "Верного нет", "options": [{"text": "a"}, {"text": "b"}]},
			],
		)

		self.assertEqual(ответ["error"]["code"], "invalid_question")
		self.assertEqual(ответ["error"]["question_index"], 2)
		self.assertEqual(frappe.db.count("LMS Question"), было, "остались вопросы от сбойного квиза")
		self.assertIsNone(frappe.db.get_value("Course Lesson", self.уроки[0], "quiz_id"))

	def test_ученик_не_собирает_курсы_и_не_видит_эталонов(self):
		"""Отдельный эндпоинт ничего не защищает — защищает эта проверка."""
		ученик = создать_ученика(f"pupil-{frappe.generate_hash(length=6)}@example.com")
		frappe.set_user(ученик)

		for вызов in (
			lambda: authoring.course_draft(course=self.курс),
			lambda: authoring.add_lesson(chapter=self.глава, title="Свой урок", body="x"),
			lambda: authoring.publish_course(course=self.курс),
			lambda: authoring.set_directive(lesson=self.уроки[0], teaching_directive="x"),
		):
			with self.assertRaises(frappe.PermissionError):
				вызов()
