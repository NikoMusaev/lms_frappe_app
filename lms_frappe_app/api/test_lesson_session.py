# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Занятие по уроку для веб-чата (lms-platform#151).

Метод только читает: по нему сервис узнаёт, идёт ли по уроку разговор и
закрыт ли урок, — и решает, показать историю или начинать занятие. Поэтому он
не заводит занятий и не пишет событий в журнал: иначе каждый возврат на
страницу оставлял бы след, которого не было.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning import quiz
from lms_frappe_app.tests.sample_data import (
	зачислить,
	создать_занятие,
	создать_ученика,
	создать_урок,
)
from lms_frappe_app.api import student

СОСТОЯНИЕ = json.dumps({"id": "conv-1", "messages": []})


class IntegrationTestLessonSession(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"lesson-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		зачислить(self.ученик, self.урок)
		self.чужой = создать_ученика(f"lesson-other-{суффикс}@example.com")
		# Зачисление — под Administrator: обычному ученику Learning запрещает
		# записываться на неопубликованный курс, а тестовые курсы такие и есть.
		зачислить(self.чужой, self.урок)
		frappe.set_user(self.ученик)

	def событий(self, занятие: str) -> int:
		return frappe.db.count("Agent Session Event", {"session": занятие})

	def занятий(self) -> int:
		return frappe.db.count(
			"Agent Learning Session", {"student": self.ученик, "lesson": self.урок}
		)

	def test_без_занятий_отдаётся_пусто(self):
		данные = student.lesson_session(self.урок)["data"]

		self.assertEqual(данные["session"], None)
		self.assertEqual(данные["status"], None)
		self.assertFalse(данные["has_chat_state"])
		self.assertFalse(данные["completed"])

	def test_незакрытое_занятие_отдаётся_как_идущее(self):
		занятие = student.start_lesson(lesson=self.урок)["data"]["session"]

		данные = student.lesson_session(self.урок)["data"]

		self.assertEqual(данные["session"], занятие)
		self.assertEqual(данные["status"], "In Progress")
		self.assertFalse(данные["completed"])

	def test_закрытое_занятие_с_разговором_видно_целиком(self):
		"""Ради этого метод и заводится: ученик вернулся к пройденному уроку,
		и сервису нужно найти разговор, а не начинать урок заново."""
		занятие = student.start_lesson(lesson=self.урок)["data"]["session"]
		student.save_chat_state(занятие, СОСТОЯНИЕ, "1")
		запись = frappe.get_doc("Agent Learning Session", занятие)
		quiz.отметить_урок_пройденным(запись)
		запись.status = "Completed"
		запись.save(ignore_permissions=True)

		данные = student.lesson_session(self.урок)["data"]

		self.assertEqual(данные["session"], занятие)
		self.assertEqual(данные["status"], "Completed")
		self.assertTrue(данные["has_chat_state"])
		self.assertTrue(данные["completed"])

	def test_отдаётся_последнее_занятие_урока(self):
		первое = создать_занятие(self.ученик, self.урок)
		frappe.db.set_value("Agent Learning Session", первое, "status", "Abandoned")
		последнее = student.start_lesson(lesson=self.урок)["data"]["session"]

		данные = student.lesson_session(self.урок)["data"]

		self.assertEqual(данные["session"], последнее)

	def test_чужое_занятие_не_видно(self):
		frappe.set_user(self.чужой)
		чужое = student.start_lesson(lesson=self.урок)["data"]["session"]
		frappe.set_user(self.ученик)

		данные = student.lesson_session(self.урок)["data"]

		self.assertNotEqual(данные["session"], чужое)
		self.assertEqual(данные["session"], None)

	def test_метод_ничего_не_заводит_и_не_пишет_в_журнал(self):
		занятие = student.start_lesson(lesson=self.урок)["data"]["session"]
		событий_до = self.событий(занятие)
		занятий_до = self.занятий()

		student.lesson_session(self.урок)
		student.lesson_session(self.урок)

		self.assertEqual(self.событий(занятие), событий_до)
		self.assertEqual(self.занятий(), занятий_до)
