# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Настройка входа через Google.

`Why:` ключ провайдера — данные, а не код, и заводить его кликами значит
терять при пересоздании сайта. Здесь проверяется, что настройка приезжает из
конфигурации сайта, переживает повторные миграции и не требует секретов там,
где их нет.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password

from lms_frappe_app.install import КЛЮЧ_ID, КЛЮЧ_СЕКРЕТ, обеспечить_вход_через_google

ЗАПИСЬ = ("Social Login Key", "google")


class IntegrationTestGoogleLogin(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(self._вернуть_конфигурацию)
		self.прежние = {
			ключ: frappe.conf.get(ключ) for ключ in (КЛЮЧ_ID, КЛЮЧ_СЕКРЕТ)
		}
		if frappe.db.exists(*ЗАПИСЬ):
			frappe.delete_doc(*ЗАПИСЬ, force=True, ignore_permissions=True)

	def _вернуть_конфигурацию(self):
		for ключ, значение in self.прежние.items():
			if значение is None:
				frappe.conf.pop(ключ, None)
			else:
				frappe.conf[ключ] = значение

	def _задать(self, client_id: str, client_secret: str):
		frappe.conf[КЛЮЧ_ID] = client_id
		frappe.conf[КЛЮЧ_СЕКРЕТ] = client_secret

	def test_без_ключей_ничего_не_создаётся(self):
		"""Локальная разработка не обязана держать секреты Google."""
		frappe.conf.pop(КЛЮЧ_ID, None)
		frappe.conf.pop(КЛЮЧ_СЕКРЕТ, None)

		обеспечить_вход_через_google()

		self.assertFalse(frappe.db.exists(*ЗАПИСЬ))

	def test_ключ_создаётся_из_конфигурации(self):
		self._задать("id-1.apps.googleusercontent.com", "secret-1")

		обеспечить_вход_через_google()

		ключ = frappe.get_doc(*ЗАПИСЬ)
		self.assertEqual(ключ.client_id, "id-1.apps.googleusercontent.com")
		self.assertTrue(ключ.enable_social_login)
		self.assertEqual(ключ.sign_ups, "Allow", "пускаем всех — решение куратора")
		# Адреса приходят от Frappe, а не из нашей копии.
		self.assertIn("accounts.google.com", ключ.authorize_url)
		self.assertEqual(
			ключ.redirect_url,
			"/api/method/frappe.integrations.oauth2_logins.login_via_google",
		)

	def test_секрет_доступен_для_кнопки_входа(self):
		"""`/login` рисует кнопку, только если секрет лежит в самой записи."""
		self._задать("id-1", "secret-1")

		обеспечить_вход_через_google()

		self.assertEqual(
			get_decrypted_password(*ЗАПИСЬ, "client_secret"),
			"secret-1",
		)

	def test_повторный_вызов_не_плодит_версий(self):
		"""after_migrate зовётся на каждый старт контейнера."""
		self._задать("id-1", "secret-1")
		обеспечить_вход_через_google()
		было = frappe.db.get_value(*ЗАПИСЬ, "modified")

		обеспечить_вход_через_google()

		self.assertEqual(frappe.db.get_value(*ЗАПИСЬ, "modified"), было)

	def test_смена_секрета_подхватывается(self):
		self._задать("id-1", "secret-1")
		обеспечить_вход_через_google()

		self._задать("id-1", "secret-2")
		обеспечить_вход_через_google()

		self.assertEqual(get_decrypted_password(*ЗАПИСЬ, "client_secret"), "secret-2")

	def test_выключенный_ключ_включается_обратно(self):
		"""Иначе случайное выключение в админке переживёт все миграции."""
		self._задать("id-1", "secret-1")
		обеспечить_вход_через_google()
		frappe.db.set_value(*ЗАПИСЬ, "enable_social_login", 0)

		обеспечить_вход_через_google()

		self.assertTrue(frappe.db.get_value(*ЗАПИСЬ, "enable_social_login"))
