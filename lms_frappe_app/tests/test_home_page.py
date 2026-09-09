# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Куда попадает вошедший человек.

`Why:` домашнюю страницу задаёт не наше приложение и не `frappe/lms` — без
хука Frappe доходит до последнего фолбэка и показывает страницу настроек
`me`, из которой новому ученику некуда идти. Пропажа хука выглядела бы как
«всё работает»: сайт отвечает, вход проходит, просто ведёт не туда.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.utils import get_home_page

from lms_frappe_app.agent_learning.sample_data import создать_ученика

ДОМАШНЯЯ = "lms"


class IntegrationTestHomePage(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.local.flags.pop, "home_page", None)
		frappe.local.flags.pop("home_page", None)
		self.ученик = создать_ученика(
			f"home-{frappe.generate_hash(length=6)}@example.com"
		)

	def test_ученик_попадает_в_lms(self):
		frappe.set_user(self.ученик)

		self.assertEqual(get_home_page(), ДОМАШНЯЯ)

	def test_страница_настроек_больше_не_домашняя(self):
		"""Именно её видел первый вошедший через Google."""
		frappe.set_user(self.ученик)

		self.assertNotEqual(get_home_page(), "me")

	def test_хук_объявлен_приложением(self):
		"""Значение приходит из hooks.py, а не из настроек сайта: настройка в
		базе не переживает пересоздания сайта."""
		self.assertEqual(frappe.get_hooks("website_user_home_page")[-1], ДОМАШНЯЯ)
