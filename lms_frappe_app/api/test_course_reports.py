# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.api import authoring, student
from lms_frappe_app.api.authoring import КУРС_НЕ_НАЙДЕН
from lms_frappe_app.tests.sample_data import (
	привязать_урок,
	зачислить,
	создать_занятие,
	создать_куратора,
	создать_ученика,
	создать_урок,
)


class IntegrationTestCourseReports(IntegrationTestCase):
	"""Репорты курса глазами куратора.

	Без чтения механизм разомкнут: агент ученика шлёт `report_issue`, а
	посмотреть накопленное некому — обратная связь про курс, который не
	работает, лежит мёртвым грузом (lms-platform#231).
	"""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)

		self.куратор = создать_куратора(f"rep-author-{суффикс}@example.com")
		self.ученик = создать_ученика(f"rep-pupil-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок репортов {суффикс}")
		глава = frappe.db.get_value("Course Lesson", self.урок, "chapter")
		self.курс = frappe.db.get_value("Course Chapter", глава, "course")
		# Урок принадлежит курсу через главу, а `создать_урок` заводит уроку
		# собственный курс: без смены главы репорт по нему уходил бы в чужой
		# курс, и фильтр по уроку возвращал пустоту.
		self.второй_урок = создать_урок(f"Второй урок {суффикс}")
		frappe.db.set_value("Course Lesson", self.второй_урок, "chapter", глава)
		привязать_урок(глава, self.второй_урок)

		frappe.get_doc(
			{
				"doctype": "Agent Lesson Directive",
				"lesson": self.урок,
				"objectives": "Назвать спонсора",
				"teaching_directive": "Начать с примера",
			}
		).insert(ignore_permissions=True)

		зачислить(self.ученик, self.урок)

	def пожаловаться(self, kind: str, text: str, lesson: str | None = None) -> str:
		"""Репорт от имени ученика — тем же путём, каким его шлёт агент."""
		урок = lesson or self.урок
		занятие = создать_занятие(self.ученик, урок)
		frappe.set_user(self.ученик)
		ответ = student.report_issue(session=занятие, kind=kind, text=text)
		frappe.set_user("Administrator")
		return ответ["data"]["report"]

	def test_куратор_видит_репорты_своего_курса(self):
		self.пожаловаться("directive_mismatch", "Слишком напористо, вопросы подряд")
		frappe.set_user(self.куратор)

		репорты = authoring.course_reports(course=self.курс)["data"]["reports"]

		self.assertEqual(len(репорты), 1)
		self.assertEqual(репорты[0]["kind"], "directive_mismatch")
		self.assertEqual(репорты[0]["text"], "Слишком напористо, вопросы подряд")
		self.assertEqual(репорты[0]["lesson"], self.урок)

	def test_репорт_называет_редакцию_директивы_на_момент_жалобы(self):
		"""Претензия к директиве без её редакции нечитаема: курс с тех пор
		переписывали, и непонятно, на что жаловались."""
		self.пожаловаться("directive_mismatch", "Указание не подходит")
		frappe.set_user(self.куратор)

		репорт = authoring.course_reports(course=self.курс)["data"]["reports"][0]

		self.assertTrue(репорт["directive_version"])

	def test_кто_пожаловался_не_отдаётся(self):
		"""`Why:` куратору нужно, что не так с курсом, а не кто сказал. Имя в
		выдаче превращает обратную связь в донос и мешает жаловаться."""
		self.пожаловаться("material_issue", "Материал противоречит сам себе")
		frappe.set_user(self.куратор)

		целиком = frappe.as_json(authoring.course_reports(course=self.курс)["data"])

		self.assertNotIn(self.ученик, целиком)
		self.assertNotIn("student", целиком)

	def test_фильтр_по_виду(self):
		self.пожаловаться("material_issue", "Материал плох")
		self.пожаловаться("directive_mismatch", "Указание не подходит")
		frappe.set_user(self.куратор)

		отобранные = authoring.course_reports(course=self.курс, kind="material_issue")["data"]["reports"]

		self.assertEqual([р["kind"] for р in отобранные], ["material_issue"])

	def test_фильтр_по_уроку(self):
		self.пожаловаться("material_issue", "Про первый урок")
		self.пожаловаться("material_issue", "Про второй урок", lesson=self.второй_урок)
		frappe.set_user(self.куратор)

		отобранные = authoring.course_reports(course=self.курс, lesson=self.второй_урок)["data"]["reports"]

		self.assertEqual([р["text"] for р in отобранные], ["Про второй урок"])

	def test_ученику_метод_закрыт(self):
		"""Роль, а не эндпоинт: агент ученика не должен читать чужие жалобы."""
		self.пожаловаться("stuck", "Застрял")
		frappe.set_user(self.ученик)

		with self.assertRaises(frappe.PermissionError):
			authoring.course_reports(course=self.курс)

	def test_несуществующий_курс_отказывает_доменным_кодом(self):
		frappe.set_user(self.куратор)

		ответ = authoring.course_reports(course="нет-такого-курса")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], КУРС_НЕ_НАЙДЕН)
