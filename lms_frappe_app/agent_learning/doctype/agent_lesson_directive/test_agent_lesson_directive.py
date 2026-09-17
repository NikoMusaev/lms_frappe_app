# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.directives import действующая
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

	def test_на_урок_остаётся_одна_действующая_директива(self):
		первая = self.директива()
		self.assertEqual(первая.version, 1)
		self.assertTrue(первая.is_active)

		вторая = self.директива()
		первая.reload()

		self.assertEqual(вторая.version, 2)
		self.assertTrue(вторая.is_active)
		self.assertFalse(первая.is_active)

	def test_при_двух_действующих_версиях_берётся_свежая(self):
		"""`Why:` инвариант держит контроллер, но `is_active` правят и мимо
		него — прямой записью в базу, импортом, чужой миграцией. Разъехавшись,
		версии дают агенту произвольную из двух, и порядок «сначала старая»
		означает занятие по переписанному тексту — ровно то, от чего уходили
		новой редакцией.
		"""
		старая = self.директива()
		свежая = self.директива()
		frappe.db.set_value(DOCTYPE, старая.name, "is_active", 1, update_modified=False)

		self.assertEqual(действующая(DOCTYPE, {"lesson": self.lesson}), свежая.name)

	def test_директива_другого_урока_не_деактивируется(self):
		чужой_урок = создать_урок("Другой урок")
		чужая = frappe.get_doc(
			{"doctype": DOCTYPE, "lesson": чужой_урок, "teaching_directive": "…"}
		).insert(ignore_permissions=True)

		self.директива()
		чужая.reload()

		self.assertTrue(чужая.is_active)
