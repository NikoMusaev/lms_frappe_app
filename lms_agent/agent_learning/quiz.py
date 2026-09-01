# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Пошаговый серверный квиз.

Несущее решение всей схемы зачёта: агент работает на стороне ученика и судьёй
быть не может. Сервер выдаёт вопрос, принимает ответ и возвращает вердикт —
**эталон при этом не покидает сервер ни в одном ответе**.

Поэтому утечка директивы урока портит педагогику одного занятия, но не даёт
незаслуженного зачёта: зачёт не зависит от добросовестности агента.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from lms_agent.agent_learning.access import политика_квиза_для_курса
from lms_agent.agent_learning.errors import Отказ
from lms_agent.agent_learning.normalizer import _очистить

#: Frappe Learning хранит варианты плоскими полями option_1..option_10.
ВАРИАНТОВ_МАКСИМУМ = 10

#: Типы вопросов, которые сервер способен проверить сам.
ПРОВЕРЯЕМЫЕ_ТИПЫ = ("Choices", "User Input")

КВИЗА_НЕТ = "quiz_not_configured"
НЕЧЕГО_ПРОВЕРЯТЬ = "quiz_not_checkable"
ПОПЫТКИ_ИСЧЕРПАНЫ = "quiz_attempts_exhausted"
СЛИШКОМ_РАНО = "retry_too_soon"
ПОПЫТКА_ЗАВЕРШЕНА = "attempt_finished"
ЧУЖОЙ_ВОПРОС = "question_mismatch"


# --- начало попытки ---


def начать_попытку(session: str) -> dict:
	"""Создаёт попытку и возвращает первый вопрос."""
	занятие = frappe.get_doc("Agent Learning Session", session)
	квиз = _квиз_урока(занятие.lesson)
	if not квиз:
		raise Отказ(КВИЗА_НЕТ, "У этого урока нет квиза")

	if not _вопросы_квиза(квиз):
		# Frappe Learning не даёт смешивать Open Ended с другими типами:
		# «make sure each question in the quiz is of open ended type». Значит
		# квиз либо весь открытый — и проверить его сервер не может, — либо
		# проверяемый целиком. Промежуточного случая не существует.
		raise Отказ(
			НЕЧЕГО_ПРОВЕРЯТЬ,
			"Квиз состоит из открытых вопросов — их разбирают на занятии, а не засчитывают",
		)

	политика = политика_квиза_для_курса(занятие.student, занятие.course)
	_проверить_право_на_попытку(занятие, квиз, политика)

	попытка = frappe.get_doc(
		{
			"doctype": "Agent Quiz Attempt",
			"session": занятие.name,
			"student": занятие.student,
			"quiz": квиз,
			"lesson": занятие.lesson,
			"course": занятие.course,
			"attempt_number": _прошлых_попыток(занятие.student, квиз) + 1,
			"status": "In Progress",
			"started_at": now_datetime(),
		}
	).insert(ignore_permissions=True)

	if занятие.status == "In Progress":
		занятие.status = "Awaiting Quiz"
		занятие.save(ignore_permissions=True)
	занятие.записать_событие("Quiz Started", f"попытка {попытка.attempt_number}")

	return {"attempt": попытка.name, "question": следующий_вопрос(попытка.name)}


def _проверить_право_на_попытку(занятие, квиз: str, политика: dict) -> None:
	"""Лимит попыток и пауза перед повтором — из политики организации."""
	прошлых = _прошлых_попыток(занятие.student, квиз)
	лимит = политика["max_attempts"]
	if лимит and прошлых >= лимит:
		raise Отказ(
			ПОПЫТКИ_ИСЧЕРПАНЫ, f"Использованы все попытки ({лимит})", attempts_used=прошлых
		)

	последняя = frappe.get_all(
		"Agent Quiz Attempt",
		filters={"student": занятие.student, "quiz": квиз, "status": ("!=", "In Progress")},
		fields=["finished_at"],
		order_by="finished_at desc",
		limit=1,
	)
	if not последняя or not последняя[0].finished_at:
		return

	можно_с = add_to_date(последняя[0].finished_at, hours=политика["retry_delay_hours"])
	if now_datetime() < можно_с:
		raise Отказ(
			СЛИШКОМ_РАНО,
			"Повторить попытку можно позже",
			retry_after=можно_с.isoformat(),
		)


def _прошлых_попыток(student: str, квиз: str) -> int:
	return frappe.db.count(
		"Agent Quiz Attempt", {"student": student, "quiz": квиз, "status": ("!=", "In Progress")}
	)


def _квиз_урока(lesson: str) -> str | None:
	"""Квиз, привязанный к уроку.

	Frappe Learning допускает две привязки: поле `quiz_id` у урока и поле
	`lesson` у квиза. Смотрим обе — иначе квиз, заведённый вторым способом,
	для нас не существует.
	"""
	квиз = frappe.db.get_value("Course Lesson", lesson, "quiz_id")
	if квиз and frappe.db.exists("LMS Quiz", квиз):
		return квиз
	return frappe.db.get_value("LMS Quiz", {"lesson": lesson}, "name")


