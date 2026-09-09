# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.sample_data import (
	привязать_урок,
	создать_курс,
	создать_занятие,
	зачислить,
	добавить_в_организацию,
	создать_вопрос,
	создать_квиз,
	создать_организацию,
	создать_ученика,
	создать_урок,
	сдать_отчёт,
)
from lms_frappe_app.agent_learning.access import (
	НЕ_ЗАЧИСЛЕН,
	КУРС_НЕ_ОПУБЛИКОВАН,
	КУРС_НЕ_ОТКРЫТ,
	УЖЕ_ЗАПИСАН,
)
from lms_frappe_app.api import student

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

	def test_директива_курса_приходит_отдельным_полем(self):
		frappe.get_doc(
			{
				"doctype": "Agent Course Directive",
				"course": self.курс,
				"objectives": "Вести проект по системе",
				"teaching_directive": "Разбирай всё на проекте ученика",
				"student_profile": "Руководители малого бизнеса",
				"glossary": "Цикл — месяц работы проекта",
			}
		).insert(ignore_permissions=True)

		данные = student.start_lesson()["data"]

		self.assertEqual(данные["course_objectives"], ["Вести проект по системе"])
		self.assertEqual(данные["course_directive"]["audience"], "teacher_only")
		self.assertIn("Разбирай всё", данные["course_directive"]["teaching_directive"])
		self.assertEqual(данные["course_directive"]["glossary"], ["Цикл — месяц работы проекта"])

	def test_курс_без_директивы_не_ломает_урок(self):
		# Директива курса необязательна: урок обязан открываться и без неё.
		данные = student.start_lesson()["data"]

		self.assertIsNone(данные["course_directive"])
		self.assertEqual(данные["course_objectives"], [])

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
		сдать_отчёт(занятие)
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
		сдать_отчёт(занятие)
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

	# --- кто вошёл ---

	def test_whoami_называет_учётную_запись_и_организацию(self):
		"""Без этого «вошёл не тем аккаунтом» неотличимо от «нет курсов»."""
		данные = student.whoami()["data"]

		self.assertEqual(данные["login"], self.ученик)
		self.assertEqual(
			[(о["id"], о["role"]) for о in данные["organizations"]],
			[(self.организация, "Member")],
		)
		self.assertFalse(данные["organizations"][0]["suspended"])

	def test_whoami_не_несёт_ролей_frappe(self):
		# Роли — внутреннее устройство платформы, агенту они ни к чему.
		выдано = json.dumps(student.whoami(), ensure_ascii=False, default=str)

		for поле in ("roles", "LMS Student", "System Manager", "doctype"):
			self.assertNotIn(поле, выдано)

	# --- контекст ученика ---

	def test_start_lesson_отдаёт_заметки_об_ученике(self):
		student.remember(kind="fact", key="role", text="Директор")

		контекст = student.start_lesson()["data"]["student_context"]

		self.assertEqual([ф["key"] for ф in контекст["facts"]], ["role"])
		self.assertEqual(контекст["carried_over"], [])

	def test_заметки_приходят_вне_директивной_рамки(self):
		"""Ученику они доступны, грифа «не показывать» на них нет."""
		student.remember(kind="fact", key="role", text="Директор")

		данные = student.start_lesson()["data"]

		self.assertNotIn("Директор", json.dumps(данные["directive"], ensure_ascii=False))
		self.assertIn("Директор", json.dumps(данные["student_context"], ensure_ascii=False))

	# --- заметки об ученике ---

	def test_заметка_замещается_по_ключу(self):
		student.remember(kind="fact", key="role", text="Директор агентства")
		student.remember(kind="fact", key="Role", text="Совладелец агентства")

		факты = student.my_notes()["data"]["facts"]

		self.assertEqual(
			[(ф["key"], ф["text"]) for ф in факты],
			[("role", "Совладелец агентства")],
			"ключ нормализуется, а запись по нему замещается, а не удваивается",
		)

	def test_наблюдение_живёт_при_курсе_и_помнит_занятие(self):
		занятие = student.start_lesson()["data"]["session"]

		student.remember(
			kind="observation", key="pace", text="Торопится", session=занятие
		)

		запись = frappe.get_doc(
			"Agent Student Note", {"student": self.ученик, "note_key": "pace"}
		)
		self.assertEqual(запись.course, self.курс)
		self.assertEqual(запись.source_session, занятие)
		self.assertEqual(запись.kind, "Observation")

	def test_наблюдение_без_занятия_отклоняется(self):
		ответ = student.remember(kind="observation", key="pace", text="Торопится")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЧУЖОЕ_ЗАНЯТИЕ)

	def test_неизвестный_вид_заметки_отклоняется(self):
		ответ = student.remember(kind="мнение", key="pace", text="Торопится")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.НЕИЗВЕСТНЫЙ_ВИД)

	def test_лимит_заметок_упирается_в_предел(self):
		for номер in range(student.ЛИМИТ_ЗАМЕТОК):
			student.remember(kind="fact", key=f"k{номер}", text="да")

		ответ = student.remember(kind="fact", key="ещё один", text="да")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ПЕРЕПОЛНЕНО)

	def test_замена_по_ключу_проходит_и_на_пределе(self):
		"""Иначе упор в лимит становится тупиком: заменить тоже нельзя."""
		for номер in range(student.ЛИМИТ_ЗАМЕТОК):
			student.remember(kind="fact", key=f"k{номер}", text="да")

		self.assertTrue(student.remember(kind="fact", key="k0", text="нет")["ok"])

	def test_забытая_заметка_исчезает(self):
		student.remember(kind="fact", key="role", text="Директор")

		self.assertTrue(student.forget(key="role")["ok"])
		self.assertEqual(student.my_notes()["data"]["facts"], [])

	def test_забыть_несуществующее_отклоняется(self):
		ответ = student.forget(key="ничего-такого")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЗАМЕТКА_НЕ_НАЙДЕНА)

	def test_заметки_приходят_с_датами(self):
		student.remember(kind="fact", key="role", text="Директор")

		факт = student.my_notes()["data"]["facts"][0]

		self.assertIsNotNone(факт["since"])
		self.assertIsNotNone(факт["updated"])

	# --- отчёт по целям ---

	def test_отчёт_по_целям_сохраняется(self):
		занятие = student.start_lesson()["data"]["session"]

		ответ = student.report_outcomes(
			занятие,
			outcomes=[
				{"objective": "Понимать цикл", "status": "covered"},
				{"objective": "Уметь читать код", "status": "skipped"},
			],
		)

		self.assertTrue(ответ["ok"])
		документ = frappe.get_doc("Agent Learning Session", занятие)
		self.assertEqual(
			[(с.objective, с.status) for с in документ.outcomes],
			[("Понимать цикл", "covered"), ("Уметь читать код", "skipped")],
			"порядок берётся из директивы, а не из отчёта",
		)

	def test_отчёт_с_пропущенной_целью_отклоняется(self):
		занятие = student.start_lesson()["data"]["session"]

		ответ = student.report_outcomes(
			занятие, outcomes=[{"objective": "Понимать цикл", "status": "covered"}]
		)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЦЕЛИ_НЕ_СОВПАЛИ)
		self.assertEqual(ответ["error"]["missing"], ["Уметь читать код"])

	def test_отчёт_с_чужой_целью_отклоняется(self):
		занятие = student.start_lesson()["data"]["session"]

		ответ = student.report_outcomes(
			занятие,
			outcomes=[
				{"objective": "Понимать цикл", "status": "covered"},
				{"objective": "Уметь читать код", "status": "covered"},
				{"objective": "Выдуманная цель", "status": "covered"},
			],
		)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["unexpected"], ["Выдуманная цель"])

	def test_неизвестный_статус_отклоняется(self):
		занятие = student.start_lesson()["data"]["session"]

		ответ = student.report_outcomes(
			занятие, outcomes=[{"objective": "Понимать цикл", "status": "почти"}]
		)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЦЕЛИ_НЕ_СОВПАЛИ)

	def test_повторный_отчёт_замещает_прежний(self):
		"""Занятие продолжили — отчёт должен обновиться, а не удвоиться."""
		занятие = student.start_lesson()["data"]["session"]
		сдать_отчёт(занятие)

		student.report_outcomes(
			занятие,
			outcomes=[
				{"objective": "Понимать цикл", "status": "covered"},
				{"objective": "Уметь читать код", "status": "touched"},
			],
		)

		документ = frappe.get_doc("Agent Learning Session", занятие)
		self.assertEqual(len(документ.outcomes), 2)
		self.assertEqual(документ.outcomes[1].status, "touched")

	def test_урок_не_закрывается_без_отчёта(self):
		занятие = student.start_lesson()["data"]["session"]

		ответ = student.complete_lesson(занятие)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.НЕТ_ОТЧЁТА)

	def test_квиз_не_начинается_без_отчёта(self):
		frappe.set_user("Administrator")
		создать_квиз(self.урок, [создать_вопрос("Два?", варианты=[("2", True), ("3", False)])])
		frappe.set_user(self.ученик)
		занятие = student.start_lesson()["data"]["session"]

		ответ = student.request_quiz(занятие)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.НЕТ_ОТЧЁТА)

	def _урок_с_квизом(self):
		frappe.set_user("Administrator")
		создать_квиз(self.урок, [создать_вопрос("Два?", варианты=[("2", True), ("3", False)])])
		frappe.set_user(self.ученик)
		return student.start_lesson()["data"]["session"]

	def test_квиз_не_начинается_с_пропущенной_целью(self):
		"""Иначе ученик получает вопрос по теме, которой на занятии не было."""
		занятие = self._урок_с_квизом()
		student.report_outcomes(
			занятие,
			outcomes=[
				{"objective": "Понимать цикл", "status": "covered"},
				{"objective": "Уметь читать код", "status": "skipped"},
			],
		)

		ответ = student.request_quiz(занятие)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЦЕЛИ_ПРОПУЩЕНЫ)
		self.assertEqual(ответ["error"]["skipped"], ["Уметь читать код"])

	def test_разобранная_заново_цель_открывает_квиз(self):
		"""Отказ не тупик: отчёт замещается, и путь вперёд есть."""
		занятие = self._урок_с_квизом()
		student.report_outcomes(
			занятие,
			outcomes=[
				{"objective": "Понимать цикл", "status": "covered"},
				{"objective": "Уметь читать код", "status": "skipped"},
			],
		)

		сдать_отчёт(занятие)

		self.assertTrue(student.request_quiz(занятие)["ok"])

	def test_задетая_вскользь_цель_квиз_не_блокирует(self):
		"""`touched` — разобранная тема, пусть и коротко."""
		занятие = self._урок_с_квизом()
		student.report_outcomes(
			занятие,
			outcomes=[
				{"objective": "Понимать цикл", "status": "covered"},
				{"objective": "Уметь читать код", "status": "touched"},
			],
		)

		self.assertTrue(student.request_quiz(занятие)["ok"])

	def test_после_отчёта_урок_закрывается(self):
		занятие = student.start_lesson()["data"]["session"]
		сдать_отчёт(занятие)

		self.assertTrue(student.complete_lesson(занятие)["ok"])

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


