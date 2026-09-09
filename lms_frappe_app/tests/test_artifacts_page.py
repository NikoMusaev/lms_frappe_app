# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.sample_data import создать_ученика, создать_урок, зачислить
from lms_frappe_app.api import student


class IntegrationTestArtifactsPage(IntegrationTestCase):
	"""Страница «Мои документы»: кто и что на ней видит."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"page-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.курс = зачислить(self.ученик, self.урок)
		frappe.get_doc(
			{
				"doctype": "Agent Course Artifact",
				"course": self.курс,
				"slug": "summary",
				"title": "Резюме проекта",
				"blocks": [
					{"block_key": "goal", "title": "Цель", "hint": "Одной фразой"},
					{"block_key": "sponsor", "title": "Спонсор"},
				],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(self.ученик)
		student.update_artifact(self.курс, "summary", "goal", "Открыть **седьмую** кофейню")
		frappe.set_user("Administrator")

	def сведения_для(self, пользователь: str, **параметры) -> dict:
		from lms_frappe_app.www.artifacts import сведения

		frappe.set_user(пользователь)
		return сведения(пользователь, **параметры)

	def test_гость_получает_приглашение_войти(self):
		с = self.сведения_для("Guest")

		self.assertTrue(с["is_guest"])
		self.assertEqual(с["courses"], [])
		self.assertIn("redirect-to=/artifacts", с["login_url"])

	def test_ученик_видит_курс_с_документами_и_заполненностью(self):
		с = self.сведения_для(self.ученик)

		курс = next(к for к in с["courses"] if к["id"] == self.курс)
		self.assertEqual(
			[(а["artifact"], а["blocks_filled"], а["blocks_total"]) for а in курс["artifacts"]],
			[("summary", 1, 2)],
		)

	def test_документ_показывает_блоки_разметкой_и_подсказками(self):
		с = self.сведения_для(self.ученик, course=self.курс, artifact="summary")

		блоки = с["document"]["blocks"]
		self.assertIn("<strong>седьмую</strong>", блоки[0]["html"])
		self.assertEqual(блоки[1]["html"], "")
		self.assertEqual(блоки[1]["hint"], "")  # у спонсора подсказки нет
		self.assertIn("artifact=summary", с["document"]["download_url"])

	def test_чужой_документ_не_показывается(self):
		"""Коллега по курсу видит свой пустой документ, а не чужой текст."""
		коллега = создать_ученика(f"page-b-{frappe.generate_hash(length=6)}@example.com")
		зачислить(коллега, self.урок)

		с = self.сведения_для(коллега, course=self.курс, artifact="summary")

		self.assertEqual([б["content"] for б in с["document"]["blocks"]], ["", ""])

	def test_чужой_курс_и_неизвестный_документ_дают_пустую_страницу(self):
		посторонний = создать_ученика(f"page-c-{frappe.generate_hash(length=6)}@example.com")

		self.assertTrue(self.сведения_для(посторонний, course=self.курс, artifact="summary")["missing"])
		self.assertTrue(self.сведения_для(self.ученик, course=self.курс, artifact="lean_canvas")["missing"])

	def test_курс_без_документов_в_списке_не_показывается(self):
		одинокий = создать_ученика(f"page-d-{frappe.generate_hash(length=6)}@example.com")
		зачислить(одинокий, создать_урок(f"Без документов {frappe.generate_hash(length=6)}"))

		self.assertEqual(self.сведения_для(одинокий)["courses"], [])

	def test_markdown_собирается_одним_файлом(self):
		from lms_frappe_app.www.artifacts import собрать_markdown

		с = self.сведения_для(self.ученик, course=self.курс, artifact="summary")
		текст = собрать_markdown(с["document"])

		self.assertTrue(текст.startswith("# Резюме проекта\n"))
		self.assertIn("## Цель\n\nОткрыть **седьмую** кофейню", текст)
		self.assertIn("## Спонсор\n\n_Не заполнено._", текст)

	def test_пункт_сайдбара_ставится_один_раз(self):
		from lms_frappe_app.install import обеспечить_пункты_сайдбара

		frappe.set_user("Administrator")
		обеспечить_пункты_сайдбара()
		обеспечить_пункты_сайдбара()
		пункты = frappe.get_all(
			"LMS Sidebar Item",
			{"parenttype": "LMS Settings", "parentfield": "sidebar_items", "route": "artifacts-sidebar"},
			["title", "web_page"],
		)
		self.assertEqual(len(пункты), 1)
		self.assertEqual(пункты[0].title, "Мои документы")
		self.assertFalse(frappe.db.get_value("Web Page", пункты[0].web_page, "published"))

	def test_маршрут_пункта_ведёт_на_страницу(self):
		редиректы = {п["source"]: п["target"] for п in frappe.get_hooks("website_redirects")}
		self.assertEqual(редиректы.get("/artifacts-sidebar"), "/artifacts")
