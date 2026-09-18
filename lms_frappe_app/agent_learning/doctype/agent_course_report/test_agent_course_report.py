# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.tests.sample_data import (
	зачислить,
	создать_занятие,
	создать_менеджера,
	создать_организацию,
	создать_ученика,
	создать_урок,
)


class IntegrationTestAgentCourseReport(IntegrationTestCase):
	"""Репорт агента о курсе: хранение и очередь разбора."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"rep-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.курс = зачислить(self.ученик, self.урок)
		self.занятие = создать_занятие(self.ученик, self.урок)

	def test_новый_репорт_ждёт_разбора(self):
		"""Why: статус — очередь методолога. Репорт, заведённый без статуса,
		выпал бы из фильтра «новые» и не был бы разобран никогда."""
		репорт = frappe.get_doc(
			{
				"doctype": "Agent Course Report",
				"session": self.занятие,
				"course": self.курс,
				"lesson": self.урок,
				"kind": "Material Issue",
				"text": "В примере перепутаны роли",
			}
		).insert()

		self.assertEqual(репорт.status, "New")

	def test_репорты_не_читают_ни_ученик_ни_руководитель(self):
		"""Why: репорт о курсе — не отчётность по людям. Граница проходит по
		сущности: прав на доктайп у роли нет вовсе, и обойти это новым методом
		или фильтром полей нельзя. Дописанный в схему блок прав иначе не
		заметит никто."""
		суффикс = frappe.generate_hash(length=6)
		организация = создать_организацию(f"Компания {суффикс}")
		руководитель = создать_менеджера(f"rep-m-{суффикс}@example.com", организация)

		frappe.set_user(self.ученик)
		self.assertFalse(frappe.has_permission("Agent Course Report", "read"))

		frappe.set_user(руководитель)
		self.assertFalse(frappe.has_permission("Agent Course Report", "read"))