class IntegrationTestCompleteLesson(IntegrationTestCase):
	"""Урок без квиза должен закрываться, урок с квизом — только квизом."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"cl-{суффикс}@example.com")
		self.теория = создать_урок(f"Теория {суффикс}")
		self.курс = зачислить(self.ученик, self.теория)
		# Второй урок того же курса, с квизом.
		глава = frappe.db.get_value("Course Lesson", self.теория, "chapter")
		self.практика = frappe.get_doc(
			{"doctype": "Course Lesson", "title": "Практика", "chapter": глава}
		).insert(ignore_permissions=True).name
		привязать_урок(глава, self.практика)
		вопрос = создать_вопрос("Два плюс два?", варианты=[("4", True), ("5", False)])
		создать_квиз(self.практика, [вопрос])
		frappe.set_user(self.ученик)

	def test_урок_без_квиза_закрывается_и_двигает_прогресс(self):
		"""Иначе ученик застревает на первом же теоретическом уроке.

		Директивы у этого урока нет, значит нет и целей: отчёт не требуется —
		требовать было бы нечего, а отказ загнал бы агента в тупик.
		"""
		занятие = student.start_lesson(lesson=self.теория)["data"]["session"]

		ответ = student.complete_lesson(занятие)["data"]

		self.assertEqual(ответ["session_status"], "Completed")
		self.assertTrue(
			frappe.db.exists(
				"LMS Course Progress",
				{"member": self.ученик, "lesson": self.теория, "status": "Complete"},
			)
		)

	def test_после_закрытия_приходит_следующий_урок(self):
		занятие = student.start_lesson(lesson=self.теория)["data"]["session"]
		student.complete_lesson(занятие)

		следующий = student.start_lesson()["data"]

		self.assertEqual(следующий["lesson"]["id"], self.практика)

	def test_урок_с_обязательным_квизом_так_не_закрыть(self):
		"""Несущее ограничение: иначе метод стал бы обходом проверки."""
		занятие = student.start_lesson(lesson=self.практика)["data"]["session"]

		ответ = student.complete_lesson(занятие)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.НУЖЕН_КВИЗ)
		self.assertFalse(
			frappe.db.exists(
				"LMS Course Progress",
				{"member": self.ученик, "lesson": self.практика, "status": "Complete"},
			)
		)

	def test_курс_проходится_целиком(self):
		# Критерий готовности: оба урока закрыты, курс пройден.
		занятие = student.start_lesson(lesson=self.теория)["data"]["session"]
		student.complete_lesson(занятие)

		практика = student.start_lesson()["data"]
		квиз = student.request_quiz(практика["session"])["data"]
		student.submit_answer(квиз["attempt"], квиз["question"]["id"], "1")

		курс = next(
			к for к in student.list_my_courses()["data"]["courses"] if к["id"] == self.курс
		)
		self.assertEqual(курс["progress"]["lessons_completed"], 2)
		self.assertEqual(курс["progress"]["lessons_total"], 2)
		self.assertIsNone(курс["next_lesson"])

	def test_чужое_занятие_закрыть_нельзя(self):
		frappe.set_user("Administrator")
		чужой = создать_ученика(f"cl-other-{frappe.generate_hash(length=6)}@example.com")
		зачислить(чужой, self.теория)
		чужое = создать_занятие(чужой, self.теория)
		frappe.set_user(self.ученик)

		ответ = student.complete_lesson(чужое)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ЧУЖОЕ_ЗАНЯТИЕ)


class IntegrationTestSelfEnroll(IntegrationTestCase):
	"""Самозапись: частный ученик и сотрудник компании."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"self-{суффикс}@example.com")
		self.урок = создать_урок(f"Открытый {суффикс}")
		self.курс = frappe.db.get_value(
			"Course Chapter", frappe.db.get_value("Course Lesson", self.урок, "chapter"), "course"
		)
		frappe.db.set_value("LMS Course", self.курс, "published", 1)

	def каталог(self):
		return {к["id"] for к in student.list_catalog()["data"]["courses"]}

	def test_частный_ученик_видит_каталог_и_записывается(self):
		frappe.set_user(self.ученик)
		self.assertIn(self.курс, self.каталог())

		ответ = student.enroll(self.курс)["data"]

		self.assertEqual(ответ["course"], self.курс)
		self.assertEqual(ответ["first_lesson"]["id"], self.урок)
		self.assertTrue(
			frappe.db.exists("LMS Enrollment", {"member": self.ученик, "course": self.курс})
		)

	def test_записанный_курс_из_каталога_исчезает(self):
		# Он и так виден в list_my_courses — дублировать незачем.
		frappe.set_user(self.ученик)
		student.enroll(self.курс)
		self.assertNotIn(self.курс, self.каталог())

	def test_повторная_запись_отклоняется(self):
		frappe.set_user(self.ученик)
		student.enroll(self.курс)

		ответ = student.enroll(self.курс)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], УЖЕ_ЗАПИСАН)

	def test_неопубликованный_курс_недоступен(self):
		frappe.db.set_value("LMS Course", self.курс, "published", 0)
		frappe.set_user(self.ученик)

		self.assertNotIn(self.курс, self.каталог())
		self.assertEqual(student.enroll(self.курс)["error"]["code"], КУРС_НЕ_ОПУБЛИКОВАН)

	def test_сотрудник_видит_только_курсы_своей_компании(self):
		"""Обучение идёт за счёт компании: запись на произвольный курс
		каталога тратила бы чужой бюджет."""
		frappe.set_user("Administrator")
		свой = создать_курс(f"Свой {frappe.generate_hash(length=6)}")
		frappe.db.set_value("LMS Course", свой, "published", 1)
		организация = создать_организацию(
			f"Компания {frappe.generate_hash(length=6)}",
			allowed_courses=[{"course": свой}],
		)
		добавить_в_организацию(self.ученик, организация)

		frappe.set_user(self.ученик)
		каталог = self.каталог()

		self.assertIn(свой, каталог)
		self.assertNotIn(self.курс, каталог)
		self.assertEqual(student.enroll(self.курс)["error"]["code"], КУРС_НЕ_ОТКРЫТ)

	def test_компания_без_ограничений_открывает_весь_каталог(self):
		frappe.set_user("Administrator")
		организация = создать_организацию(f"Компания {frappe.generate_hash(length=6)}")
		добавить_в_организацию(self.ученик, организация)

		frappe.set_user(self.ученик)

		self.assertIn(self.курс, self.каталог())


