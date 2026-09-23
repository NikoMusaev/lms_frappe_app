# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentAuthorNote(Document):
	"""Замечание автора на месте курса и нить ответов к нему.

	Не содержание курса: его пишут человек в кабинете и агент куратора, чтобы
	петля «увидел → агент поправил → принял» не шла через пересказ в чате.
	Правила адреса и переходов — в `agent_learning/notes.py`; статус меняют
	только авторские методы. Ученику недоступно: роль `LMS Student` прав на
	этот DocType не имеет.
	"""
