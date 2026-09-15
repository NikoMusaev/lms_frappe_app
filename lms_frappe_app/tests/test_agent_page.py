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
		from lms_frappe_app.install import обеспечить_пункты_сайдбара

		frappe.set_user("Administrator")
		обеспечить_пункты_сайдбара()
		обеспечить_пункты_сайдбара()
		пункты = frappe.get_all(
			"LMS Sidebar Item",
			{"parenttype": "LMS Settings", "parentfield": "sidebar_items", "route": "agent-sidebar"},
			["title", "web_page"],
		)
		self.assertEqual(len(пункты), 1)
		self.assertEqual(пункты[0].title, "Подключить агента")
		# Web Page у пункта обязателен, но это заглушка: сайдбар ведёт по её
		# route, а на настоящую страницу уводит редирект. Публиковать нельзя.
		self.assertFalse(frappe.db.get_value("Web Page", пункты[0].web_page, "published"))

	def test_маршрут_пункта_ведёт_на_страницу(self):
		# `route` пункта — это route его Web Page (fetch_from); без редиректа
		# сайдбар привёл бы на неопубликованную заглушку и 404.
		редиректы = {п["source"]: п["target"] for п in frappe.get_hooks("website_redirects")}
		self.assertEqual(редиректы.get("/agent-sidebar"), "/agent")

	# --- веб-чат (lms-platform#141) ---

	def test_состав_пунктов_сайдбара(self):
		# Пин на состав: пункт, добавленный или убранный мимо ревью, виден здесь.
		from lms_frappe_app.install import ПУНКТЫ_САЙДБАРА

		self.assertEqual(
			[п["route"] for п in ПУНКТЫ_САЙДБАРА],
			["agent-sidebar", "study-in-browser", "artifacts-sidebar"],
		)

	def test_заглушки_не_попадают_в_пути_mcp_сервиса(self):
		"""Traefik сопоставляет пути сервиса mcp по префиксу.

		`Why:` заглушка `/chat-sidebar` уходила в MCP-сервис по правилу `/chat`
		и отвечала «Not Found» вместо переадресации в чат (lms-platform#142).
		"""
		from lms_frappe_app.install import ПУНКТЫ_САЙДБАРА

		пути_mcp = ("mcp", "authoring", "chat", ".well-known")
		for пункт in ПУНКТЫ_САЙДБАРА:
			self.assertFalse(пункт["route"].startswith(пути_mcp), пункт["route"])

	def test_пункт_браузера_ставится_один_раз(self):
		from lms_frappe_app.install import обеспечить_пункты_сайдбара

		frappe.set_user("Administrator")
		обеспечить_пункты_сайдбара()
		обеспечить_пункты_сайдбара()
		пункты = frappe.get_all(
			"LMS Sidebar Item",
			{"parenttype": "LMS Settings", "parentfield": "sidebar_items", "route": "study-in-browser"},
			["title", "web_page"],
		)
		self.assertEqual(len(пункты), 1)
		self.assertEqual(пункты[0].title, "Заниматься в браузере")
		self.assertFalse(frappe.db.get_value("Web Page", пункты[0].web_page, "published"))

	def test_маршрут_пункта_браузера_ведёт_в_чат(self):
		# Чат живёт в MCP-сервисе на том же домене, что и сайт, — как `/mcp`.
		редиректы = {п["source"]: п["target"] for п in frappe.get_hooks("website_redirects")}
		self.assertEqual(редиректы.get("/study-in-browser"), "/chat")

	def test_патч_убирает_заглушку_под_путём_чата(self):
		from lms_frappe_app.install import обеспечить_пункты_сайдбара
		from lms_frappe_app.patches.v0_1.chat_sidebar_route import execute

		frappe.set_user("Administrator")
		заглушка = frappe.get_doc(
			{
				"doctype": "Web Page",
				"published": 0,
				"content_type": "Rich Text",
				"main_section": "<p>Заглушка</p>",
				# Заголовок другой: имя Web Page строится из него, а новая
				# заглушка с тем же заголовком уже заведена миграцией. На стенде
				# столкновения нет — патч идёт раньше after_migrate.
				"title": "Заниматься в браузере под путём чата",
				"route": "chat-sidebar",
			}
		).insert(ignore_permissions=True)
		настройки = frappe.get_single("LMS Settings")
		настройки.append("sidebar_items", {"web_page": заглушка.name, "icon": "message-circle"})
		настройки.save(ignore_permissions=True)
		обеспечить_пункты_сайдбара()

		execute()
		execute()  # повторный запуск не падает

		self.assertFalse(frappe.db.exists("Web Page", {"route": "chat-sidebar"}))
		self.assertFalse(frappe.db.exists("LMS Sidebar Item", {"web_page": заглушка.name}))
		self.assertTrue(
			frappe.db.exists("LMS Sidebar Item", {"parenttype": "LMS Settings", "route": "study-in-browser"})
		)

	def test_страница_зовёт_в_браузер_с_числом_пробных_уроков(self):
		from lms_frappe_app.agent_learning.sample_data import политика_по_умолчанию

		self.addCleanup(политика_по_умолчанию)
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Agent Learning Settings", "web_demo_lessons", 3)
		frappe.clear_document_cache("Agent Learning Settings", "Agent Learning Settings")
		ученик = создать_ученика(f"web-{frappe.generate_hash(length=6)}@example.com")

		с = self.сведения_для(ученик)

		self.assertEqual(с["chat_url"], f"{с['site_url']}/chat")
		self.assertEqual(с["web_demo_lessons"], 3)
