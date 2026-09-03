# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from lms_frappe_app.agent_learning.doctype.agent_learning_session.agent_learning_session import (
	закрыть_брошенные_занятия,
)
from lms_frappe_app.agent_learning.sample_data import создать_ученика, создать_урок

DOCTYPE = "Agent Learning Session"
ПЕРВЫЙ = "uchenik-odin@example.com"
ВТОРОЙ = "uchenik-dva@example.com"


class IntegrationTestAgentLearningSession(IntegrationTestCase):
	"""Занятие: изоляция по ученику, переходы статусов, закрытие брошенных."""

	def setUp(self):
		self.lesson = создать_урок()
		создать_ученика(ПЕРВЫЙ)
		создать_ученика(ВТОРОЙ)
		self.addCleanup(frappe.set_user, "Administrator")

	def занятие(self, student=ПЕРВЫЙ, **поля):
		return frappe.get_doc(
			{"doctype": DOCTYPE, "student": student, "lesson": self.lesson, **поля}
		).insert(ignore_permissions=True)

	# --- изоляция ---

	def test_ученик_видит_в_списке_только_свои_занятия(self):
		своё = self.занятие(student=ПЕРВЫЙ)
		чужое = self.занятие(student=ВТОРОЙ)

		frappe.set_user(ПЕРВЫЙ)
		видимые = frappe.get_list(DOCTYPE, pluck="name")

		self.assertIn(своё.name, видимые)
		self.assertNotIn(чужое.name, видимые)

	def test_чужое_занятие_недоступно_по_прямому_обращению(self):
		"""Фильтр списка сам по себе не защищает: чужую запись попробуют
		открыть по имени, а не искать в списке."""
		чужое = self.занятие(student=ВТОРОЙ)

		frappe.set_user(ПЕРВЫЙ)
		self.assertFalse(frappe.has_permission(DOCTYPE, "read", doc=чужое.name))

	def test_своё_занятие_доступно(self):
		своё = self.занятие(student=ПЕРВЫЙ)
		frappe.set_user(ПЕРВЫЙ)
		self.assertTrue(frappe.has_permission(DOCTYPE, "read", doc=своё.name))

	# --- переходы ---

	def test_курс_проставляется_по_уроку(self):
		ожидаемый = frappe.db.get_value(
			"Course Chapter", frappe.db.get_value("Course Lesson", self.lesson, "chapter"), "course"
		)
		self.assertEqual(self.занятие().course, ожидаемый)

	def test_недопустимый_переход_отклоняется(self):
		занятие = self.занятие()
		занятие.status = "Completed"
		занятие.save(ignore_permissions=True)

		занятие.status = "In Progress"
		with self.assertRaises(frappe.ValidationError):
			занятие.save(ignore_permissions=True)

	def test_завершение_проставляет_время(self):
		занятие = self.занятие()
		занятие.status = "Completed"
		занятие.save(ignore_permissions=True)
		self.assertTrue(занятие.finished_at)

	# --- журнал ---

	def test_событие_двигает_отметку_активности(self):
		занятие = self.занятие()
		frappe.db.set_value(
			DOCTYPE, занятие.name, "last_activity_at", add_to_date(now_datetime(), hours=-3)
		)

		занятие.записать_событие("Directive Issued", "выдана директива")

		обновлённая = frappe.db.get_value(DOCTYPE, занятие.name, "last_activity_at")
		self.assertGreater(обновлённая, add_to_date(now_datetime(), minutes=-1))

	def test_запись_журнала_не_изменяется(self):
		занятие = self.занятие()
		событие = занятие.записать_событие("Checkpoint Reported", "разобрали цикл")

		событие.note = "переписано"
		with self.assertRaises(frappe.ValidationError):
			событие.save(ignore_permissions=True)

	# --- брошенные занятия ---

	def test_брошенное_занятие_закрывается(self):
		занятие = self.занятие()
		frappe.db.set_value(
			DOCTYPE, занятие.name, "last_activity_at", add_to_date(now_datetime(), hours=-24)
		)

		закрыть_брошенные_занятия()
		занятие.reload()

		# Проверяется конкретное занятие, а не счётчик: задача сканирует всю
		# базу, и счётчик зависел бы от данных соседних тестов.
		self.assertEqual(занятие.status, "Abandoned")
		self.assertTrue(
			frappe.db.exists(
				"Agent Session Event", {"session": занятие.name, "kind": "Session Abandoned"}
			)
		)

	def test_свежее_занятие_не_трогается(self):
		занятие = self.занятие()
		закрыть_брошенные_занятия()
		занятие.reload()
		self.assertEqual(занятие.status, "In Progress")

	def test_завершённое_занятие_не_переоткрывается(self):
		занятие = self.занятие()
		занятие.status = "Completed"
		занятие.save(ignore_permissions=True)
		frappe.db.set_value(
			DOCTYPE, занятие.name, "last_activity_at", add_to_date(now_datetime(), hours=-24)
		)

		закрыть_брошенные_занятия()
		занятие.reload()

		self.assertEqual(занятие.status, "Completed")
