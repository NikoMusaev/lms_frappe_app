# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Замечания автора: адрес места, переходы статуса и чей ход.

`Why:` петля «увидел → агент поправил → принял» держится на трёх правилах:
замечание указывает точное место, агент не принимает замечания за автора, а
автор не отмечает их сделанными за агента; очередь строится по тому, чьё
слово последнее (lms-high-time/learning-services#266).
"""

from frappe.tests import UnitTestCase

from lms_frappe_app.agent_learning.errors import Отказ
from lms_frappe_app.agent_learning.notes import (
	НЕВЕРНЫЙ_АДРЕС,
	НЕДОПУСТИМЫЙ_ПЕРЕХОД,
	группа,
	ждёт,
	проверить_переход,
	разобрать_адрес,
)

ПОЛЯ_УРОКА = ("objectives", "teaching_directive")
ПОЛЯ_КУРСА = ("glossary", "teaching_directive")


def адрес(target: str, lesson: str | None = None) -> dict:
	return разобрать_адрес(target, lesson, ПОЛЯ_УРОКА, ПОЛЯ_КУРСА)


class TestNoteTargets(UnitTestCase):
	def test_адреса_разбираются_по_видам(self):
		случаи = {
			("course", None): {"kind": "course", "key": None},
			("course_directive.glossary", None): {"kind": "course_directive", "key": "glossary"},
			("lesson", "L-1"): {"kind": "lesson", "key": None},
			("material", "L-1"): {"kind": "material", "key": None},
			("directive.teaching_directive", "L-1"): {"kind": "directive", "key": "teaching_directive"},
			("question.QTS-2026-00213", "L-1"): {"kind": "question", "key": "QTS-2026-00213"},
			("block. Register/RISKS", None): {"kind": "block", "key": "register/risks"},
			("block.register/risks", "L-1"): {"kind": "block", "key": "register/risks"},
			("map.T1_4", None): {"kind": "map", "key": "T1_4"},
		}
		for (target, lesson), ожидаемое in случаи.items():
			with self.subTest(target=target):
				self.assertEqual(адрес(target, lesson), ожидаемое)

	def test_неверный_адрес_отклоняется_с_местом(self):
		случаи = {
			("", None): "target",
			("chapter", None): "target",
			("directive.nope", "L-1"): "target",
			("directive.", "L-1"): "target",
			("course_directive.objectives", None): "target",
			("question.", "L-1"): "target",
			("block.register", None): "target",
			("block./risks", None): "target",
			("map.", None): "target",
			("material", None): "lesson",
			("directive.objectives", None): "lesson",
			("question.QTS-1", None): "lesson",
			("course", "L-1"): "lesson",
			("course_directive.glossary", "L-1"): "lesson",
		}
		for (target, lesson), место in случаи.items():
			with self.subTest(target=target, lesson=lesson):
				with self.assertRaises(Отказ) as пойманный:
					адрес(target, lesson)
				self.assertEqual(пойманный.exception.код, НЕВЕРНЫЙ_АДРЕС)
				self.assertEqual(пойманный.exception.подробности["where"], место)


class TestNoteTransitions(UnitTestCase):
	def test_допустимые_переходы(self):
		for было, стало, via, текст in (
			("open", "done", "agent", "Переписал шаг 3"),
			("done", "accepted", "author", None),
			("open", "accepted", "author", None),
			("done", "open", "author", "Пример всё ещё про кафе"),
			("accepted", "open", "author", "Всплыло снова"),
		):
			with self.subTest(было=было, стало=стало, via=via):
				проверить_переход(было, стало, via, текст)

	def test_недопустимые_переходы(self):
		for было, стало, via, текст in (
			("done", "accepted", "agent", None),
			("open", "accepted", "agent", None),
			("open", "done", "author", "Сам поправил"),
			("open", "done", "agent", None),
			("open", "done", "agent", "   "),
			("done", "open", "author", None),
			("accepted", "open", "author", ""),
			("open", "open", "author", "Ещё раз"),
			("done", "done", "agent", "Ещё раз"),
			("accepted", "done", "agent", "Сделал"),
			("open", "closed", "author", None),
			("open", "done", "robot", "Сделал"),
		):
			with self.subTest(было=было, стало=стало, via=via, текст=текст):
				with self.assertRaises(Отказ) as пойманный:
					проверить_переход(было, стало, via, текст)
				self.assertEqual(пойманный.exception.код, НЕДОПУСТИМЫЙ_ПЕРЕХОД)


class TestWhoseTurn(UnitTestCase):
	def ответ(self, via: str) -> dict:
		return {"via": via, "text": "…"}

	def test_чей_ход(self):
		случаи = (
			("open", "author", [], "agent"),
			("open", "agent", [], "author"),
			("open", "author", [self.ответ("agent")], "author"),
			("open", "agent", [self.ответ("author")], "agent"),
			("open", "author", [self.ответ("agent"), self.ответ("author")], "agent"),
			("done", "author", [self.ответ("agent")], "author"),
			("accepted", "author", [self.ответ("author")], None),
		)
		for статус, via, ответы, ожидаемое in случаи:
			with self.subTest(статус=статус, via=via, ответов=len(ответы)):
				self.assertEqual(ждёт(статус, via, ответы), ожидаемое)

	def test_группа_очереди(self):
		self.assertEqual(группа("done", "author"), "check")
		self.assertEqual(группа("open", "author"), "question")
		self.assertEqual(группа("open", "agent"), "agent")
		self.assertEqual(группа("accepted", None), "accepted")
