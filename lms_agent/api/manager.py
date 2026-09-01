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
from lms_agent.agent_learning.errors import Отказ
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
		уроки = _уроки_курса(назначение.course)
		пройдено = _пройдено_по_участникам(назначение.course, участники)
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


def _пройдено_по_участникам(курс: str, участники: list[str]) -> dict[str, int]:
	"""Сколько уроков курса пройдено каждым — одним запросом на курс."""
	записи = frappe.get_all(
		"LMS Course Progress",
		filters={"course": курс, "member": ("in", участники), "status": "Complete"},
		fields=["member"],
	)
	пройдено: dict[str, int] = {}
	for запись in записи:
		пройдено[запись.member] = пройдено.get(запись.member, 0) + 1
	return пройдено


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
			for запись in курсы_ученика(user)
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
	"""Кому предназначено назначение — по правилу самого назначения.

	Копия этого правила здесь уже разъехалась с оригиналом: доктайп фильтрует
	участников по ролям членства, отчёт — нет. Сегодня это ничего не меняет,
	но при четвёртой роли отчёт и выданные зачисления разошлись бы.
	"""
	return frappe.get_doc("Course Allocation", назначение.name).адресаты()


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
		# Просрочка считается тем же правилом, что и для ученика: раньше
		# менеджер и ученик видели разное про один и тот же курс.
		"overdue": bool(
			назначение.deadline and getdate(назначение.deadline) < getdate(nowdate())
		),
		"last_activity": активность.isoformat() if активность else None,
	}


def _уроки_курса(курс: str) -> list[str]:
	from lms_agent.api.student import _уроки_курса as уроки

	return уроки(курс)