# --- вопросы ---


def _вопросы_квиза(квиз: str) -> list[dict]:
	"""Вопросы квиза, которые сервер может проверить сам.

	Open Ended отсеиваются: их проверка требует человека, а зачёт, который
	ставит агент, не зачёт вовсе. Такие вопросы остаются материалом для
	устного разбора на занятии.
	"""
	строки = frappe.get_all(
		"LMS Quiz Question",
		filters={"parent": квиз},
		fields=["question", "marks"],
		order_by="idx asc",
	)
	вопросы = []
	for строка in строки:
		тип = frappe.db.get_value("LMS Question", строка.question, "type")
		if тип in ПРОВЕРЯЕМЫЕ_ТИПЫ:
			вопросы.append({"question": строка.question, "marks": строка.marks or 1, "type": тип})
	return вопросы


def следующий_вопрос(attempt: str) -> dict | None:
	"""Первый неотвеченный вопрос попытки — без единого поля эталона."""
	попытка = frappe.get_doc("Agent Quiz Attempt", attempt)
	вопросы = _вопросы_квиза(попытка.quiz)
	отвеченные = set(
		frappe.get_all("Agent Quiz Answer", filters={"attempt": attempt}, pluck="question")
	)
	for номер, вопрос in enumerate(вопросы, start=1):
		if вопрос["question"] not in отвеченные:
			return _вопрос_для_агента(вопрос, номер, len(вопросы))
	return None


def _вопрос_для_агента(вопрос: dict, номер: int, всего: int) -> dict:
	"""Вопрос в том виде, в каком его может увидеть агент.

	Здесь нет и не может быть `is_correct_*`, `explanation_*` и
	`possibility_*`: любой из них — готовый ответ.
	"""
	запись = frappe.get_doc("LMS Question", вопрос["question"])
	отдать = {
		"id": запись.name,
		"text": _очистить(запись.question),
		"kind": "choice" if запись.type == "Choices" else "input",
		"index": номер,
		"total": всего,
	}
	if запись.type == "Choices":
		отдать["multiple"] = bool(запись.multiple)
		отдать["options"] = [
			{"id": str(номер_варианта), "text": _очистить(текст)}
			for номер_варианта, текст in _варианты(запись)
		]
	return отдать


def _варианты(запись) -> list[tuple[int, str]]:
	варианты = []
	for номер in range(1, ВАРИАНТОВ_МАКСИМУМ + 1):
		текст = запись.get(f"option_{номер}")
		if текст and str(текст).strip():
			варианты.append((номер, текст))
	return варианты


# --- ответ и вердикт ---


def принять_ответ(attempt: str, question: str, answer: str) -> dict:
	"""Сверяет ответ, возвращает вердикт и следующий вопрос."""
	попытка = frappe.get_doc("Agent Quiz Attempt", attempt)
	if попытка.status != "In Progress":
		raise Отказ(ПОПЫТКА_ЗАВЕРШЕНА, "Эта попытка уже завершена")

	вопросы = {в["question"]: в for в in _вопросы_квиза(попытка.quiz)}
	if question not in вопросы:
		raise Отказ(ЧУЖОЙ_ВОПРОС, "Вопрос не из этой попытки")
	if frappe.db.exists("Agent Quiz Answer", {"attempt": attempt, "question": question}):
		raise Отказ(ЧУЖОЙ_ВОПРОС, "На этот вопрос уже отвечено")

	запись = frappe.get_doc("LMS Question", question)
	верно, пояснение = _сверить(запись, answer)
	баллы = вопросы[question]["marks"]

	frappe.get_doc(
		{
			"doctype": "Agent Quiz Answer",
			"attempt": attempt,
			"question": question,
			"answer": str(answer)[:500],
			"is_correct": int(верно),
			"marks": баллы if верно else 0,
			"marks_out_of": баллы,
			"answered_at": now_datetime(),
		}
	).insert(ignore_permissions=True)

	вердикт = {"correct": верно}
	if пояснение:
		# Пояснение отдаётся только вместе с вердиктом по уже отвеченному
		# вопросу — до ответа оно было бы подсказкой.
		вердикт["explanation"] = пояснение

	следующий = следующий_вопрос(attempt)
	ответ = {
		"verdict": вердикт,
		"next_question": следующий,
		"attempt_finished": следующий is None,
	}
	if следующий is None:
		ответ["result"] = _завершить(попытка)
	return ответ


