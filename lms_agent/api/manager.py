# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Методы руководителя организации.

Изоляция проверяется **явно**, и это не дублирование хуков: `frappe.get_all`
— это `get_list(ignore_permissions=True)`, и `permission_query_conditions` к
нему не применяются никогда. Отчёт, положившийся на хуки, отдавал занятия
любого человека на платформе кому угодно — проверено эксплуатацией.
"""

import frappe

from lms_agent.agent_learning.access import курсы_ученика
from lms_agent.agent_learning.doctype.course_allocation.course_allocation import (
	адресаты_назначения,
)
from lms_agent.agent_learning.errors import Отказ
from lms_agent.agent_learning.structure import уроки_курса
from lms_agent.agent_learning.permissions import (
	организации_менеджера,
	свои_организации_пересекаются,
)
from lms_agent.api import контракт, текущий_пользователь

ЧУЖОЙ_УЧЕНИК = "not_your_student"

СТАТУСЫ = {
	"not_started": "не начат",
	"in_progress": "в процессе",
	"completed": "пройден",
}


@frappe.whitelist()
@контракт
def org_report(course: str | None = None, status: str | None = None) -> dict:
	"""Обучение своей организации: кто на чём и что просрочено."""
	менеджер = текущий_пользователь()
	организации = организации_менеджера(менеджер)
	if not организации:
		return {"rows": []}

	назначения = frappe.get_all(
		"Course Allocation",
		filters={"organization": ("in", организации), **({"course": course} if course else {})},
		fields=["name", "organization", "course", "audience", "deadline", "mandatory"],
	)

	строки = []
	# Данные, общие для всех участников курса, читаются один раз: прежняя
	# редакция строила список уроков и запрашивала прогресс на каждую пару
	# «назначение × участник», и организация на пятьсот человек с десятью
	# курсами давала десятки тысяч запросов в одном вызове.
	for назначение in назначения:
		участники = _адресаты(назначение)
		if not участники:
			continue
		уроки = уроки_курса(назначение.course)
		пройдено = _пройдено_по_участникам(назначение.course, участники, уроки)
		имена = _имена(участники)
		последняя_активность = _последняя_активность(назначение.course, участники)

		for участник in участники:
			строка = _строка_отчёта(
				участник,
				назначение,
				уроки=уроки,
				пройдено=пройдено.get(участник, 0),
				имя=имена.get(участник),
				активность=последняя_активность.get(участник),
			)
			if status and строка["status"] != status:
				continue
			строки.append(строка)
	return {"rows": строки}


def _пройдено_по_участникам(
	курс: str, участники: list[str], уроки: list[str]
) -> dict[str, int]:
	"""Сколько уроков курса пройдено каждым — одним запросом на курс.

	Считаются только уроки, которые сейчас в курсе. `Why:` записи прогресса
	переживают перенос урока в другую главу, и подсчёт «по строкам» давал
	долю больше единицы, а статус «пройден» не наступал никогда.
	"""
	в_курсе = set(уроки)
	записи = frappe.get_all(
		"LMS Course Progress",
		filters={"course": курс, "member": ("in", участники), "status": "Complete"},
		fields=["member", "lesson"],
	)
	пройдено: dict[str, set[str]] = {}
	for запись in записи:
		if запись.lesson in в_курсе:
			пройдено.setdefault(запись.member, set()).add(запись.lesson)
	return {участник: len(уроки) for участник, уроки in пройдено.items()}


def _имена(участники: list[str]) -> dict[str, str]:
	return {
		запись.name: запись.full_name
		for запись in frappe.get_all(
			"User", filters={"name": ("in", участники)}, fields=["name", "full_name"]
		)
	}


def _последняя_активность(курс: str, участники: list[str]) -> dict[str, object]:
	"""Последнее занятие каждого участника по курсу — одним запросом."""
	последние: dict[str, object] = {}
	for занятие in frappe.get_all(
		"Agent Learning Session",
		filters={"course": курс, "student": ("in", участники)},
		fields=["student", "started_at"],
		order_by="started_at asc",
	):
		последние[занятие.student] = занятие.started_at
	return последние


@frappe.whitelist()
@контракт
def student_detail(user: str) -> dict:
	"""Подробности по одному ученику своей организации.

	Тексты ответов на вопросы не отдаются: отчёт про результат, а не про
	содержание диалога с агентом.
	"""
	if not свои_организации_пересекаются(текущий_пользователь(), user):
		raise Отказ(ЧУЖОЙ_УЧЕНИК, "Этот ученик не из вашей организации", user=user)

	занятия = frappe.get_all(
		"Agent Learning Session",
		filters={"student": user},
		fields=["name", "lesson", "course", "status", "started_at", "finished_at"],
		order_by="started_at desc",
		limit=50,
	)
	попытки = frappe.get_all(
		"Agent Quiz Attempt",
		filters={"student": user},
		fields=["quiz", "lesson", "attempt_number", "status", "score", "passed", "finished_at"],
		order_by="finished_at desc",
		limit=50,
	)
	return {
		"user": user,
		"full_name": frappe.db.get_value("User", user, "full_name"),
		"courses": [
			{
				"id": запись["course"],
				"title": frappe.db.get_value("LMS Course", запись["course"], "title"),
				"deadline": запись["deadline"],
				"overdue": запись["overdue"],
				"mandatory": запись["mandatory"],
			}
			# Только курсы, пришедшие от организаций вызывающего: человек
			# может состоять в нескольких компаниях, и назначения чужой
			# руководителя не касаются, как и его самозаписи.
			for запись in курсы_ученика(user)
			if запись["organization"] in организации_менеджера(текущий_пользователь())
		],
		"sessions": [
			{
				"lesson": з.lesson,
				"course": з.course,
				"status": з.status,
				"started_at": з.started_at.isoformat() if з.started_at else None,
				"finished_at": з.finished_at.isoformat() if з.finished_at else None,
			}
			for з in занятия
		],
		"quiz_attempts": [
			{
				"lesson": п.lesson,
				"attempt": п.attempt_number,
				"status": п.status,
				"score": п.score,
				"passed": bool(п.passed),
				"finished_at": п.finished_at.isoformat() if п.finished_at else None,
			}
			for п in попытки
		],
	}


def _адресаты(назначение) -> list[str]:
	"""Кому предназначено назначение — общим правилом, без загрузки документа.

	Копия этого правила здесь уже разъезжалась с оригиналом. Правило одно, но
	поднимать документ с дочерними таблицами на каждое назначение отчёту
	незачем — ради этого и вынесена функция.
	"""
	return адресаты_назначения(
		назначение.name, назначение.organization, назначение.audience
	)


def _строка_отчёта(
	участник: str,
	назначение,
	*,
	уроки: list[str],
	пройдено: int,
	имя: str | None,
	активность,
) -> dict:
	from frappe.utils import getdate, nowdate

	доля = (пройдено / len(уроки)) if уроки else 0.0

	if пройдено == 0:
		статус = "not_started"
	elif уроки and пройдено == len(уроки):
		статус = "completed"
	else:
		статус = "in_progress"

	return {
		"user": участник,
		"full_name": имя,
		"course": назначение.course,
		"organization": назначение.organization,
		"status": статус,
		"progress": round(доля, 2),
		"deadline": назначение.deadline,
		"mandatory": bool(назначение.mandatory),
		# Пройденный курс не просрочен: иначе отчёт «кто не успел» после
		# дедлайна показывает всех подряд, включая закрывших курс заранее.
		# У ученика overdue — свойство курса, здесь — свойство человека.
		"overdue": bool(
			назначение.deadline
			and статус != "completed"
			and getdate(назначение.deadline) < getdate(nowdate())
		),
		"last_activity": активность.isoformat() if активность else None,
	}


