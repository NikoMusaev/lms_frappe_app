# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Язык платформы.

`Why:` интерфейс LMS своего переключателя не показывает — язык он спрашивает
у сервера, а настройка живёт в базе и не переживает пересоздания сайта.

Ставится патчем, а не хуком миграции. Первая попытка была хуком с проверкой
«поле пусто»: на стенде оно оказалось не пустым — Frappe при установке пишет
туда `en`, — и язык не менялся три выкатки подряд, молча.
"""

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.patches.v0_1.russian_language import ЯЗЫК, execute


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

	def test_патч_ставит_русский_поверх_умолчания(self):
		"""Frappe пишет в это поле `en` при установке — именно это и меняем."""
		self._задать("en")

		execute()

		self.assertEqual(
			frappe.db.get_single_value("System Settings", "language"), ЯЗЫК
		)

	def test_патч_ставит_русский_и_на_пустом(self):
		self._задать("")

		execute()

		self.assertEqual(
			frappe.db.get_single_value("System Settings", "language"), ЯЗЫК
		)

	def test_русский_включён(self):
		"""`Why:` Frappe заводит его выключенным, и тогда языка нет ни в
		селекторе профиля, ни в подборе по `Accept-Language`."""
		from lms_frappe_app.patches.v0_1.enable_russian_language import execute as включить

		frappe.db.set_value("Language", ЯЗЫК, "enabled", 0)
		включить()

		self.assertTrue(frappe.db.get_value("Language", ЯЗЫК, "enabled"))

	def test_русский_в_списке_доступных(self):
		"""Именно этот список видит селектор языка и подбор по заголовку."""
		from frappe.translate import get_all_languages
		from lms_frappe_app.patches.v0_1.enable_russian_language import execute as включить

		включить()

		self.assertIn(ЯЗЫК, get_all_languages())

	def test_русский_известен_платформе(self):
		"""`sync_languages` заводит запись на каждой миграции — без неё
		настройка указывала бы на несуществующий язык."""
		self.assertTrue(frappe.db.exists("Language", ЯЗЫК))
