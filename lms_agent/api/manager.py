# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Методы руководителя организации.

Изоляция проверяется **явно**, и это не дублирование хуков: `frappe.get_all`
— это `get_list(ignore_permissions=True)`, и `permission_query_conditions` к
нему не применяются никогда. Отчёт, положившийся на хуки, отдавал занятия
любого человека на платформе кому угодно — проверено эксплуатацией.
"""

import frappe

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
	for назначение in назначения:
		for участник in _адресаты(назначение):
			строка = _строка_отчёта(участник, назначение)
			if status and строка["status"] != status:
				continue
			строки.append(строка)
	return {"rows": строки}


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
	if назначение.audience == "Selected Members":
		return frappe.get_all(
			"Course Allocation Member", filters={"parent": назначение.name}, pluck="user"
		)
	return frappe.get_all(
		"Organization Membership",
		filters={"organization": назначение.organization},
		pluck="user",
	)


def _строка_отчёта(участник: str, назначение) -> dict:
	from frappe.utils import getdate, nowdate

	уроки = _уроки_курса(назначение.course)
	пройдены = frappe.get_all(
		"LMS Course Progress",
		filters={"member": участник, "course": назначение.course, "status": "Complete"},
		pluck="lesson",
	)
	пройдено = len([у for у in уроки if у in set(пройдены)])
	доля = (пройдено / len(уроки)) if уроки else 0.0

	if пройдено == 0:
		статус = "not_started"
	elif уроки and пройдено == len(уроки):
		статус = "completed"
	else:
		статус = "in_progress"

	последняя = frappe.get_all(
		"Agent Learning Session",
		filters={"student": участник, "course": назначение.course},
		fields=["started_at"],
		order_by="started_at desc",
		limit=1,
	)
	return {
		"user": участник,
		"full_name": frappe.db.get_value("User", участник, "full_name"),
		"course": назначение.course,
		"organization": назначение.organization,
		"status": статус,
		"progress": round(доля, 2),
		"deadline": назначение.deadline,
		"mandatory": bool(назначение.mandatory),
		"overdue": bool(
			назначение.deadline
			and статус != "completed"
			and getdate(назначение.deadline) < getdate(nowdate())
		),
		"last_activity": последняя[0].started_at.isoformat()
		if последняя and последняя[0].started_at
		else None,
	}


def _уроки_курса(курс: str) -> list[str]:
	from lms_agent.api.student import _уроки_курса as уроки

	return уроки(курс)