class IntegrationTestCourseOutline(IntegrationTestCase):
	"""Структура курса: агент должен уметь вернуться к пройденному."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"out-{суффикс}@example.com")
		self.первый = создать_урок(f"Первый {суффикс}")
		self.курс = зачислить(self.ученик, self.первый)
		глава = frappe.db.get_value("Course Lesson", self.первый, "chapter")
		self.второй = frappe.get_doc(
			{"doctype": "Course Lesson", "title": "Второй", "chapter": глава}
		).insert(ignore_permissions=True).name
		привязать_урок(глава, self.второй)
		frappe.set_user(self.ученик)

	def test_незакрытая_цель_переносится_на_следующий_урок(self):
		"""Агент следующего занятия должен знать, что осталось подобрать."""
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "Agent Lesson Directive",
				"lesson": self.первый,
				"objectives": "Разобрать основу\nПосчитать сроки",
			}
		).insert(ignore_permissions=True)
		frappe.set_user(self.ученик)

		первое = student.start_lesson(lesson=self.первый)["data"]["session"]
		student.report_outcomes(
			первое,
			outcomes=[
				{"objective": "Разобрать основу", "status": "covered"},
				{"objective": "Посчитать сроки", "status": "skipped"},
			],
		)
		student.complete_lesson(первое)

		перенос = student.start_lesson(lesson=self.второй)["data"]["student_context"][
			"carried_over"
		]

		self.assertEqual(
			[(п["objective"], п["status"]) for п in перенос],
			[("Посчитать сроки", "skipped")],
			"разобранная цель переноситься не должна",
		)
		self.assertEqual(перенос[0]["lesson"], self.первый)

	def уроки(self):
		структура = student.course_outline(self.курс)["data"]
		return [урок for глава in структура["chapters"] for урок in глава["lessons"]]

	def test_структура_показывает_все_уроки_и_текущий(self):
		уроки = self.уроки()

		self.assertEqual([у["id"] for у in уроки], [self.первый, self.второй])
		self.assertTrue(уроки[0]["current"])
		self.assertFalse(уроки[0]["completed"])

	def test_после_прохождения_урок_помечен_пройденным(self):
		student.complete_lesson(student.start_lesson()["data"]["session"])

		уроки = self.уроки()

		self.assertTrue(уроки[0]["completed"])
		self.assertTrue(уроки[1]["current"], "текущим должен стать следующий урок")

	def test_по_структуре_можно_вернуться_к_пройденному(self):
		# Ровно то, ради чего метод и нужен: идентификатор пройденного урока
		# больше неоткуда взять — list_my_courses отдаёт только следующий.
		student.complete_lesson(student.start_lesson()["data"]["session"])

		пройденный = next(у["id"] for у in self.уроки() if у["completed"])
		повтор = student.start_lesson(lesson=пройденный)["data"]

		self.assertEqual(повтор["lesson"]["id"], пройденный)
		self.assertTrue(повтор["content"]["markdown"] is not None)

	def test_повтор_пройденного_не_двигает_прогресс(self):
		student.complete_lesson(student.start_lesson()["data"]["session"])
		до = student.list_my_courses()["data"]["courses"][0]["progress"]

		повтор = student.start_lesson(lesson=self.первый)["data"]
		student.complete_lesson(повтор["session"])

		self.assertEqual(student.list_my_courses()["data"]["courses"][0]["progress"], до)

	def test_структура_чужого_курса_недоступна(self):
		frappe.set_user("Administrator")
		чужой = создать_курс(f"Чужой {frappe.generate_hash(length=6)}")
		frappe.set_user(self.ученик)

		ответ = student.course_outline(чужой)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], НЕ_ЗАЧИСЛЕН)


class IntegrationTestArtifacts(IntegrationTestCase):
	"""Документы курса: ученик собирает их по ходу обучения, агент помогает."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"art-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.курс = зачислить(self.ученик, self.урок)
		self.схема(
			blocks=[
				{"block_key": "goal", "title": "Цель", "hint": "Одной фразой, без клише"},
				{"block_key": "sponsor", "title": "Спонсор"},
			]
		)
		frappe.set_user(self.ученик)

	def схема(self, slug: str = "summary", **поля):
		frappe.set_user("Administrator")
		документ = frappe.get_doc(
			{
				"doctype": "Agent Course Artifact",
				"course": self.курс,
				"slug": slug,
				"title": "Резюме проекта",
				**поля,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(self.ученик)
		return документ

	# --- чтение ---

	def test_без_ключа_перечисляются_документы_с_заполненностью(self):
		перечень = student.artifact(self.курс)["data"]["artifacts"]

		self.assertEqual(
			[(а["artifact"], а["blocks_total"], а["blocks_filled"]) for а in перечень],
			[("summary", 2, 0)],
		)
		self.assertEqual(перечень[0]["layout"], "sections")

	def test_с_ключом_приходят_блоки_с_подсказками(self):
		student.update_artifact(self.курс, "summary", "goal", "Открыть седьмую кофейню")

		документ = student.artifact(self.курс, "summary")["data"]

		self.assertEqual(
			[(б["key"], б["content"]) for б in документ["blocks"]],
			[("goal", "Открыть седьмую кофейню"), ("sponsor", "")],
			"порядок — из схемы; пустой блок приходит без содержимого",
		)
		self.assertEqual(документ["blocks"][0]["hint"], "Одной фразой, без клише")

	def test_неизвестный_документ_отклоняется(self):
		ответ = student.artifact(self.курс, "lean_canvas")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.АРТЕФАКТ_НЕ_НАЙДЕН)

	def test_документы_чужого_курса_недоступны(self):
		frappe.set_user("Administrator")
		чужой = создать_курс(f"Чужой {frappe.generate_hash(length=6)}")
		frappe.set_user(self.ученик)

		ответ = student.artifact(чужой)

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], НЕ_ЗАЧИСЛЕН)

	def test_документы_идут_в_порядке_объявления(self):
		"""Правка схемы не должна переставлять документы местами."""
		self.схема("map", title="Карта результатов", blocks=[{"block_key": "d1", "title": "Р1"}])
		self.схема("summary", blocks=[{"block_key": "goal", "title": "Цель"}])

		перечень = student.artifact(self.курс)["data"]["artifacts"]

		self.assertEqual([а["artifact"] for а in перечень], ["summary", "map"])

	# --- запись ---

	def test_запись_создаёт_экземпляр_и_считает_заполненность(self):
		ответ = student.update_artifact(self.курс, "summary", "goal", "Открыть кофейню")["data"]

		self.assertEqual((ответ["blocks_filled"], ответ["blocks_total"]), (1, 2))
		self.assertTrue(
			frappe.db.exists(
				"Agent Student Artifact",
				{"student": self.ученик, "course": self.курс, "artifact": "summary"},
			)
		)

	def test_повторная_запись_замещает_блок(self):
		student.update_artifact(self.курс, "summary", "goal", "Черновик")
		student.update_artifact(self.курс, "summary", "Goal", "Открыть седьмую кофейню")

		документ = frappe.get_doc(
			"Agent Student Artifact",
			{"student": self.ученик, "course": self.курс, "artifact": "summary"},
		)
		self.assertEqual(
			[(б.block_key, б.content) for б in документ.blocks],
			[("goal", "Открыть седьмую кофейню")],
			"ключ нормализуется, строка замещается, а не удваивается",
		)

	def test_неизвестный_блок_отклоняется(self):
		ответ = student.update_artifact(self.курс, "summary", "budget", "Миллион")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.БЛОК_НЕ_НАЙДЕН)

	def test_пустой_блок_отклоняется(self):
		ответ = student.update_artifact(self.курс, "summary", "goal", "   ")

		self.assertFalse(ответ["ok"])
		self.assertEqual(ответ["error"]["code"], student.ПУСТОЙ_БЛОК)

	def test_блок_исчезнувший_из_схемы_не_теряет_содержимого(self):
		"""Автор правит схему — труд ученика остаётся."""
		student.update_artifact(self.курс, "summary", "sponsor", "Марина")
		self.схема(blocks=[{"block_key": "goal", "title": "Цель"}])

		без_спонсора = student.artifact(self.курс, "summary")["data"]["blocks"]
		self.assertEqual([б["key"] for б in без_спонсора], ["goal"])

		self.схема(
			blocks=[{"block_key": "goal", "title": "Цель"}, {"block_key": "sponsor", "title": "Спонсор"}]
		)
		вернулся = student.artifact(self.курс, "summary")["data"]["blocks"]
		self.assertEqual(вернулся[1]["content"], "Марина")

	def test_запись_помнит_версию_схемы(self):
		student.update_artifact(self.курс, "summary", "goal", "Цель")
		вторая = self.схема(blocks=[{"block_key": "goal", "title": "Цель"}])
		student.update_artifact(self.курс, "summary", "goal", "Уточнённая цель")

		документ = frappe.get_doc(
			"Agent Student Artifact",
			{"student": self.ученик, "course": self.курс, "artifact": "summary"},
		)
		self.assertEqual(документ.schema_version, вторая.name)

	# --- блоки урока ---

	def test_start_lesson_приносит_блоки_своего_урока(self):
		"""Подсказка «сегодня собираем резюме», а не ограничение."""
		frappe.set_user("Administrator")
		глава = frappe.db.get_value("Course Lesson", self.урок, "chapter")
		другой = frappe.get_doc(
			{"doctype": "Course Lesson", "title": "Другой", "chapter": глава}
		).insert(ignore_permissions=True).name
		привязать_урок(глава, другой)
		frappe.set_user(self.ученик)
		self.схема(
			blocks=[
				{"block_key": "goal", "title": "Цель", "lesson": self.урок},
				{"block_key": "sponsor", "title": "Спонсор", "lesson": другой},
			]
		)
		student.update_artifact(self.курс, "summary", "goal", "Открыть кофейню")

		блоки = student.start_lesson(lesson=self.урок)["data"]["artifact_blocks"]

		self.assertEqual(
			[(б["artifact"], б["key"], б["content"]) for б in блоки],
			[("summary", "goal", "Открыть кофейню")],
			"блок другого урока не приходит",
		)

	def test_урок_без_блоков_отдаёт_пустой_список(self):
		self.assertEqual(student.start_lesson(lesson=self.урок)["data"]["artifact_blocks"], [])
