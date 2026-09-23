# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

from urllib.parse import quote

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.api import authoring
from lms_frappe_app.tests.sample_data import политика_по_умолчанию, создать_куратора, создать_ученика


class IntegrationTestAuthorPage(IntegrationTestCase):
	"""Кабинет автора: зеркало курса, собранного агентом (#261)."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(политика_по_умолчанию)
		суффикс = frappe.generate_hash(length=6)
		self.куратор = создать_куратора(f"author-{суффикс}@example.com")
		frappe.set_user(self.куратор)
		self.курс = authoring.create_course(title=f"Кабинет {суффикс}", summary="Для зеркала")["data"]["id"]
		первая = authoring.add_chapter(course=self.курс, title="Рамка")["data"]["id"]
		вторая = authoring.add_chapter(course=self.курс, title="Сборка")["data"]["id"]
		self.материал = "## Первый раздел\n\nТекст с **выделением**.\n\n" + "\n\n".join(["абзац. " * 40] * 4)
		self.уроки = [
			authoring.add_lesson(chapter=первая, title="Первый", body=self.материал)["data"]["id"],
			authoring.add_lesson(chapter=первая, title="Второй", body="")["data"]["id"],
			authoring.add_lesson(chapter=вторая, title="Третий", body="# Третий\n\nТекст.")["data"]["id"],
		]
		authoring.set_directive(
			lesson=self.уроки[0],
			teaching_directive="Начни с проекта.",
			objectives="Цель один\nЦель два",
			success_criteria="Ученик сдал квиз",
		)
		authoring.add_quiz(
			lesson=self.уроки[0],
			passing_percentage=60,
			questions=[
				{
					"text": "Что здесь не так?",
					"options": [
						{"text": "Верно", "correct": True, "explanation": "Потому что."},
						{"text": "Неверно"},
					],
				}
			],
		)
		authoring.set_course_artifact(
			course=self.курс,
			artifact="register",
			title="Реестр",
			blocks=[
				{"key": "risks", "title": "Риски", "hint": "Пять записей", "lesson": self.уроки[0]},
				{"key": "review", "title": "Сверка"},
			],
		)

	def сведения_для(self, пользователь: str, **параметры) -> dict:
		from lms_frappe_app.www.author import сведения

		frappe.set_user(пользователь)
		return сведения(пользователь, **параметры)

	def урок_структуры(self, с: dict, урок: str) -> dict:
		return next(у for г in с["course"]["chapters"] for у in г["lessons"] if у["id"] == урок)

	def test_гость_получает_приглашение_войти(self):
		с = self.сведения_для("Guest")

		self.assertTrue(с["is_guest"])
		self.assertIn("redirect-to=/author", с["login_url"])
		self.assertEqual(с["courses"], [])

	def test_ученику_кабинет_закрыт(self):
		ученик = создать_ученика(f"author-s-{frappe.generate_hash(length=6)}@example.com")

		с = self.сведения_для(ученик, course=self.курс)

		self.assertFalse(с["allowed"])
		self.assertIsNone(с["course"])
		self.assertEqual(с["courses"], [])

	def test_куратор_видит_курсы_других_кураторов(self):
		"""Курсы общие: второй автор видит курс, который собирал первый."""
		коллега = создать_куратора(f"author-b-{frappe.generate_hash(length=6)}@example.com")

		с = self.сведения_для(коллега)

		self.assertIn(self.курс, [к["id"] for к in с["courses"]])

	def test_экран_курса_показывает_наполненность_и_блоки(self):
		с = self.сведения_для(self.куратор, course=self.курс)

		курс = с["course"]
		self.assertEqual(
			курс["counts"], {"lessons": 3, "with_body": 2, "with_directive": 1, "with_quiz": 1}
		)
		self.assertEqual([г["color"] for г in курс["chapters"]], [1, 2])
		первый = self.урок_структуры(с, self.уроки[0])
		self.assertEqual(первый["number"], 1)
		self.assertEqual(первый["blocks"], ["risks"])
		self.assertIn(f"lesson={quote(self.уроки[0])}", первый["url"])
		self.assertEqual(self.урок_структуры(с, self.уроки[2])["number"], 3)
		блоки = курс["artifacts"][0]["blocks"]
		self.assertEqual([(б["key"], б["lesson_title"]) for б in блоки], [("risks", "Первый"), ("review", None)])

	def test_готовность_ссылается_на_урок(self):
		с = self.сведения_для(self.куратор, course=self.курс)

		пустой = [п for п in с["course"]["readiness"]["blocking"] if п.get("lesson") == self.уроки[1]]
		self.assertTrue(пустой, с["course"]["readiness"])
		self.assertEqual(пустой[0]["lesson_title"], "Второй")
		self.assertIn(f"lesson={quote(self.уроки[1])}", пустой[0]["url"])

	def test_экран_урока_целиком(self):
		frappe.db.set_single_value("Agent Learning Settings", "lesson_segment_limit", 300)
		frappe.clear_document_cache("Agent Learning Settings", "Agent Learning Settings")

		с = self.сведения_для(self.куратор, course=self.курс, lesson=self.уроки[0])

		урок = с["lesson"]
		self.assertGreater(len(урок["segments_html"]), 1)
		self.assertIn("<strong>выделением</strong>", урок["segments_html"][0])
		self.assertEqual(урок["facts"]["body_segments"], len(урок["segments_html"]))
		self.assertEqual(урок["directive"]["objectives"], ["Цель один", "Цель два"])
		self.assertEqual(урок["quiz"]["passing_percentage"], 60)
		self.assertEqual(урок["blocks"][0]["key"], "risks")
		self.assertIsNone(урок["prev"])
		self.assertEqual(урок["next"]["id"], self.уроки[1])
		self.assertEqual(урок["chapter_title"], "Рамка")

	def test_соседи_урока_через_границу_главы(self):
		с = self.сведения_для(self.куратор, course=self.курс, lesson=self.уроки[1])

		self.assertEqual(с["lesson"]["prev"]["id"], self.уроки[0])
		self.assertEqual(с["lesson"]["next"]["id"], self.уроки[2])
		self.assertIsNone(с["lesson"]["directive"])
		self.assertEqual(с["lesson"]["segments_html"], [])

	def test_урок_не_из_курса_и_неизвестный_курс_дают_пометку(self):
		чужой_курс = authoring.create_course(title=f"Другой {frappe.generate_hash(length=6)}", summary="к")[
			"data"
		]["id"]

		self.assertTrue(self.сведения_для(self.куратор, course=чужой_курс, lesson=self.уроки[0])["missing"])
		self.assertTrue(self.сведения_для(self.куратор, course="такого-курса-нет")["missing"])
