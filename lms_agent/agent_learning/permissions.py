# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Изоляция организаций.

Менеджер видит обучение своей компании и не видит чужого. Ограничение стоит
на правах Frappe — `permission_query_conditions` для списков и `has_permission`
для прямого обращения по имени записи, — поэтому работает одинаково в браузере
и в MCP: оба канала ходят от имени пользователя.

**Источник правды о принадлежности — `Organization Membership`**, а не
`User Permission`. Спека предлагала второе, но членство у нас уже есть, и
`User Permission` стал бы второй копией того же факта: две записи, которые
рано или поздно разъедутся, и тогда непонятно, какая правдива.
"""

from __future__ import annotations

import frappe

ВСЕВИДЯЩИЕ_РОЛИ = frozenset({"System Manager", "Administrator", "Agent Service"})
РОЛИ_МЕНЕДЖЕРА = ("Manager", "Org Admin")


def видит_всё(user: str) -> bool:
	"""Роли, для которых изоляция не применяется."""
	return bool(set(frappe.get_roles(user)) & ВСЕВИДЯЩИЕ_РОЛИ)


def организации_менеджера(user: str) -> list[str]:
	"""Организации, обучение которых пользователь вправе видеть целиком.

	Роль Frappe `Organization Manager` даёт саму возможность смотреть отчёты,
	а вот **какие именно** организации — определяет членство. Без членства
	роль не открывает ничего: иначе первый же менеджер увидел бы всех.
	"""
	if "Organization Manager" not in frappe.get_roles(user):
		return []
	return frappe.get_all(
		"Organization Membership",
		filters={"user": user, "role": ("in", РОЛИ_МЕНЕДЖЕРА)},
		pluck="organization",
	)


def _список(значения: list[str]) -> str:
	return ", ".join(frappe.db.escape(значение) for значение in значения)


def условие_членства(user: str | None = None) -> str:
	"""`Organization Membership`: своё членство плюс состав своей организации."""
	user = user or frappe.session.user
	if видит_всё(user):
		return ""
	свои = f"`tabOrganization Membership`.`user` = {frappe.db.escape(user)}"
	организации = организации_менеджера(user)
	if not организации:
		return свои
	return f"({свои} or `tabOrganization Membership`.`organization` in ({_список(организации)}))"


def условие_назначения(user: str | None = None) -> str:
	"""`Course Allocation`: назначения своих организаций.

	Ученик видит назначения компаний, в которых состоит: по ним он получает
	дедлайны и понимает, что курс обязателен. Чужие — не видит вовсе.
	"""
	from lms_agent.agent_learning.doctype.learning_organization.learning_organization import (
		организации_пользователя,
	)

	user = user or frappe.session.user
	if видит_всё(user):
		return ""
	организации = организации_пользователя(user)
	if not организации:
		# Не «покажем всё», а «не покажем ничего»: пустое условие в Frappe
		# означает отсутствие ограничений, и ошибка здесь открыла бы чужие
		# назначения целиком.
		return "1 = 0"
	return f"`tabCourse Allocation`.`organization` in ({_список(организации)})"


def условие_занятия(user: str | None = None) -> str:
	"""`Agent Learning Session`: свои занятия, менеджеру — занятия его людей."""
	user = user or frappe.session.user
	if видит_всё(user):
		return ""
	свои = f"`tabAgent Learning Session`.`student` = {frappe.db.escape(user)}"
	организации = организации_менеджера(user)
	if not организации:
		return свои
	подзапрос = (
		"select user from `tabOrganization Membership` "
		f"where organization in ({_список(организации)})"
	)
	return f"({свои} or `tabAgent Learning Session`.`student` in ({подзапрос}))"


def доступно_занятие(doc, ptype: str = "read", user: str | None = None) -> bool:
	"""Права на конкретное занятие.

	Нужен рядом с фильтром списка: без него чужое занятие остаётся доступным
	по прямому обращению по имени записи — а именно так его и попробуют взять.
	"""
	user = user or frappe.session.user
	if видит_всё(user) or doc.student == user:
		return True
	организации = организации_менеджера(user)
	if not организации:
		return False
	return bool(
		frappe.db.exists(
			"Organization Membership",
			{"user": doc.student, "organization": ("in", организации)},
		)
	)


def доступно_членство(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if видит_всё(user) or doc.user == user:
		return True
	return doc.organization in организации_менеджера(user)


def доступно_назначение(doc, ptype: str = "read", user: str | None = None) -> bool:
	from lms_agent.agent_learning.doctype.learning_organization.learning_organization import (
		организации_пользователя,
	)

	user = user or frappe.session.user
	return видит_всё(user) or doc.organization in организации_пользователя(user)


def условие_события(user: str | None = None) -> str:
	"""`Agent Session Event`: журнал тех занятий, которые пользователю видны."""
	user = user or frappe.session.user
	if видит_всё(user):
		return ""
	видимые_занятия = (
		f"select name from `tabAgent Learning Session` where {условие_занятия(user)}"
	)
	return f"`tabAgent Session Event`.`session` in ({видимые_занятия})"


def доступно_событие(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if видит_всё(user):
		return True
	занятие = frappe.db.get_value(
		"Agent Learning Session", doc.session, ["name", "student"], as_dict=True
	)
	return bool(занятие) and доступно_занятие(занятие, ptype, user)
