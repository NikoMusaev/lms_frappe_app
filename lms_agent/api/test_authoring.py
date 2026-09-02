# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Курс, собранный агентом куратора, против трактовки Frappe Learning.

`Why:` авторинг пишет ровно те структуры, чтение которых уже трижды ломалось —
строки порядка глав и уроков. Курс, собранный нашими методами, обязан читаться
самой платформой так же, как собранный руками в интерфейсе; иначе ученик пойдёт
по одной последовательности, а куратор будет видеть другую.
"""

import frappe
from frappe.tests import IntegrationTestCase

from lms_agent.agent_learning.sample_data import создать_куратора, создать_ученика
from lms_agent.agent_learning import quiz
from lms_agent.agent_learning import structure
from lms_agent.agent_learning.structure import уроки_главы
from lms_agent.api import authoring


class IntegrationTestAuthoring(IntegrationTestCase):
	def setUp(self):
		суффикс = frappe.generate_hash(length=6)
		self.куратор = создать_куратора(f"curator-{суффикс}@example.com")
		frappe.set_user(self.куратор)

		self.курс = authoring.create_course(title=f"Курс {суффикс}", summary="Собран агентом")["data"]["id"]
		self.глава = authoring.add_chapter(course=self.курс, title="Глава")["data"]["id"]
		self.уроки = [
			authoring.add_lesson(chapter=self.глава, title=f"Урок {б}", body=f"# {б}")["data"]["id"]
			for б in "ABC"
		]

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_собранный_курс_читается_frappe_learning(self):
		from lms.lms.utils import get_chapters, get_lessons

		self.assertEqual([у["name"] for у in get_lessons(self.курс)], self.уроки)
		self.assertEqual([г["name"] for г in get_chapters(self.курс)], [self.глава])

	def test_перестановка_видна_frappe_learning(self):
		from lms.lms.utils import get_lessons

		новый = [self.уроки[2], self.уроки[0], self.уроки[1]]
		authoring.reorder_lessons(chapter=self.глава, lessons=новый)

		self.assertEqual(уроки_главы(self.глава), новый)
		self.assertEqual([у["name"] for у in get_lessons(self.курс)], новый)

	def test_неполный_список_отклоняется(self):
		"""Агент, забывший урок, иначе молча выкинул бы его из программы."""
		ответ = authoring.reorder_lessons(chapter=self.глава, lessons=self.уроки[:2])

		self.assertEqual(ответ["error"]["code"], "order_mismatch")
		self.assertEqual(уроки_главы(self.глава), self.уроки)

	def test_публикация_блокируется_пока_курс_не_готов(self):
		authoring.update_lesson(lesson=self.уроки[0], body="")

		ответ = authoring.publish_course(course=self.курс)

		self.assertEqual(ответ["error"]["code"], "course_not_ready")
		self.assertIn("empty_lesson", [п["code"] for п in ответ["error"]["problems"]])
		self.assertFalse(frappe.db.get_value("LMS Course", self.курс, "published"))

	def test_кривой_вопрос_не_оставляет_мусора(self):
		"""Отказ отменяет только вопросы этого квиза, но отменяет их все."""
		было = frappe.db.count("LMS Question")

		ответ = authoring.add_quiz(
			lesson=self.уроки[0],
			questions=[
				{"text": "Верный есть", "options": [{"text": "a", "correct": True}, {"text": "b"}]},
				{"text": "Верного нет", "options": [{"text": "a"}, {"text": "b"}]},
			],
		)

		self.assertEqual(ответ["error"]["code"], "invalid_question")
		self.assertEqual(ответ["error"]["question_index"], 2)
		self.assertEqual(frappe.db.count("LMS Question"), было, "остались вопросы от сбойного квиза")
		self.assertIsNone(frappe.db.get_value("Course Lesson", self.уроки[0], "quiz_id"))

	def test_ученик_не_собирает_курсы_и_не_видит_эталонов(self):
		"""Отдельный эндпоинт ничего не защищает — защищает эта проверка."""
		ученик = создать_ученика(f"pupil-{frappe.generate_hash(length=6)}@example.com")
		frappe.set_user(ученик)

		for вызов in (
			lambda: authoring.course_draft(course=self.курс),
			lambda: authoring.add_lesson(chapter=self.глава, title="Свой урок", body="x"),
			lambda: authoring.publish_course(course=self.курс),
			lambda: authoring.set_directive(lesson=self.уроки[0], teaching_directive="x"),
		):
			with self.assertRaises(frappe.PermissionError):
				вызов()


class IntegrationTestAuthoringEdits(IntegrationTestCase):
	"""Правка собранного: без неё сборка через агента разваливается."""

	def setUp(self):
		суффикс = frappe.generate_hash(length=6)
		self.куратор = создать_куратора(f"editor-{суффикс}@example.com")
		frappe.set_user(self.куратор)
		self.курс = authoring.create_course(title=f"Правка {суффикс}", summary="было")["data"]["id"]
		self.глава = authoring.add_chapter(course=self.курс, title="Было")["data"]["id"]
		self.урок = authoring.add_lesson(chapter=self.глава, title="Урок", body="# Урок")["data"]["id"]
		authoring.add_quiz(
			lesson=self.урок,
			questions=[{"text": "Первый?", "options": [{"text": "a", "correct": True}, {"text": "b"}]}],
		)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_курс_находится_по_списку(self):
		"""Без списка идентификатор курса взять негде — все методы требуют его."""
		курсы = authoring.list_courses()["data"]["courses"]

		наш = [курс for курс in курсы if курс["id"] == self.курс]
		self.assertTrue(наш, "созданный курс не виден в списке")
		self.assertFalse(наш[0]["published"])
		self.assertEqual(наш[0]["lessons_total"], 1)

	def test_название_курса_и_главы_правятся(self):
		authoring.update_course(course=self.курс, title="Стало", summary="и описание")
		authoring.update_chapter(chapter=self.глава, title="Стало")

		self.assertEqual(frappe.db.get_value("LMS Course", self.курс, "title"), "Стало")
		self.assertEqual(frappe.db.get_value("Course Chapter", self.глава, "title"), "Стало")

	def test_второй_квиз_на_уроке_отклоняется(self):
		"""`Why:` урок отдаёт агенту ровно один квиз, второй становится
		невидимым мусором — а куратор считает, что заменил вопросы."""
		ответ = authoring.add_quiz(
			lesson=self.урок,
			questions=[{"text": "Другой?", "options": [{"text": "c", "correct": True}, {"text": "d"}]}],
		)

		self.assertEqual(ответ["error"]["code"], "quiz_exists")
		self.assertEqual(frappe.db.count("LMS Quiz", {"lesson": self.урок}), 1)

	def test_вопросы_квиза_добавляются_правятся_и_убираются(self):
		квиз = quiz._квиз_урока(self.урок)
		первый = frappe.get_all("LMS Quiz Question", filters={"parent": квиз}, pluck="question")[0]

		добавлен = authoring.add_question(
			lesson=self.урок,
			question={"text": "Второй?", "options": [{"text": "c", "correct": True}, {"text": "d"}]},
		)["data"]
		self.assertEqual(добавлен["questions_total"], 2)

		authoring.update_question(question=первый, text="Исправленный?")
		self.assertEqual(frappe.db.get_value("LMS Question", первый, "question"), "Исправленный?")

		убран = authoring.remove_question(lesson=self.урок, question=первый)["data"]
		self.assertEqual(убран["questions_total"], 1)
		# Сам вопрос остаётся: на него ссылаются ответы прошлых попыток.
		self.assertTrue(frappe.db.exists("LMS Question", первый))

	def test_варианты_заменяются_целиком(self):
		"""Правка «трёх вариантов на два» не должна оставлять третий."""
		вопрос = frappe.get_all(
			"LMS Quiz Question", filters={"parent": quiz._квиз_урока(self.урок)}, pluck="question"
		)[0]
		authoring.update_question(
			question=вопрос,
			options=[{"text": "1", "correct": True}, {"text": "2"}, {"text": "3"}],
		)

		authoring.update_question(
			question=вопрос, options=[{"text": "новый", "correct": True}, {"text": "другой"}]
		)

		документ = frappe.get_doc("LMS Question", вопрос)
		self.assertEqual(документ.option_1, "новый")
		self.assertIsNone(документ.option_3, "третий вариант остался от прошлой редакции")

	def test_неверная_правка_не_оставляет_вопрос_наполовину(self):
		вопрос = frappe.get_all(
			"LMS Quiz Question", filters={"parent": quiz._квиз_урока(self.урок)}, pluck="question"
		)[0]

		ответ = authoring.update_question(
			question=вопрос, text="Без верного", options=[{"text": "x"}, {"text": "y"}]
		)

		self.assertEqual(ответ["error"]["code"], "invalid_question")
		self.assertEqual(frappe.db.get_value("LMS Question", вопрос, "question"), "Первый?")


class IntegrationTestAuthoringStructure(IntegrationTestCase):
	"""Перенос и удаление: чинят ошибку структуры, но не историю ученика."""

	def setUp(self):
		суффикс = frappe.generate_hash(length=6)
		# Удаление уроков Frappe Learning разрешает только `Moderator`.
		self.куратор = создать_куратора(f"mover-{суффикс}@example.com", роль="Moderator")
		frappe.set_user(self.куратор)
		self.курс = authoring.create_course(title=f"Структура {суффикс}", summary="к")["data"]["id"]
		self.первая = authoring.add_chapter(course=self.курс, title="Первая")["data"]["id"]
		self.вторая = authoring.add_chapter(course=self.курс, title="Вторая")["data"]["id"]
		self.уроки = [
			authoring.add_lesson(chapter=self.первая, title=б, body=f"# {б}")["data"]["id"]
			for б in "ABC"
		]

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_урок_переставляется_внутри_главы(self):
		authoring.move_lesson(lesson=self.уроки[2], position=1)

		self.assertEqual(уроки_главы(self.первая), [self.уроки[2], self.уроки[0], self.уроки[1]])

	def test_урок_переносится_в_другую_главу(self):
		authoring.move_lesson(lesson=self.уроки[0], chapter=self.вторая)

		self.assertEqual(уроки_главы(self.вторая), [self.уроки[0]])
		self.assertNotIn(self.уроки[0], уроки_главы(self.первая))
		# Поле курса переезжает вместе с уроком: иначе он останется числиться
		# в прежнем курсе, а показываться в новом.
		self.assertEqual(frappe.db.get_value("Course Lesson", self.уроки[0], "chapter"), self.вторая)

	def test_лишний_урок_удаляется_целиком(self):
		authoring.add_quiz(
			lesson=self.уроки[1],
			questions=[{"text": "Вопрос?", "options": [{"text": "a", "correct": True}, {"text": "b"}]}],
		)
		квиз = quiz._квиз_урока(self.уроки[1])

		authoring.remove_lesson(lesson=self.уроки[1])

		self.assertNotIn(self.уроки[1], уроки_главы(self.первая))
		self.assertFalse(frappe.db.exists("Course Lesson", self.уроки[1]))
		self.assertFalse(frappe.db.exists("LMS Quiz", квиз), "квиз остался без урока")

	def test_урок_с_прогрессом_не_удаляется(self):
		"""`Why:` стирание урока, по которому занимались, испортило бы историю
		зачётов; курс от лишнего урока не рушится, а история — да."""
		ученик = создать_ученика(f"pupil-{frappe.generate_hash(length=6)}@example.com")
		frappe.get_doc(
			{
				"doctype": "LMS Course Progress",
				"lesson": self.уроки[0],
				"member": ученик,
				"course": self.курс,
				"status": "Complete",
			}
		).insert(ignore_permissions=True)

		ответ = authoring.remove_lesson(lesson=self.уроки[0])

		self.assertEqual(ответ["error"]["code"], "lesson_in_use")
		self.assertEqual(ответ["error"]["progress"], 1)
		self.assertTrue(frappe.db.exists("Course Lesson", self.уроки[0]))

	def test_непустая_глава_не_удаляется(self):
		ответ = authoring.remove_chapter(chapter=self.первая)

		self.assertEqual(ответ["error"]["code"], "chapter_not_empty")
		self.assertTrue(frappe.db.exists("Course Chapter", self.первая))

	def test_пустая_глава_удаляется(self):
		authoring.remove_chapter(chapter=self.вторая)

		self.assertFalse(frappe.db.exists("Course Chapter", self.вторая))
		self.assertNotIn(
			self.вторая, [глава["name"] for глава in structure.главы_курса(self.курс)]
		)


class IntegrationTestAuthoringReadBack(IntegrationTestCase):
	"""Обратное чтение: сверить, что на платформе лежит утверждённый текст."""

	def setUp(self):
		суффикс = frappe.generate_hash(length=6)
		self.куратор = создать_куратора(f"reader-{суффикс}@example.com")
		frappe.set_user(self.куратор)
		self.курс = authoring.create_course(title=f"Чтение {суффикс}", summary="к")["data"]["id"]
		глава = authoring.add_chapter(course=self.курс, title="Глава")["data"]["id"]
		self.материал = "## Заголовок\n\nАбзац с примером.\n\n- пункт\n- ещё пункт\n"
		self.урок = authoring.add_lesson(
			chapter=глава, title="Урок", body=self.материал
		)["data"]["id"]

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_материал_возвращается_дословно(self):
		"""`Why:` иначе сверять собранное с исходником нечем — `course_draft`
		показывает только признак `has_body`."""
		урок = authoring.get_lesson(lesson=self.урок)["data"]

		self.assertEqual(урок["body"], self.материал)
		self.assertEqual(урок["title"], "Урок")

	def test_директива_приходит_действующей_версией(self):
		authoring.set_directive(lesson=self.урок, teaching_directive="Первая редакция")
		authoring.set_directive(
			lesson=self.урок, teaching_directive="Вторая редакция", objectives="Цель"
		)

		директива = authoring.get_lesson(lesson=self.урок)["data"]["directive"]

		self.assertEqual(директива["teaching_directive"], "Вторая редакция")
		self.assertEqual(директива["version"], 2)

	def test_урок_без_директивы_не_ломает_чтение(self):
		урок = authoring.get_lesson(lesson=self.урок)["data"]

		self.assertIsNone(урок["directive"])
		self.assertIsNone(урок["quiz"])

	def test_ученик_не_читает_урок_авторским_методом(self):
		ученик = создать_ученика(f"pupil-{frappe.generate_hash(length=6)}@example.com")
		frappe.set_user(ученик)

		with self.assertRaises(frappe.PermissionError):
			authoring.get_lesson(lesson=self.урок)
