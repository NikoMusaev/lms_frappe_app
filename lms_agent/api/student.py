# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Методы учебного потока.

Спроектированы вокруг занятия, а не вокруг таблиц: универсального доступа к
записям здесь нет и не будет — иначе агент начнёт изобретать собственные
сценарии в обход педагогики и прав.
"""

import frappe
from frappe.utils import now_datetime

from lms_agent.agent_learning import quiz
from lms_agent.agent_learning.access import (
	НЕ_ЗАЧИСЛЕН,
	доступен_курс,
	ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА,
	каталог_для,
	курсы_ученика,
	можно_записаться,
	политика_квиза_для_курса,
)
from lms_agent.agent_learning.errors import Отказ
from lms_agent.agent_learning.normalizer import нормализовать_урок
from lms_agent.api import контракт, текущий_пользователь

НЕЧЕГО_УЧИТЬ = "nothing_to_study"
НУЖЕН_КВИЗ = "quiz_required"
УРОК_НЕ_НАЙДЕН = "lesson_not_found"
ЧУЖОЕ_ЗАНЯТИЕ = "not_your_session"


@frappe.whitelist()
@контракт
def list_my_courses() -> dict:
	"""Назначенные курсы с прогрессом, дедлайнами и просрочками."""
	ученик = текущий_пользователь()
	курсы = []
	for запись in курсы_ученика(ученик):
		# Уроки и пройденное читаются один раз на курс: прежняя редакция
		# строила их заново для прогресса и для следующего урока.
		уроки = _уроки_курса(запись["course"])
		пройдены = _пройденные(ученик, запись["course"])
		пройдено = len([урок for урок in уроки if урок in пройдены])
		всего = len(уроки)
		следующий = _первый_непройденный(уроки, пройдены)
		курсы.append(
			{
				"id": запись["course"],
				"title": frappe.db.get_value("LMS Course", запись["course"], "title"),
				"organization": запись["organization"],
				"mandatory": запись["mandatory"],
				"deadline": запись["deadline"],
				"overdue": запись["overdue"],
				"progress": {"lessons_total": всего, "lessons_completed": пройдено},
				"next_lesson": следующий,
			}
		)
	return {"courses": курсы}


@frappe.whitelist()
@контракт
def list_catalog() -> dict:
	"""Курсы, на которые ученик может записаться сам."""
	return {"courses": каталог_для(текущий_пользователь())}


@frappe.whitelist(methods=["POST"])
@контракт
def enroll(course: str) -> dict:
	"""Записывает ученика на курс из каталога."""
	ученик = текущий_пользователь()
	можно, причина = можно_записаться(ученик, course)
	if not можно:
		raise Отказ(причина, "На этот курс записаться нельзя", course=course)

	frappe.get_doc(
		{
			"doctype": "LMS Enrollment",
			"member": ученик,
			"course": course,
			"member_type": "Student",
		}
	).insert(ignore_permissions=True)

	return {
		"course": course,
		"title": frappe.db.get_value("LMS Course", course, "title"),
		"first_lesson": _следующий_урок(ученик, course),
	}


@frappe.whitelist()
@контракт
def course_outline(course: str) -> dict:
	"""Структура курса: главы, уроки и что из них пройдено.

	`Why:` без этого агент видит только следующий незакрытый урок и не может
	вернуться к пройденному — идентификатор взять неоткуда. «Повторим
	прошлую тему перед экзаменом» было невыполнимо при живом доступе к
	материалу.
	"""
	ученик = текущий_пользователь()
	можно, причина = доступен_курс(ученик, course)
	if not можно:
		raise Отказ(причина, "Этот курс сейчас недоступен", course=course)

	пройдены = _пройденные(ученик, course)
	следующий = _следующий_урок(ученик, course)
	# Порядок берётся тот же, что у остального кода: через ссылки глав и
	# уроков, иначе структура разойдётся с тем, что считает «следующим уроком».
	порядок = _уроки_курса(course)
	названия = {
		урок.name: урок.title
		for урок in frappe.get_all(
			"Course Lesson", filters={"name": ("in", порядок)}, fields=["name", "title"]
		)
	} if порядок else {}

	главы = []
	for глава in _главы_курса(course):
		уроки_главы = [
			урок
			for урок in порядок
			if frappe.db.get_value("Course Lesson", урок, "chapter") == глава["name"]
		]
		главы.append(
			{
				"title": глава["title"],
				"lessons": [
					{
						"id": урок,
						"title": названия.get(урок),
						"completed": урок in пройдены,
						"current": bool(следующий and следующий["id"] == урок),
					}
					for урок in уроки_главы
				],
			}
		)
	return {"course": course, "chapters": главы}


def _главы_курса(курс: str) -> list[dict]:
	"""Главы курса по порядку — тем же правилом, что и уроки."""
	из_ссылок = frappe.get_all(
		"Chapter Reference", filters={"parent": курс}, pluck="chapter", order_by="idx asc"
	)
	имена = из_ссылок or frappe.get_all(
		"Course Chapter", filters={"course": курс}, pluck="name"
	)
	названия = {
		глава.name: глава.title
		for глава in frappe.get_all(
			"Course Chapter", filters={"name": ("in", имена)}, fields=["name", "title"]
		)
	} if имена else {}
	return [{"name": имя, "title": названия.get(имя)} for имя in имена]


@frappe.whitelist(methods=["POST"])
@контракт
def start_lesson(lesson: str | None = None, segment: int = 1) -> dict:
	"""Начинает занятие: создаёт сессию и отдаёт всё нужное для урока.

	`segment` — часть длинного урока, считая с единицы. Без него агент видел
	бы только начало: материал режется по заголовкам, а способа попросить
	продолжение не было вовсе.
	"""
	ученик = текущий_пользователь()
	lesson = lesson or _выбрать_урок(ученик)

	курс = _курс_урока(lesson)
	# Один обход вместо трёх: доступ, сведения о курсе и просрочка берутся
	# из одного и того же списка.
	доступные = {запись["course"]: запись for запись in курсы_ученика(ученик)}
	if курс not in доступные:
		причина = (
			ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА
			if frappe.db.exists("LMS Enrollment", {"member": ученик, "course": курс})
			else НЕ_ЗАЧИСЛЕН
		)
		raise Отказ(причина, "Этот курс сейчас недоступен", course=курс)

	# Продолжение урока не заводит второе занятие: иначе на один урок копились
	# бы незакрытые сессии, которые потом закрывает фоновая задача.
	занятие = _текущее_занятие(ученик, lesson) or frappe.get_doc(
		{
			"doctype": "Agent Learning Session",
			"student": ученик,
			"lesson": lesson,
			"course": курс,
			"via_trusted_service": 1,
		}
	).insert(ignore_permissions=True)

	материал = нормализовать_урок(lesson)
	segment = max(1, int(segment or 1))
	директива = _директива(lesson)
	занятие.записать_событие("Directive Issued", f"урок {lesson}")

	политика = политика_квиза_для_курса(ученик, курс)
	сведения = доступные[курс]

	return {
		"session": занятие.name,
		"lesson": {
			"id": lesson,
			"title": материал.title,
			"course": курс,
			"overdue": bool(сведения.get("overdue")),
		},
		"content": {
			"markdown": материал.сегмент(segment),
			"segment_index": min(segment, материал.total_segments or 1),
			"total_segments": материал.total_segments,
		},
		"media": [
			{"kind": м.kind, "title": м.title, "url": м.url} for м in материал.media
		],
		"objectives": директива.get("objectives", []),
		"directive": директива.get("directive"),
		"quiz": {
			"required": политика["quiz_required"],
			"pass_threshold": политика["pass_threshold"],
			"attempts_left": _осталось_попыток(ученик, lesson, политика),
		},
	}


@frappe.whitelist(methods=["POST"])
@контракт
def report_checkpoint(session: str, note: str) -> dict:
	"""Отметка о пройденном по ходу занятия. Телеметрия, не зачёт."""
	занятие = _своё_занятие(session)
	занятие.записать_событие("Checkpoint Reported", note)
	return {"recorded_at": now_datetime().isoformat()}


@frappe.whitelist(methods=["POST"])
@контракт
def complete_lesson(session: str) -> dict:
	"""Отмечает урок пройденным, когда проверять нечего.

	Для урока с обязательным квизом отказывает: иначе этот метод стал бы
	обходом проверки. Зачёт по квизу ставит только сервер, и обойти его
	вызовом нельзя.
	"""
	занятие = _своё_занятие(session)
	if quiz.требуется_квиз(занятие.lesson, занятие.student, занятие.course):
		raise Отказ(
			НУЖЕН_КВИЗ,
			"Этот урок закрывается только сдачей квиза",
			session=session,
		)

	quiz.отметить_урок_пройденным(занятие)
	if занятие.status in ("In Progress", "Awaiting Quiz"):
		занятие.status = "Completed"
		занятие.save(ignore_permissions=True)
	занятие.записать_событие("Verdict Returned", "урок закрыт без квиза")

	return {
		"lesson": занятие.lesson,
		"session_status": занятие.status,
		"next_lesson": _следующий_урок(занятие.student, занятие.course),
	}


@frappe.whitelist(methods=["POST"])
@контракт
def request_quiz(session: str) -> dict:
	"""Создаёт попытку и отдаёт первый вопрос."""
	_своё_занятие(session)
	return quiz.начать_попытку(session)


@frappe.whitelist(methods=["POST"])
@контракт
def submit_answer(attempt: str, question: str, answer: str) -> dict:
	"""Принимает ответ, возвращает вердикт и следующий вопрос."""
	попытка = frappe.get_doc("Agent Quiz Attempt", attempt)
	if попытка.student != текущий_пользователь():
		# Права на чтение мало: занятия и попытки своих людей читает ещё и
		# руководитель, а отвечать за ученика он не должен — иначе сожжёт
		# ему попытку или провалит квиз за него.
		raise Отказ(ЧУЖОЕ_ЗАНЯТИЕ, "Это чужая попытка", attempt=attempt)
	return quiz.принять_ответ(attempt, question, answer)


@frappe.whitelist()
@контракт
def get_my_progress() -> dict:
	"""Сводка по себе."""
	ученик = текущий_пользователь()
	курсы = курсы_ученика(ученик)
	занятия = frappe.get_all(
		"Agent Learning Session",
		filters={"student": ученик},
		fields=["lesson", "status", "started_at"],
		order_by="started_at desc",
		limit=10,
	)
	return {
		"courses_total": len(курсы),
		"courses_overdue": sum(1 for к in курсы if к["overdue"]),
		"courses": [
			{
				"id": курс["course"],
				"title": frappe.db.get_value("LMS Course", курс["course"], "title"),
				"deadline": курс["deadline"],
				"overdue": курс["overdue"],
				"completion": _доля_пройденного(ученик, курс["course"]),
			}
			for курс in курсы
		],
		"recent_sessions": [
			{
				"lesson": з.lesson,
				"status": з.status,
				"started_at": з.started_at.isoformat() if з.started_at else None,
			}
			for з in занятия
		],
	}


# --- вспомогательное ---


def _текущее_занятие(ученик: str, lesson: str):
	"""Незакрытое занятие ученика по этому уроку, если оно есть."""
	открытые = frappe.get_all(
		"Agent Learning Session",
		filters={
			"student": ученик,
			"lesson": lesson,
			"status": ("in", ("In Progress", "Awaiting Quiz")),
		},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return frappe.get_doc("Agent Learning Session", открытые[0]) if открытые else None


def _своё_занятие(session: str):
	"""Занятие текущего ученика. Чужое отклоняется до всякого действия."""
	занятие = frappe.get_doc("Agent Learning Session", session)
	if занятие.student != текущий_пользователь():
		raise Отказ(ЧУЖОЕ_ЗАНЯТИЕ, "Это чужое занятие", session=session)
	return занятие


def _курс_урока(lesson: str) -> str:
	глава = frappe.db.get_value("Course Lesson", lesson, "chapter")
	курс = frappe.db.get_value("Course Chapter", глава, "course") if глава else None
	if not курс:
		raise Отказ(УРОК_НЕ_НАЙДЕН, "Такого урока нет", lesson=lesson)
	return курс


def _выбрать_урок(ученик: str) -> str:
	"""Следующий незакрытый урок с ближайшим дедлайном.

	Порядок важен: сначала просроченные и срочные курсы, потом остальные —
	ученик, попросивший «давай заниматься», должен получить то, что горит.
	"""
	курсы = sorted(
		курсы_ученика(ученик),
		key=lambda к: (к["deadline"] is None, к["deadline"] or "", not к["mandatory"]),
	)
	for курс in курсы:
		следующий = _следующий_урок(ученик, курс["course"])
		if следующий:
			return следующий["id"]
	raise Отказ(НЕЧЕГО_УЧИТЬ, "Незакрытых уроков не осталось")


def _уроки_курса(курс: str) -> list[str]:
	"""Уроки курса в том порядке, в каком их показывает браузер.

	`Why:` порядок глав и уроков Frappe Learning хранит в дочерних таблицах
	`Chapter Reference` и `Lesson Reference`, а не в полях `course`/`chapter`:
	у самих записей `idx` всегда ноль. Сортировка по нему давала случайный
	порядок — а от него зависит, какой урок ученик получит следующим.

	Прямые ссылки остаются запасным путём: курс, собранный импортом или
	миграцией, может не иметь строк-ссылок, и терять его уроки нельзя.
	"""
	главы = frappe.get_all(
		"Chapter Reference", filters={"parent": курс}, pluck="chapter", order_by="idx asc"
	) or frappe.get_all("Course Chapter", filters={"course": курс}, pluck="name")

	уроки = []
	for глава in главы:
		из_ссылок = frappe.get_all(
			"Lesson Reference", filters={"parent": глава}, pluck="lesson", order_by="idx asc"
		)
		уроки += из_ссылок or frappe.get_all(
			"Course Lesson", filters={"chapter": глава}, pluck="name"
		)
	return уроки


def _пройденные(ученик: str, курс: str) -> set[str]:
	return set(
		frappe.get_all(
			"LMS Course Progress",
			filters={"member": ученик, "course": курс, "status": "Complete"},
			pluck="lesson",
		)
	)


def _доля_пройденного(ученик: str, курс: str) -> float:
	"""Доля пройденных уроков курса — её обещает контракт в сводке."""
	уроки = _уроки_курса(курс)
	if not уроки:
		return 0.0
	пройдены = _пройденные(ученик, курс)
	return round(len([урок for урок in уроки if урок in пройдены]) / len(уроки), 2)


def _первый_непройденный(уроки: list[str], пройдены: set[str]) -> dict | None:
	for урок in уроки:
		if урок not in пройдены:
			return {"id": урок, "title": frappe.db.get_value("Course Lesson", урок, "title")}
	return None


def _следующий_урок(ученик: str, курс: str) -> dict | None:
	return _первый_непройденный(_уроки_курса(курс), _пройденные(ученик, курс))


def _директива(lesson: str) -> dict:
	"""Действующая директива урока — отдельным полем и с пометкой адресата.

	Материал и директива приходят разными полями, а сама директива помечена
	`audience: teacher_only`. Это одна из трёх митигаций против пересказа
	директивы ученику; гарантий она не даёт — гарантию даёт серверный квиз.
	"""
	запись = frappe.get_all(
		"Agent Lesson Directive",
		filters={"lesson": lesson, "is_active": 1},
		fields=[
			"objectives",
			"teaching_directive",
			"probing_questions",
			"common_misconceptions",
			"success_criteria",
		],
		limit=1,
		ignore_permissions=True,
	)
	if not запись:
		return {}
	д = запись[0]
	return {
		"objectives": _строки(д.objectives),
		"directive": {
			"audience": "teacher_only",
			"teaching_directive": д.teaching_directive,
			"probing_questions": _строки(д.probing_questions),
			"common_misconceptions": _строки(д.common_misconceptions),
			"success_criteria": _строки(д.success_criteria),
		},
	}


def _строки(значение: str | None) -> list[str]:
	return [строка.strip() for строка in (значение or "").splitlines() if строка.strip()]


def _осталось_попыток(ученик: str, lesson: str, политика: dict) -> int | None:
	квиз = quiz._квиз_урока(lesson)
	if not квиз:
		return None
	лимит = политика["max_attempts"]
	if not лимит:
		return None
	return max(0, лимит - quiz._прошлых_попыток(ученик, квиз))
