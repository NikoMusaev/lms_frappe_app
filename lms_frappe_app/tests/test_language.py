# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Язык платформы.

`Why:` интерфейс LMS своего переключателя не показывает — язык он спрашивает
у сервера. Настройка живёт в базе и не переживает пересоздания сайта, поэтому
приезжает кодом; но выбранный администратором язык трогать нельзя, иначе
каждая выкатка откатывала бы его решение.
"""

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.install import ЯЗЫК, обеспечить_язык_платформы


class IntegrationTestLanguage(IntegrationTestCase):
	def setUp(self):
		self.прежний = frappe.db.get_single_value("System Settings", "language")
		self.addCleanup(self._вернуть)

	def _вернуть(self):
		frappe.db.set_single_value("System Settings", "language", self.прежний or "")
		frappe.clear_cache()

	def _задать(self, значение: str):
		frappe.db.set_single_value("System Settings", "language", значение)
		frappe.clear_document_cache("System Settings", "System Settings")

	def test_пустой_язык_становится_русским(self):
		self._задать("")

		обеспечить_язык_платформы()

		self.assertEqual(
			frappe.db.get_single_value("System Settings", "language"), ЯЗЫК
		)

	def test_выбранный_язык_не_трогаем(self):
		"""Настойчивость откатывала бы решение администратора каждой выкаткой."""
		self._задать("de")

		обеспечить_язык_платформы()

		self.assertEqual(frappe.db.get_single_value("System Settings", "language"), "de")

	def test_русский_известен_платформе(self):
		"""`sync_languages` заводит запись на каждой миграции — без неё
		настройка указывала бы на несуществующий язык."""
		self.assertTrue(frappe.db.exists("Language", ЯЗЫК))
