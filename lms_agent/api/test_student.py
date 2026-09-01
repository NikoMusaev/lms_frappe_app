# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_agent.agent_learning.sample_data import (
	зачислить,
	добавить_в_организацию,
	создать_вопрос,
	создать_квиз,
	создать_организацию,
	создать_ученика,
	создать_урок,
)
from lms_agent.api import student

ЭТАЛОННЫЕ_ПОЛЯ = ("is_correct", "possibility", "explanation_")


class IntegrationTestStudentAPI(IntegrationTestCase):
	"""Методы учебного потока — в том виде, в каком их увидит агент."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)

		self.ученик = создать_ученика(f"api-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.курс = frappe.db.get_value(
			"Course Chapter", frappe.db.get_value("Course Lesson", self.урок, "chapter"), "course"
		)
		frappe.db.set_value(
			"Course Lesson",
			self.урок,
			"body",
			"## Циклы\n\nЦикл повторяет действие. {{ YouTubeVideo(abc) }}",
		)
		self.директива = frappe.get_doc(
			{
				"doctype": "Agent Lesson Directive",
				"lesson": self.урок,
				"objectives": "Понимать цикл\nУметь читать код",
				"teaching_directive": "Начать с примера, не с определения",
				"probing_questions": "Что произойдёт при нуле итераций?",
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
				"mandatory": 1,
			}
		).insert(ignore_permissions=True)

		frappe.set_user(self.ученик)

	# --- форма ответа ---

	def test_успех_приходит_в_форме_контракта(self):
		ответ = student.list_my_courses()
		self.assertTrue(ответ["ok"])
		self.assertIn("courses", ответ["data"])

	def test_отказ_приходит_успешным_ответом_с_кодом(self):
		# Ожидаемый отказ не может ехать HTTP-ошибкой: тело ошибки формирует
		# Frappe, и машинного кода в нём не остаётся.
		ответ = student.start_lesson(lesson="такого-урока-нет")
		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.УРОК_НЕ_НАЙДЕН)

	# --- список курсов ---

	def test_курс_приходит_с_дедлайном_и_прогрессом(self):
		курсы = student.list_my_courses()["data"]["courses"]
		мой = next(к for к in курсы if к["id"] == self.курс)

		self.assertEqual(str(мой["deadline"]), "2026-12-31")
		self.assertTrue(мой["mandatory"])
		self.assertEqual(мой["progress"]["lessons_total"], 1)
		self.assertEqual(мой["progress"]["lessons_completed"], 0)
		self.assertEqual(мой["next_lesson"]["id"], self.урок)

	def test_во_внутренностях_frappe_наружу_не_течёт(self):
		# Контракт обязан оставаться интерфейсом общего назначения.
		выдано = json.dumps(student.list_my_courses(), ensure_ascii=False, default=str)
		for поле in ("doctype", "docstatus", "modified_by", "owner"):
			self.assertNotIn(поле, выдано)

	# --- начало урока ---

	def test_урок_отдаётся_с_материалом_целями_и_директивой(self):
		данные = student.start_lesson()["data"]

		self.assertEqual(данные["lesson"]["id"], self.урок)
		self.assertIn("Цикл повторяет действие", данные["content"]["markdown"])
		self.assertEqual(данные["objectives"], ["Понимать цикл", "Уметь читать код"])
		self.assertEqual(данные["directive"]["audience"], "teacher_only")
		self.assertIn("Начать с примера", данные["directive"]["teaching_directive"])

	def test_материал_и_директива_разными_полями(self):
		# Одна из трёх митигаций против пересказа директивы ученику.
		данные = student.start_lesson()["data"]
		self.assertNotIn("Начать с примера", данные["content"]["markdown"])

	def test_макрос_видео_ушёл_в_медиа(self):
		данные = student.start_lesson()["data"]
		self.assertEqual([м["kind"] for м in данные["media"]], ["video"])
		self.assertNotIn("{{", данные["content"]["markdown"])

	def test_занятие_создано_и_помечено_доверенным(self):
		данные = student.start_lesson()["data"]
		занятие = frappe.get_doc("Agent Learning Session", данные["session"])
		self.assertEqual(занятие.student, self.ученик)
		self.assertTrue(занятие.via_trusted_service)

	def test_без_аргумента_берётся_урок_с_ближайшим_дедлайном(self):
		# Ученик, сказавший «давай заниматься», должен получить то, что горит.
		frappe.set_user("Administrator")
		срочный_урок = создать_урок(f"Срочный {frappe.generate_hash(length=6)}")
		срочный_курс = frappe.db.get_value(
			"Course Chapter",
			frappe.db.get_value("Course Lesson", срочный_урок, "chapter"),
			"course",
		)
		frappe.get_doc(
			{
				"doctype": "Course Allocation",
				"organization": self.организация,
				"course": срочный_курс,
				"deadline": "2026-06-30",
				"mandatory": 1,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(self.ученик)

		данные = student.start_lesson()["data"]

		self.assertEqual(данные["lesson"]["id"], срочный_урок)

	# --- квиз через методы ---

	def test_полный_проход_квиза_через_методы(self):
		frappe.set_user("Administrator")
		вопрос = создать_вопрос("Два плюс два?", варианты=[("4", True), ("5", False)])
		создать_квиз(self.урок, [вопрос])
		frappe.set_user(self.ученик)

		занятие = student.start_lesson()["data"]["session"]
		начало = student.request_quiz(занятие)["data"]
		итог = student.submit_answer(начало["attempt"], вопрос, "1")["data"]

		self.assertTrue(итог["verdict"]["correct"])
		self.assertTrue(итог["result"]["passed"])
		self.assertEqual(итог["result"]["session_status"], "Completed")

	def test_в_вопросе_квиза_нет_полей_эталона(self):
		frappe.set_user("Administrator")
		вопрос = создать_вопрос(
			"Столица?", варианты=[("Москва", True), ("Тула", False)], пояснение="Так исторически"
		)
		создать_квиз(self.урок, [вопрос])
		frappe.set_user(self.ученик)

		занятие = student.start_lesson()["data"]["session"]
		выдано = json.dumps(student.request_quiz(занятие), ensure_ascii=False, default=str)

		for поле in ЭТАЛОННЫЕ_ПОЛЯ:
			self.assertNotIn(поле, выдано)
		self.assertNotIn("Так исторически", выдано)

	def test_чекпоинт_пишется_в_журнал(self):
		занятие = student.start_lesson()["data"]["session"]
		student.report_checkpoint(занятие, "разобрали пример с циклом")

		self.assertTrue(
			frappe.db.exists(
				"Agent Session Event", {"session": занятие, "kind": "Checkpoint Reported"}
			)
		)

	# --- чужое ---

	def test_чужое_занятие_отклоняется_машинным_кодом(self):
		# Отказ, а не исключение прав: агенту нужен код, по которому он
		# объяснит ученику происходящее. Проверка идёт по принадлежности
		# занятия, а не по праву чтения — читать чужое занятие вправе ещё и
		# руководитель, но действовать в нём он не должен.
		frappe.set_user("Administrator")
		чужой = создать_ученика(f"other-{frappe.generate_hash(length=6)}@example.com")
		чужое = frappe.get_doc(
			{"doctype": "Agent Learning Session", "student": чужой, "lesson": self.урок}
		).insert(ignore_permissions=True)
		frappe.set_user(self.ученик)

		ответ = student.report_checkpoint(чужое.name, "чужой урок")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЧУЖОЕ_ЗАНЯТИЕ)

	# --- сводка ---

	def test_сводка_считает_курсы_и_последние_занятия(self):
		student.start_lesson()
		сводка = student.get_my_progress()["data"]

		# Ровно один: «не меньше» замаскировало бы утечку чужих зачислений.
		self.assertEqual(сводка["courses_total"], 1)
		self.assertEqual(сводка["courses_overdue"], 0)
		self.assertEqual(сводка["recent_sessions"][0]["lesson"], self.урок)


class IntegrationTestLongLesson(IntegrationTestCase):
	"""Длинный урок: агент должен уметь дочитать его до конца."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"seg-{суффикс}@example.com")
		self.урок = создать_урок(f"Длинный {суффикс}")
		frappe.db.set_value(
			"Course Lesson",
			self.урок,
			"body",
			"\n\n".join(f"## Часть {i}\n\n" + "текст. " * 400 for i in range(4)),
		)
		зачислить(self.ученик, self.урок)
		frappe.set_user(self.ученик)

	def test_урок_режется_на_сегменты(self):
		данные = student.start_lesson(lesson=self.урок)["data"]
		self.assertGreater(данные["content"]["total_segments"], 1)
		self.assertEqual(данные["content"]["segment_index"], 1)

	def test_второй_сегмент_достижим(self):
		# Без параметра сегмента агент видел только начало урока: способа
		# попросить продолжение не было вовсе.
		первый = student.start_lesson(lesson=self.урок)["data"]["content"]["markdown"]
		второй = student.start_lesson(lesson=self.урок, segment=2)["data"]

		self.assertEqual(второй["content"]["segment_index"], 2)
		self.assertNotEqual(второй["content"]["markdown"], первый)

	def test_продолжение_не_плодит_занятия(self):
		# Иначе на один урок копятся незакрытые сессии, которые потом
		# закрывает фоновая задача, засоряя журнал и отчётность.
		первое = student.start_lesson(lesson=self.урок)["data"]["session"]
		второе = student.start_lesson(lesson=self.урок, segment=2)["data"]["session"]
		self.assertEqual(первое, второе)

	def test_номер_за_границами_не_роняет_выдачу(self):
		данные = student.start_lesson(lesson=self.урок, segment=99)["data"]
		self.assertEqual(
			данные["content"]["segment_index"], данные["content"]["total_segments"]
		)
