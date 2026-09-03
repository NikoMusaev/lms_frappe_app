# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Изоляция на том же пути, по которому идут настоящие запросы.

`Why:` прежние тесты изоляции ходили через `frappe.get_list`, а код —
через `frappe.get_all`, то есть `get_list(ignore_permissions=True)`. Права к
нему не применяются никогда, и десять зелёных тестов соседствовали с
работающей утечкой. Здесь всё проверяется вызовом методов API и прямым
обращением к записям, как это делает настоящий агент.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.errors import Отказ
from lms_frappe_app.agent_learning.sample_data import (
	добавить_в_организацию,
	создать_вопрос,
	создать_занятие,
	создать_квиз,
	создать_менеджера,
	создать_организацию,
	создать_ученика,
	создать_урок,
	зачислить,
)
from lms_frappe_app.api import manager, student


class IntegrationTestApiIsolation(IntegrationTestCase):
	"""Чужое недоступно ни методом, ни прямой записью."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)

		self.компания_а = создать_организацию(f"Компания А {суффикс}")
		self.компания_б = создать_организацию(f"Компания Б {суффикс}")
		self.ученик = создать_ученика(f"i-a-{суффикс}@example.com")
		self.чужой = создать_ученика(f"i-b-{суффикс}@example.com")
		добавить_в_организацию(self.ученик, self.компания_а)
		добавить_в_организацию(self.чужой, self.компания_б)

		self.урок = создать_урок(f"Урок {суффикс}")
		self.вопрос = создать_вопрос("Столица?", варианты=[("Москва", True), ("Тула", False)])
		создать_квиз(self.урок, [self.вопрос])
		# Оба зачислены: квиз проверяет доступ к курсу, и без зачисления
		# тесты изоляции падали бы по другой причине, чем проверяют.
		зачислить(self.ученик, self.урок)
		зачислить(self.чужой, self.урок)
		self.чужое_занятие = создать_занятие(self.чужой, self.урок)

	# --- отчётность ---

	def test_рядовой_ученик_не_получает_чужие_подробности(self):
		frappe.set_user(self.ученик)
		ответ = manager.student_detail(self.чужой)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], manager.ЧУЖОЙ_УЧЕНИК)

	def test_менеджер_не_получает_ученика_чужой_компании(self):
		менеджер = создать_менеджера(
			f"i-m-{frappe.generate_hash(length=6)}@example.com", self.компания_а
		)
		frappe.set_user(менеджер)

		ответ = manager.student_detail(self.чужой)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], manager.ЧУЖОЙ_УЧЕНИК)

	def test_менеджер_получает_своего_ученика(self):
		менеджер = создать_менеджера(
			f"i-m2-{frappe.generate_hash(length=6)}@example.com", self.компания_а
		)
		frappe.set_user(менеджер)

		ответ = manager.student_detail(self.ученик)

		self.assertTrue(ответ["ok"])
		self.assertEqual(ответ["data"]["user"], self.ученик)

	# --- чужое занятие и чужая попытка ---

	def test_чекпоинт_в_чужое_занятие_отклоняется(self):
		frappe.set_user(self.ученик)
		ответ = student.report_checkpoint(self.чужое_занятие, "не моё занятие")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЧУЖОЕ_ЗАНЯТИЕ)

	def test_квиз_по_чужому_занятию_не_начинается(self):
		# Иначе можно сжечь чужую попытку — они лимитированы.
		frappe.set_user(self.ученик)
		ответ = student.request_quiz(self.чужое_занятие)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЧУЖОЕ_ЗАНЯТИЕ)

	def test_ответ_в_чужую_попытку_отклоняется(self):
		frappe.set_user(self.чужой)
		чужая_попытка = student.request_quiz(self.чужое_занятие)["data"]["attempt"]

		frappe.set_user(self.ученик)
		ответ = student.submit_answer(чужая_попытка, self.вопрос, "1")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЧУЖОЕ_ЗАНЯТИЕ)

	# --- прямая запись мимо методов ---

	def test_ученик_не_может_править_свою_попытку_напрямую(self):
		"""Главное: иначе зачёт ставится без единого ответа.

		Проверено эксплуатацией до починки — PUT со `score` проходил.
		"""
		frappe.set_user(self.чужой)
		попытка = student.request_quiz(self.чужое_занятие)["data"]["attempt"]

		self.assertFalse(
			frappe.has_permission("Agent Quiz Attempt", "write", doc=попытка, user=self.чужой)
		)

	def test_ученик_не_может_создать_себе_членство(self):
		# Иначе он вписывается в любую компанию и получает её курсы.
		frappe.set_user(self.ученик)
		членство = frappe.get_doc(
			{
				"doctype": "Organization Membership",
				"user": self.ученик,
				"organization": self.компания_б,
				"role": "Manager",
			}
		)
		self.assertFalse(
			frappe.has_permission("Organization Membership", "create", doc=членство)
		)

	def test_ученик_не_может_править_назначения(self):
		frappe.set_user(self.ученик)
		self.assertFalse(frappe.has_permission("Course Allocation", "write"))
		self.assertFalse(frappe.has_permission("Course Allocation", "create"))

	def test_ученик_не_может_править_своё_занятие(self):
		своё = создать_занятие(self.ученик, self.урок)
		frappe.set_user(self.ученик)
		self.assertFalse(
			frappe.has_permission("Agent Learning Session", "write", doc=своё)
		)

	def test_чужая_попытка_не_читается_даже_по_имени(self):
		frappe.set_user(self.чужой)
		чужая = student.request_quiz(self.чужое_занятие)["data"]["attempt"]

		frappe.set_user(self.ученик)
		self.assertFalse(frappe.has_permission("Agent Quiz Attempt", "read", doc=чужая))

	def test_чтение_остаётся_доступным(self):
		# Урезание прав не должно сломать обычную работу.
		frappe.set_user(self.ученик)
		self.assertTrue(frappe.has_permission("Agent Learning Session", "read"))
		self.assertTrue(student.list_my_courses()["ok"])


class IntegrationTestQuizAnswerLeak(IntegrationTestCase):
	"""Ответы квиза — только свои, даже руководителю.

	`Why:` в записи ответа лежит текст ответа рядом с признаком верности —
	готовый эталон. Руководитель нередко проходит тот же курс, что и его
	сотрудники: чтение чужих ответов дало бы ему ответы на собственный квиз.
	"""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.компания = создать_организацию(f"Компания {суффикс}")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.вопрос = создать_вопрос("Столица?", варианты=[("Москва", True), ("Тула", False)])
		создать_квиз(self.урок, [self.вопрос])

		self.сотрудник = создать_ученика(f"emp-{суффикс}@example.com")
		добавить_в_организацию(self.сотрудник, self.компания)
		зачислить(self.сотрудник, self.урок)
		self.руководитель = создать_менеджера(f"boss-{суффикс}@example.com", self.компания)

		frappe.set_user(self.сотрудник)
		попытка = student.request_quiz(создать_занятие(self.сотрудник, self.урок))["data"]
		student.submit_answer(попытка["attempt"], self.вопрос, "1")
		frappe.set_user("Administrator")

	def test_записи_ответов_не_читает_никто_кроме_служебных_ролей(self):
		"""Ни руководитель, ни сам ученик: вердикт приходит из метода.

		Записи ответов вообще не выставлены наружу — так утечка невозможна не
		по фильтру, а по отсутствию права. Руководителю агрегаты доступны
		методом отчётности, где текстов ответов нет.
		"""
		for кто in (self.руководитель, self.сотрудник):
			frappe.set_user(кто)
			self.assertFalse(
				frappe.has_permission("Agent Quiz Answer", "read"),
				f"{кто} получил доступ к записям ответов",
			)

	def test_руководитель_видит_результат_но_не_ответы(self):
		frappe.set_user(self.руководитель)
		данные = manager.student_detail(self.сотрудник)["data"]

		self.assertTrue(данные["quiz_attempts"], "итоги попыток руководителю нужны")
		выдано = json.dumps(данные, ensure_ascii=False, default=str)
		self.assertNotIn("Москва", выдано)
		self.assertNotIn("is_correct", выдано)
