# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.sample_data import создать_куратора, создать_ученика


class IntegrationTestAgentPage(IntegrationTestCase):
	"""Страница «Подключить агента»: кто и какие адреса на ней видит."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def сведения_для(self, пользователь: str) -> dict:
		from lms_frappe_app.www.agent import сведения

		frappe.set_user(пользователь)
		return сведения(пользователь)

	def test_гость_получает_приглашение_войти(self):
		# Адреса эндпоинтов — не секрет, но без учётной записи подключаться
		# некуда: агент входит во Frappe той же учёткой.
		с = self.сведения_для("Guest")
		self.assertTrue(с["is_guest"])
		self.assertEqual(с["connections"], [])
		self.assertIn("redirect-to=/agent", с["login_url"])

	def test_ученик_видит_только_учебный_эндпоинт(self):
		ученик = создать_ученика(f"uch-{frappe.generate_hash(length=6)}@example.com")
		с = self.сведения_для(ученик)
		self.assertFalse(с["is_guest"])
		self.assertFalse(с["is_curator"])
		адреса = [п["url"] for п in с["connections"]]
		self.assertEqual(len(адреса), 1)
		self.assertTrue(адреса[0].endswith("/mcp"))

	def test_куратор_видит_оба_эндпоинта(self):
		куратор = создать_куратора(f"kur-{frappe.generate_hash(length=6)}@example.com")
		с = self.сведения_для(куратор)
		self.assertTrue(с["is_curator"])
		адреса = [п["url"] for п in с["connections"]]
		self.assertEqual(len(адреса), 2)
		self.assertTrue(any(а.endswith("/mcp") for а in адреса))
		self.assertTrue(any(а.endswith("/authoring") for а in адреса))
		# Куратору первым вызовом нужен гайд — иначе клиент без prompts
		# выводит порядок работы из описаний инструментов.
		авторинг = next(п for п in с["connections"] if п["url"].endswith("/authoring"))
		self.assertIn("authoring_guide", авторинг["first_step"])

	def test_адреса_строятся_от_адреса_сайта(self):
		# Хардкод домена сломал бы локальный стенд и любой другой хост.
		куратор = создать_куратора(f"kur-{frappe.generate_hash(length=6)}@example.com")
		с = self.сведения_для(куратор)
		for п in с["connections"]:
			self.assertTrue(п["url"].startswith(с["site_url"]))

	def test_ссылка_на_исходники_есть_всегда(self):
		# Обязательство AGPL ст. 13: пользователь сетевого сервиса видит,
		# откуда взять исходники, — и гость тоже.
		for пользователь in ("Guest", "Administrator"):
			с = self.сведения_для(пользователь)
			self.assertTrue(с["source_url"].startswith("https://github.com/"))

	def test_пункт_сайдбара_ставится_один_раз(self):
		from lms_frappe_app.install import обеспечить_пункт_сайдбара

		frappe.set_user("Administrator")
		обеспечить_пункт_сайдбара()
		обеспечить_пункт_сайдбара()
		пункты = frappe.get_all(
			"LMS Sidebar Item",
			{"parenttype": "LMS Settings", "parentfield": "sidebar_items", "route": "agent"},
			["title"],
		)
		self.assertEqual(len(пункты), 1)
		self.assertEqual(пункты[0].title, "Подключить агента")
