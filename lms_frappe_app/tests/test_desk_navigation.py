# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Навигация в desk: приложение на стартовом экране, workspace и сайдбар.

`Why:` Frappe 16 держит навигацию на постоянном сайдбаре, который
автогенерируется по модулю и берёт не больше трёх доктайпов, а на стартовый
экран приложение попадает только через `add_to_apps_screen`. Без своих
записей разделы приложения открывались только по прямой ссылке — так их и
нашли на проде.
"""

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.sample_data import создать_ученика

WORKSPACE = "Agent Learning"
МОДУЛЬ = "Agent Learning"


class IntegrationTestDeskNavigation(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_workspace_модуля_публичный(self):
		# Точка входа в desk: без неё сайдбару нечего показывать.
		workspace = frappe.get_doc("Workspace", WORKSPACE)

		self.assertTrue(workspace.public)
		self.assertEqual(workspace.module, МОДУЛЬ)
		self.assertFalse(workspace.is_hidden)

	def test_сайдбар_ведёт_на_каждый_доктайп_модуля(self):
		"""Пин на состав: новый доктайп без строки в сайдбаре снова станет
		невидимым, и заметят это по прямой ссылке, как в прошлый раз."""
		сайдбар = frappe.get_doc("Workspace Sidebar", WORKSPACE)
		ссылки = {п.link_to for п in сайдбар.items if п.type == "Link" and п.link_type == "DocType"}
		доктайпы = set(
			frappe.get_all("DocType", filters={"module": МОДУЛЬ, "istable": 0}, pluck="name")
		)

		self.assertTrue(сайдбар.standard)
		self.assertEqual(доктайпы - ссылки, set(), "доктайпы модуля без пункта в сайдбаре")

	def test_сайдбар_начинается_с_обзора(self):
		сайдбар = frappe.get_doc("Workspace Sidebar", WORKSPACE)
		первый = сайдбар.items[0]

		self.assertEqual((первый.link_type, первый.link_to), ("Workspace", WORKSPACE))

	def test_workspace_показывает_карточки_с_доктайпами(self):
		workspace = frappe.get_doc("Workspace", WORKSPACE)
		карточки = [с.label for с in workspace.links if с.type == "Card Break"]
		ссылки = {с.link_to for с in workspace.links if с.type == "Link"}

		self.assertEqual(карточки, ["Курс", "Ученики", "Организации"])
		self.assertIn("Agent Student Artifact", ссылки)

	def test_приложение_объявлено_для_стартового_экрана(self):
		приложения = {п["name"]: п for п in frappe.get_hooks("add_to_apps_screen")}

		self.assertIn("lms_frappe_app", приложения)
		self.assertEqual(приложения["lms_frappe_app"]["route"], "/desk/agent-learning")
		self.assertTrue(frappe.get_attr(приложения["lms_frappe_app"]["has_permission"]))

	def test_стартовый_экран_виден_администратору_и_скрыт_от_ученика(self):
		"""Ученик живёт в интерфейсе Frappe Learning; ссылка в desk для него —
		дверь в 403."""
		from lms_frappe_app.agent_learning.permissions import доступен_desk

		ученик = создать_ученика(f"desk-{frappe.generate_hash(length=6)}@example.com")

		frappe.set_user("Administrator")
		self.assertTrue(доступен_desk())
		frappe.set_user(ученик)
		self.assertFalse(доступен_desk())

	def test_плитка_на_стартовом_экране_ведёт_в_сайдбар_модуля(self):
		"""`Why:` плитки стартового экрана — записи Desktop Icon, и
		автогенерация из add_to_apps_screen для нового приложения при
		миграции не сработала: на проде стартовый экран показывал только
		Framework и Frappe Learning. Плитка типа Link не требует файла
		логотипа, а видна тем, кому доступен хоть один пункт сайдбара."""
		плитка = frappe.get_doc("Desktop Icon", WORKSPACE)

		self.assertTrue(плитка.standard)
		self.assertFalse(плитка.hidden)
		self.assertEqual((плитка.link_type, плитка.link_to), ("Workspace Sidebar", WORKSPACE))
