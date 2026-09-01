# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OrganizationMembership(Document):
	"""Участие пользователя в организации.

	Отдельный DocType, а не строка в таблице организации: пользователь может
	состоять в нескольких организациях, и запросы по членству должны
	оставаться индексируемыми.
	"""

	def validate(self):
		self._проверить_повтор()

	def _проверить_повтор(self) -> None:
		уже_есть = frappe.db.exists(
			self.doctype,
			{"user": self.user, "organization": self.organization, "name": ("!=", self.name)},
		)
		if уже_есть:
			frappe.throw(
				frappe._("{0} уже состоит в организации {1}").format(self.user, self.organization),
				frappe.DuplicateEntryError,
			)
