# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.sample_data import создать_ученика, создать_урок

DOCTYPE = "Agent Lesson Directive"
УЧЕНИК = "uchenik-proba@example.com"


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
		создать_ученика(УЧЕНИК)
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
		чужой_урок = создать_урок("Другой урок")
		чужая = frappe.get_doc(
			{"doctype": DOCTYPE, "lesson": чужой_урок, "teaching_directive": "…"}
		).insert(ignore_permissions=True)

		self.директива()
		чужая.reload()

		self.assertTrue(чужая.is_active)
