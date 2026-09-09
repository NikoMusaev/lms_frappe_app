# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.sample_data import создать_курс, создать_ученика

DOCTYPE = "Agent Course Artifact"


class IntegrationTestAgentCourseArtifact(IntegrationTestCase):
	"""Схема артефакта: версии по паре «курс + ключ», ключи блоков, доступ."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.курс = создать_курс(f"Курс {frappe.generate_hash(length=6)}")

	def схема(self, slug: str = "project_summary", **поля):
		return frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"course": self.курс,
				"slug": slug,
				"title": "Резюме проекта",
				"blocks": [
					{"block_key": "goal", "title": "Цель", "hint": "Одной фразой"},
					{"block_key": "sponsor", "title": "Спонсор"},
				],
				**поля,
			}
		).insert(ignore_permissions=True)

	def test_версия_считается_по_курсу_и_ключу(self):
		"""Ради этого миксин и обобщали: в курсе несколько документов, и
		версии у каждого свои."""
		резюме = self.схема("project_summary")
		карта = self.схема("deliverables_map")
		резюме.reload()

		self.assertEqual(резюме.version, 1)
		self.assertEqual(карта.version, 1)
		self.assertTrue(резюме.is_active, "схема другого документа не снимает эту с действия")
		self.assertTrue(карта.is_active)

	def test_новая_версия_того_же_документа_вытесняет_прежнюю(self):
		первая = self.схема()
		вторая = self.схема()
		первая.reload()

		self.assertEqual(вторая.version, 2)
		self.assertTrue(вторая.is_active)
		self.assertFalse(первая.is_active)

	def test_ключи_нормализуются(self):
		схема = self.схема(" Project_Summary ", blocks=[{"block_key": " Goal ", "title": "Цель"}])

		self.assertEqual(схема.slug, "project_summary")
		self.assertEqual(схема.blocks[0].block_key, "goal")
		self.assertEqual(схема.blocks[0].span, 1)

	def test_повторяющийся_ключ_блока_отклоняется(self):
		with self.assertRaises(frappe.ValidationError):
			self.схема(
				blocks=[
					{"block_key": "goal", "title": "Цель"},
					{"block_key": "GOAL", "title": "Цель ещё раз"},
				]
			)

	def test_ученик_не_имеет_доступа_к_схеме(self):
		"""Схема адресована автору; ученику блоки приходят через метод."""
		ученик = создать_ученика(f"art-{frappe.generate_hash(length=6)}@example.com")
		self.схема()
		frappe.set_user(ученик)

		self.assertFalse(frappe.has_permission(DOCTYPE, "read"))
		self.assertFalse(frappe.has_permission(DOCTYPE, "write"))
