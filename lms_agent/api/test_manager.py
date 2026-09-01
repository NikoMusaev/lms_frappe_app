# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_agent.agent_learning.sample_data import (
	добавить_в_организацию,
	создать_занятие,
	создать_менеджера,
	создать_организацию,
	создать_ученика,
	создать_урок,
)
from lms_agent.api import manager


class IntegrationTestManagerAPI(IntegrationTestCase):
	"""Отчётность менеджера: только своя организация, только результаты."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)

		self.компания_а = создать_организацию(f"Компания А {суффикс}")
		self.компания_б = создать_организацию(f"Компания Б {суффикс}")

		self.урок = создать_урок(f"Урок {суффикс}")
		self.курс = frappe.db.get_value(
			"Course Chapter", frappe.db.get_value("Course Lesson", self.урок, "chapter"), "course"
		)

		self.ученик_а = создать_ученика(f"sa-{суффикс}@example.com")
		self.ученик_б = создать_ученика(f"sb-{суффикс}@example.com")
		добавить_в_организацию(self.ученик_а, self.компания_а)
		добавить_в_организацию(self.ученик_б, self.компания_б)

		for организация in (self.компания_а, self.компания_б):
			frappe.get_doc(
				{
					"doctype": "Course Allocation",
					"organization": организация,
					"course": self.курс,
					"deadline": "2026-12-31",
					"mandatory": 1,
				}
			).insert(ignore_permissions=True)

		self.менеджер = создать_менеджера(f"mg-{суффикс}@example.com", self.компания_а)

	def отчёт(self, **аргументы):
		frappe.set_user(self.менеджер)
		return manager.org_report(**аргументы)["data"]["rows"]

	def test_отчёт_показывает_учеников_своей_организации(self):
		строки = self.отчёт()
		self.assertIn(self.ученик_а, {с["user"] for с in строки})

	def test_ученики_чужой_организации_в_отчёт_не_попадают(self):
		строки = self.отчёт()
		self.assertNotIn(self.ученик_б, {с["user"] for с in строки})

	def test_отчёт_несёт_дедлайн_статус_и_долю_пройденного(self):
		строка = next(с for с in self.отчёт() if с["user"] == self.ученик_а)

		self.assertEqual(строка["status"], "not_started")
		self.assertEqual(строка["progress"], 0.0)
		self.assertEqual(str(строка["deadline"]), "2026-12-31")
		self.assertTrue(строка["mandatory"])
		self.assertFalse(строка["overdue"])

	def test_фильтр_по_статусу_отсекает_остальных(self):
		self.assertEqual(self.отчёт(status="completed"), [])
		self.assertTrue(self.отчёт(status="not_started"))

	def test_фильтр_по_курсу(self):
		self.assertTrue(self.отчёт(course=self.курс))
		self.assertEqual(self.отчёт(course="несуществующий-курс"), [])

	def test_менеджер_без_организаций_видит_пустой_отчёт(self):
		# Роль сама по себе не открывает ничего — нужна связка с членством.
		одиночка = создать_ученика(f"lone-{frappe.generate_hash(length=6)}@example.com")
		frappe.get_doc("User", одиночка).add_roles("Organization Manager")

		frappe.set_user(одиночка)

		self.assertEqual(manager.org_report()["data"]["rows"], [])

	def test_подробности_ученика_без_текстов_ответов(self):
		# Отчёт про результат, а не про содержание диалога с агентом.
		занятие = создать_занятие(self.ученик_а, self.урок)
		frappe.get_doc("Agent Learning Session", занятие).записать_событие(
			"Checkpoint Reported", "ученик спросил про вложенные циклы"
		)

		frappe.set_user(self.менеджер)
		данные = manager.student_detail(self.ученик_а)["data"]

		self.assertEqual(данные["user"], self.ученик_а)
		self.assertTrue(данные["sessions"])
		self.assertNotIn("вложенные циклы", json.dumps(данные, ensure_ascii=False, default=str))
