# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Регрессия на утечку эталонов.

Прогоняет **все** методы контракта и ищет в ответах то, чего там быть не
может. Дёшево и ловит самый дорогой класс ошибок: утечка эталона обесценивает
серверный квиз целиком, а с ним и устойчивость схемы к пересказу директивы
агентом.

Проверка намеренно тупая — поиск подстрок по всему JSON. Умная проверка
пропустит поле, добавленное завтра.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.leak_guards import проверить_ответ
from lms_frappe_app.agent_learning.sample_data import (
	добавить_в_организацию,
	создать_вопрос,
	создать_квиз,
	создать_менеджера,
	создать_организацию,
	создать_ученика,
	создать_урок,
)
from lms_frappe_app.api import manager, student

ПРАВИЛЬНЫЙ_ВАРИАНТ = "Москва"
НЕВЕРНЫЙ_ВАРИАНТ = "Тула"
ТЕКСТ_ПОЯСНЕНИЯ = "Столицей она стала в пятнадцатом веке"


class IntegrationTestNoLeak(IntegrationTestCase):
	"""Ни один метод не отдаёт эталон и не протекает структурами Frappe."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)

		self.ученик = создать_ученика(f"leak-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.курс = frappe.db.get_value(
			"Course Chapter", frappe.db.get_value("Course Lesson", self.урок, "chapter"), "course"
		)
		self.вопрос = создать_вопрос(
			"Столица России?",
			варианты=[(ПРАВИЛЬНЫЙ_ВАРИАНТ, True), (НЕВЕРНЫЙ_ВАРИАНТ, False)],
			пояснение=ТЕКСТ_ПОЯСНЕНИЯ,
		)
		создать_квиз(self.урок, [self.вопрос])

		frappe.get_doc(
			{
				"doctype": "Agent Lesson Directive",
				"lesson": self.урок,
				"teaching_directive": "Спросить, какие города ученик считает столицами",
				"success_criteria": "Называет верно",
			}
		).insert(ignore_permissions=True)

		self.организация = создать_организацию(f"Компания {суффикс}")
		добавить_в_организацию(self.ученик, self.организация)
		frappe.get_doc(
			{
				"doctype": "Course Allocation",
				"organization": self.организация,
				"course": self.курс,
				"deadline": "2026-12-31",
			}
		).insert(ignore_permissions=True)
		self.менеджер = создать_менеджера(f"leakmg-{суффикс}@example.com", self.организация)

	def проверить(self, что: str, ответ) -> str:
		"""Ответ без эталонов, внутренностей Frappe и текста пояснения.

		Текст проверяется отдельно от имён полей: утечка вида
		`{"hint": <текст пояснения>}` мимо проверки имён проходит.
		"""
		return проверить_ответ(self, ответ, что, запрещённые_тексты=(ТЕКСТ_ПОЯСНЕНИЯ,))

	def test_ни_один_метод_ученика_не_отдаёт_эталон(self):
		frappe.set_user(self.ученик)

		self.проверить("list_my_courses", student.list_my_courses())
		self.проверить("get_my_progress", student.get_my_progress())

		урок = student.start_lesson()
		выдано = self.проверить("start_lesson", урок)
		# Директива в start_lesson быть обязана — она адресована агенту.
		self.assertIn("Спросить, какие города", выдано)

		занятие = урок["data"]["session"]
		self.проверить("report_checkpoint", student.report_checkpoint(занятие, "разобрали"))

		квиз = student.request_quiz(занятие)
		выдано = self.проверить("request_quiz", квиз)
		# Варианты видны, а какой из них верный — нет.
		self.assertIn(ПРАВИЛЬНЫЙ_ВАРИАНТ, выдано)
		self.assertIn(НЕВЕРНЫЙ_ВАРИАНТ, выдано)

		попытка = квиз["data"]["attempt"]
		ответ = student.submit_answer(попытка, self.вопрос, "2")
		self.проверить("submit_answer", ответ)
		# Неверный ответ не должен подсказывать верный: проверку текста
		# пояснения делает `проверить`.
		self.assertFalse(ответ["data"]["verdict"]["correct"])

	def test_пояснение_приходит_только_к_верному_ответу(self):
		frappe.set_user(self.ученик)
		занятие = student.start_lesson()["data"]["session"]
		попытка = student.request_quiz(занятие)["data"]["attempt"]

		ответ = student.submit_answer(попытка, self.вопрос, "1")

		self.assertTrue(ответ["data"]["verdict"]["correct"])
		self.assertIn(ТЕКСТ_ПОЯСНЕНИЯ, ответ["data"]["verdict"]["explanation"])

	def test_ни_один_метод_руководителя_не_отдаёт_эталон(self):
		frappe.set_user(self.ученик)
		занятие = student.start_lesson()["data"]["session"]
		попытка = student.request_quiz(занятие)["data"]["attempt"]
		student.submit_answer(попытка, self.вопрос, "1")

		frappe.set_user(self.менеджер)

		self.проверить("org_report", manager.org_report())
		self.проверить("student_detail", manager.student_detail(self.ученик))

	def test_отчёт_руководителя_не_несёт_ответов_ученика(self):
		# Отчёт про результат, а не про содержание диалога.
		frappe.set_user(self.ученик)
		занятие = student.start_lesson()["data"]["session"]
		student.report_checkpoint(занятие, "ученик перепутал столицу с крупнейшим городом")
		попытка = student.request_quiz(занятие)["data"]["attempt"]
		student.submit_answer(попытка, self.вопрос, "2")

		frappe.set_user(self.менеджер)
		# Реплика ученика из журнала — то, что отчёт не имеет права раскрывать.
		# Прежняя проверка искала здесь текст варианта ответа, которого в
		# записи не бывает: ответ хранится номером.
		проверить_ответ(
			self,
			manager.student_detail(self.ученик),
			"student_detail",
			запрещённые_тексты=("перепутал столицу",),
		)