def _сверить(запись, answer: str) -> tuple[bool, str | None]:
	"""Сверка с эталоном. Возвращает вердикт и пояснение.

	Тривиальна намеренно: ценность не в сверке, а в том, какие вопросы
	задаются и как они порождаются, — а это закрытая часть. Взамен получаем
	гарантию, что эталоны не утекают через агента.
	"""
	if запись.type == "Choices":
		выбранные = _разобрать_выбор(answer)
		верные = {
			str(номер)
			for номер in range(1, ВАРИАНТОВ_МАКСИМУМ + 1)
			if запись.get(f"is_correct_{номер}")
		}
		пояснение = " ".join(
			_очистить(запись.get(f"explanation_{номер}"))
			for номер in sorted(верные)
			if запись.get(f"explanation_{номер}")
		)
		return выбранные == верные, пояснение or None

	эталоны = {
		_привести(запись.get(f"possibility_{номер}"))
		for номер in range(1, ВАРИАНТОВ_МАКСИМУМ + 1)
		if запись.get(f"possibility_{номер}")
	}
	return _привести(answer) in эталоны, None


def _разобрать_выбор(answer: str) -> set[str]:
	"""Номера выбранных вариантов из ответа агента.

	Принимаем и «2», и «1,3», и список: агенты форматируют по-разному, а
	отказ из-за запятой выглядел бы как неверный ответ.
	"""
	if isinstance(answer, (list, tuple, set)):
		части = [str(часть) for часть in answer]
	else:
		части = str(answer or "").replace(";", ",").split(",")
	return {часть.strip() for часть in части if часть.strip()}


def _привести(значение) -> str:
	return " ".join(str(значение or "").lower().split())


# --- завершение ---


def _завершить(попытка) -> dict:
	"""Считает итог, пишет стандартные записи Frappe Learning, закрывает занятие."""
	ответы = frappe.get_all(
		"Agent Quiz Answer",
		filters={"attempt": попытка.name},
		fields=["question", "answer", "is_correct", "marks", "marks_out_of"],
	)
	всего = sum(о.marks_out_of or 0 for о in ответы)
	набрано = sum(о.marks or 0 for о in ответы)
	доля = (набрано / всего) if всего else 0.0

	политика = политика_квиза_для_курса(попытка.student, попытка.course)
	зачтено = доля >= политика["pass_threshold"]

	попытка.status = "Passed" if зачтено else "Failed"
	попытка.score = round(доля, 3)
	попытка.passed = int(зачтено)
	попытка.finished_at = now_datetime()
	попытка.submission = _записать_итог_frappe(попытка, ответы, набрано, всего, доля)
	попытка.save(ignore_permissions=True)

	занятие = frappe.get_doc("Agent Learning Session", попытка.session)
	if зачтено:
		_отметить_урок_пройденным(попытка)
		занятие.status = "Completed"
		занятие.save(ignore_permissions=True)
	занятие.записать_событие(
		"Verdict Returned", f"итог {попытка.score}, {'зачтено' if зачтено else 'не зачтено'}"
	)

	return {
		"score": попытка.score,
		"passed": зачтено,
		"pass_threshold": политика["pass_threshold"],
		"session_status": занятие.status,
	}


def _записать_итог_frappe(попытка, ответы, набрано: int, всего: int, доля: float) -> str:
	"""Стандартный `LMS Quiz Submission` — чтобы результат был виден в браузере.

	Оба канала обязаны сходиться в одной записи: ученик начинает урок с
	агентом и видит результат в браузере, потому что запись физически одна.
	"""
	порог = frappe.db.get_value("LMS Quiz", попытка.quiz, "passing_percentage") or 0
	итог = frappe.get_doc(
		{
			"doctype": "LMS Quiz Submission",
			"quiz": попытка.quiz,
			"course": попытка.course,
			"member": попытка.student,
			"score": набрано,
			"score_out_of": всего,
			"percentage": round(доля * 100),
			"passing_percentage": порог,
			"result": [
				{
					"question_name": о.question,
					"question": frappe.db.get_value("LMS Question", о.question, "question"),
					"answer": о.answer,
					"marks": о.marks,
					"marks_out_of": о.marks_out_of,
					"is_correct": о.is_correct,
				}
				for о in ответы
			],
		}
	).insert(ignore_permissions=True)
	return итог.name


def _отметить_урок_пройденным(попытка) -> None:
	"""Пишет `LMS Course Progress` — тот же прогресс, что видит браузер."""
	уже = frappe.db.exists(
		"LMS Course Progress", {"member": попытка.student, "lesson": попытка.lesson}
	)
	if уже:
		frappe.db.set_value("LMS Course Progress", уже, "status", "Complete")
		return
	frappe.get_doc(
		{
			"doctype": "LMS Course Progress",
			"member": попытка.student,
			"lesson": попытка.lesson,
			"chapter": frappe.db.get_value("Course Lesson", попытка.lesson, "chapter"),
			"course": попытка.course,
			"status": "Complete",
		}
	).insert(ignore_permissions=True)
