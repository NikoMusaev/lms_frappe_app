# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Окно установки PWA на телефоне не всплывает (learning-services#301)."""

import frappe
from frappe.tests import IntegrationTestCase


class IntegrationTestInstallPrompt(IntegrationTestCase):
	def test_патч_прячет_окно_установки(self):
		from lms_frappe_app.patches.v0_1.hide_install_prompt import execute

		frappe.db.set_single_value("LMS Settings", "disable_pwa", 0)

		execute()

		self.assertEqual(frappe.db.get_single_value("LMS Settings", "disable_pwa"), 1)

	def test_патч_в_списке_миграций(self):
		"""Без строки в `patches.txt` патч не выполнится на стенде никогда."""
		патчи = frappe.get_app_path("lms_frappe_app", "patches.txt")
		with open(патчи, encoding="utf-8") as файл:
			self.assertIn("lms_frappe_app.patches.v0_1.hide_install_prompt", файл.read())
