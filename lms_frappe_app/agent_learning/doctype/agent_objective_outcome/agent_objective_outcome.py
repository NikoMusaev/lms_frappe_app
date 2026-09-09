# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentObjectiveOutcome(Document):
	"""Как прошла одна цель урока на конкретном занятии.

	Цель хранится строкой, а не ссылкой на директиву: директива
	версионируется, и переформулированная автором цель не должна задним
	числом переписывать то, о чём уже отчитались.
	"""
