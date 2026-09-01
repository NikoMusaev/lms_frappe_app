# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Доступ ученика к курсам.

Одно место, где сходятся три источника: зачисление, назначение организации и
статус самой организации. `Why:` правила пересечения этих трёх не очевидны, и
разложенные по вызывающим местам они разъедутся — каждый метод начнёт решать
по-своему, кто что видит.

Основание доступа — **зачисление** (`LMS Enrollment`). Назначение добавляет
поверх дедлайн и обязательность, но само по себе доступа не даёт и не отнимает.
Так частный ученик и сотрудник компании живут на одной схеме.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate, nowdate

from lms_agent.agent_learning.doctype.course_allocation.course_allocation import (
	назначения_пользователя,
)
from lms_agent.agent_learning.doctype.learning_organization.learning_organization import (
	политика_квиза,
)

#: Коды отказов контракта — их видит агент, по ним он объясняет ученику,
#: что происходит. Тексты меняются, коды нет.
НЕ_ЗАЧИСЛЕН = "not_enrolled"
ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА = "organization_suspended"


def курсы_ученика(user: str) -> list[dict]:
	"""Курсы, доступные ученику, с условиями поверх.

	Список строится по зачислениям, а не по назначениям: иначе ученик, который
	записался сам, не увидел бы ничего — у него назначений нет вовсе.
	"""
	зачисления = frappe.get_all(
		"LMS Enrollment", filters={"member": user}, fields=["name", "course"]
	)
	if not зачисления:
		return []

	условия = _условия_по_курсам(user)
	курсы = []
	for зачисление in зачисления:
		условие = условия.get(зачисление.course)
		if условие and условие["suspended"]:
			# Курс пришёл от приостановленной организации: доступ закрыт, но
			# зачисление цело — при возобновлении прогресс не потеряется.
			continue
		дедлайн = условие["deadline"] if условие else None
		курсы.append(
			{
				"course": зачисление.course,
				"enrollment": зачисление.name,
				"organization": условие["organization"] if условие else None,
				"deadline": дедлайн,
				"mandatory": bool(условие["mandatory"]) if условие else False,
				"overdue": bool(дедлайн and getdate(дедлайн) < getdate(nowdate())),
			}
		)
	return курсы


def доступен_курс(user: str, course: str) -> tuple[bool, str | None]:
	"""Может ли ученик заниматься курсом; при отказе — код причины."""
	доступные = {к["course"] for к in курсы_ученика(user)}
	if course in доступные:
		return True, None
	if frappe.db.exists("LMS Enrollment", {"member": user, "course": course}):
		# Зачисление есть, но курс не в списке — значит его перекрыла
		# приостановка организации.
		return False, ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА
	return False, НЕ_ЗАЧИСЛЕН


def политика_квиза_для_курса(user: str, course: str) -> dict:
	"""Политика квиза, действующая для ученика на этом курсе.

	Курс может быть назначен несколькими организациями сразу — человек вправе
	состоять в нескольких. Тогда берётся **строжайшая** из политик: занижать
	требования клиента из-за того, что ученик числится ещё где-то, нельзя, а
	завысить безопаснее, чем занизить.
	"""
	организации = [
		назначение.organization
		for назначение in назначения_пользователя(user, course=course)
		if not _приостановлена(назначение.organization)
	]
	if not организации:
		return политика_квиза(None)

	политики = [политика_квиза(организация) for организация in организации]
	лимиты = [п["max_attempts"] for п in политики if п["max_attempts"]]
	return {
		"quiz_required": any(п["quiz_required"] for п in политики),
		"pass_threshold": max(п["pass_threshold"] for п in политики),
		# Ноль означает «без лимита» и потому не участвует в выборе
		# строжайшего: min по нулю выбрал бы самое мягкое правило.
		"max_attempts": min(лимиты) if лимиты else 0,
		"retry_delay_hours": max(п["retry_delay_hours"] for п in политики),
	}


def _условия_по_курсам(user: str) -> dict[str, dict]:
	"""Условия назначений по курсам: ближайший дедлайн и статус организации.

	Если курс назначен несколькими организациями, побеждает действующее
	назначение с ближайшим дедлайном — оно и есть самое строгое требование.
	Курс считается перекрытым приостановкой, только когда **все** его
	назначения от приостановленных организаций.
	"""
	условия: dict[str, dict] = {}
	for назначение in назначения_пользователя(user):
		приостановлена = _приостановлена(назначение.organization)
		текущее = условия.get(назначение.course)

		if текущее and not текущее["suspended"] and приостановлена:
			continue  # действующее назначение важнее приостановленного

		лучше_дедлайн = (
			текущее is None
			or текущее["suspended"] and not приостановлена
			or _раньше(назначение.deadline, текущее["deadline"])
		)
		if лучше_дедлайн:
			условия[назначение.course] = {
				"organization": назначение.organization,
				"deadline": назначение.deadline,
				"mandatory": назначение.mandatory,
				"suspended": приостановлена,
			}
	return условия


def _раньше(дедлайн, текущий) -> bool:
	if дедлайн is None:
		return False
	if текущий is None:
		return True
	return getdate(дедлайн) < getdate(текущий)


def _приостановлена(organization: str) -> bool:
	return frappe.db.get_value("Learning Organization", organization, "status") != "Active"
