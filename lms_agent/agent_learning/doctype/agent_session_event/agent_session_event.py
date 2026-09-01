# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AgentSessionEvent(Document):
	"""Запись в журнале занятия.

	Журнал — это аудит и антифрод-сигнал одновременно: урок, «пройденный» за
	сорок секунд, виден по отметкам времени сразу, без разбирательств.

	События не редактируются и не удаляются: журнал, который можно поправить,
	перестаёт быть журналом.
	"""

	def before_insert(self):
		self.occurred_at = self.occurred_at or now_datetime()

	def before_save(self):
		# get_doc_before_save, а не is_new(): к моменту post-save хуков вставка
		# уже перестаёт считаться новой, и запрет срабатывал бы на собственное
		# создание записи. Прежняя редакция существует только у правки.
		if self.get_doc_before_save():
			frappe.throw(
				frappe._("Записи журнала занятия не изменяются"), frappe.ValidationError
			)

	def on_trash(self):
		frappe.throw(frappe._("Записи журнала занятия не удаляются"), frappe.ValidationError)


def get_permission_query_conditions(user: str | None = None) -> str:
	"""Ученик видит журнал только своих занятий."""
	from lms_agent.agent_learning.doctype.agent_learning_session.agent_learning_session import (
		_видит_все_занятия,
	)

	user = user or frappe.session.user
	if _видит_все_занятия(user):
		return ""
	return (
		"`tabAgent Session Event`.`session` in "
		"(select name from `tabAgent Learning Session` "
		f"where student = {frappe.db.escape(user)})"
	)


def has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	from lms_agent.agent_learning.doctype.agent_learning_session.agent_learning_session import (
		_видит_все_занятия,
	)

	user = user or frappe.session.user
	if _видит_все_занятия(user):
		return True
	return frappe.db.get_value("Agent Learning Session", doc.session, "student") == user
