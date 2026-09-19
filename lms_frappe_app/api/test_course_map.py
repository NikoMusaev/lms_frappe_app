# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.api import public
from lms_frappe_app.api.authoring import КУРС_НЕ_НАЙДЕН
from lms_frappe_app.tests.sample_data import (
	привязать_урок,
	зачислить,
	создать_ученика,
	создать_урок,
)

#: Поля директивы, которым нельзя выходить наружу ни при каком вызывающем.
ЗАКРЫТЫЕ_ПОЛЯ = (
	"teaching_directive",
	"probing_questions",
	"common_misconceptions",
	"success_criteria",
)


class IntegrationTestCourseMap(IntegrationTestCase):
	"""Карта курса — то, что видят гость и зачисленный ученик."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)

		self.ученик = создать_ученика(f"map-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок карты {суффикс}")
		глава = frappe.db.get_value("Course Lesson", self.урок, "chapter")
		self.курс = frappe.db.get_value("Course Chapter", глава, "course")
		frappe.db.set_value("LMS Course", self.курс, "published", 1)

		self.директива = frappe.get_doc(
			{
				"doctype": "Agent Lesson Directive",
				"lesson": self.урок,
				"objectives": "Назвать спонсора проекта\nОтличить проект от операций",
				"teaching_directive": "Начать с примера, не с определения",
				"probing_questions": "Кто принимает решение о запуске?",
				"common_misconceptions": "Проект — это любая работа",
				"success_criteria": "Ученик называет спонсора своими словами",
				"map_icon": "rocket",
			}
		).insert(ignore_permissions=True)

	def карта(self) -> dict:
		return public.course_map(course=self.курс)["data"]

	def test_гость_видит_цели_без_покрытия(self):
		frappe.set_user("Guest")

		уроки = self.карта()["chapters"][0]["lessons"]
		цели = уроки[0]["objectives"]

		self.assertEqual([ц["text"] for ц in цели], ["Назвать спонсора проекта", "Отличить проект от операций"])
		# Ключа нет вовсе: `null` был бы неотличим от «цель не разобрана».
		for цель in цели:
			self.assertNotIn("status", цель)

	def test_зачисленный_видит_своё_покрытие(self):
		зачислить(self.ученик, self.урок)
		frappe.set_user(self.ученик)
		занятие = frappe.get_doc(
			{
				"doctype": "Agent Learning Session",
				"lesson": self.урок,
				"student": self.ученик,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		from lms_frappe_app.api import student

		student.report_outcomes(
			session=занятие.name,
			outcomes=json.dumps(
				[
					{"objective": "Назвать спонсора проекта", "status": "covered"},
					{"objective": "Отличить проект от операций", "status": "touched"},
				]
			),
		)

		цели = self.карта()["chapters"][0]["lessons"][0]["objectives"]

		self.assertEqual(
			{ц["text"]: ц["status"] for ц in цели},
			{"Назвать спонсора проекта": "covered", "Отличить проект от операций": "touched"},
		)

	def test_непубликованный_курс_гостю_отказ(self):
		frappe.db.set_value("LMS Course", self.курс, "published", 0)
		frappe.set_user("Guest")

		ответ = public.course_map(course=self.курс)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], КУРС_НЕ_НАЙДЕН)

	def test_цели_берутся_из_действующей_версии_директивы(self):
		from lms_frappe_app.agent_learning import directives

		directives.записать(
			"Agent Lesson Directive",
			{"lesson": self.урок},
			{"objectives": "Единственная новая цель", "teaching_directive": "Новая версия"},
		)
		frappe.set_user("Guest")

		цели = self.карта()["chapters"][0]["lessons"][0]["objectives"]

		self.assertEqual([ц["text"] for ц in цели], ["Единственная новая цель"])

	def test_порядок_уроков_совпадает_с_программой_learning(self):
		второй = создать_урок(f"Второй урок {frappe.generate_hash(length=4)}")
		глава = frappe.db.get_value("Course Lesson", self.урок, "chapter")
		привязать_урок(глава, второй)
		frappe.set_user("Guest")

		from lms.lms.utils import get_course_outline

		наш = [
			урок["id"]
			for гл in self.карта()["chapters"]
			for урок in гл["lessons"]
		]
		их = [
			урок["name"]
			for гл in get_course_outline(self.курс)
			for урок in гл.get("lessons", [])
		]

		self.assertEqual(наш, их)

	def test_иконка_урока_приходит_из_директивы(self):
		frappe.set_user("Guest")

		урок = self.карта()["chapters"][0]["lessons"][0]

		self.assertEqual(урок["icon"], "rocket")

	def test_тело_директивы_наружу_не_выходит(self):
		frappe.set_user("Guest")

		целиком = json.dumps(self.карта(), ensure_ascii=False)

		for поле in ЗАКРЫТЫЕ_ПОЛЯ:
			self.assertNotIn(поле, целиком)
		self.assertNotIn("Начать с примера", целиком)
		self.assertNotIn("Кто принимает решение", целиком)
