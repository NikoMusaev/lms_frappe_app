# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentNoteReply(Document):
	"""Ответ в нити замечания: кто — автор или агент — и что сказал."""
