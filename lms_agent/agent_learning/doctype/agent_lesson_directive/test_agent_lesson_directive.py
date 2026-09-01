# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

DOCTYPE = "Agent Lesson Directive"
УЧЕНИК = "uchenik-proba@example.com"


def создать_урок() -> str:
	"""Минимальная цепочка курс → глава → урок."""
	course = frappe.get_doc(
		{
			"doctype": "LMS Course",
			"title": "Проба директив",
			"short_introduction": "Курс для тестов",
			"description": "<p>Курс для тестов</p>",
			"published": 0,
			"instructors": [{"instructor": "Administrator"}],
		}
	).insert(ignore_permissions=True)
	chapter = frappe.get_doc(
		{"doctype": "Course Chapter", "title": "Глава", "course": course.name}
	).insert(ignore_permissions=True)
	lesson = frappe.get_doc(
		{"doctype": "Course Lesson", "title": "Урок", "chapter": chapter.name}
	).insert(ignore_permissions=True)
	return lesson.name


def создать_ученика() -> str:
	if not frappe.db.exists("User", УЧЕНИК):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": УЧЕНИК,
				"first_name": "Ученик",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		user.add_roles("LMS Student")
	return УЧЕНИК


class IntegrationTestAgentLessonDirective(IntegrationTestCase):
	"""Директива: доступ, версии, действующая версия."""

	def setUp(self):
		self.lesson = создать_урок()

	def директива(self, **поля):
		return frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"lesson": self.lesson,
				"teaching_directive": "Начать с примера, не с определения",
				**поля,
			}
		).insert(ignore_permissions=True)

	def test_ученик_не_имеет_доступа_к_директиве(self):
		"""Несущая проверка: эталон педагогики не утекает через права.

		Директива приходит агенту только как поле ответа whitelisted-метода,
		с явной пометкой. Прямого чтения у роли ученика быть не должно ни на
		запись, ни на список.
		"""
		создать_ученика()
		self.директива()
		frappe.set_user(УЧЕНИК)
		try:
			self.assertFalse(frappe.has_permission(DOCTYPE, "read"))
			self.assertFalse(frappe.has_permission(DOCTYPE, "write"))
		finally:
			frappe.set_user("Administrator")

	def test_версия_проставляется_сама(self):
		первая = self.директива()
		вторая = self.директива()
		self.assertEqual(первая.version, 1)
		self.assertEqual(вторая.version, 2)

	def test_на_урок_остаётся_одна_действующая_директива(self):
		первая = self.директива()
		self.assertTrue(первая.is_active)

		вторая = self.директива()
		первая.reload()

		self.assertTrue(вторая.is_active)
		self.assertFalse(первая.is_active)

	def test_директива_другого_урока_не_деактивируется(self):
		чужой_урок = создать_урок()
		чужая = frappe.get_doc(
			{"doctype": DOCTYPE, "lesson": чужой_урок, "teaching_directive": "…"}
		).insert(ignore_permissions=True)

		self.директива()
		чужая.reload()

		self.assertTrue(чужая.is_active)
