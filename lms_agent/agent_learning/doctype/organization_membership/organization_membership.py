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

	def after_insert(self):
		self.догнать_назначения()

	def догнать_назначения(self) -> int:
		"""Выдаёт новому участнику курсы, назначенные организации раньше.

		`Why:` назначение считает состав на момент выдачи. Без этого сотрудник,
		вышедший на работу после назначения курса, остаётся незачисленным —
		и выясняется это в день дедлайна.
		"""
		from lms_agent.agent_learning.doctype.course_allocation.course_allocation import (
			досрочные_назначения_организации,
		)

		if frappe.db.get_value("Learning Organization", self.organization, "status") != "Active":
			return 0

		создано = 0
		for имя in досрочные_назначения_организации(self.organization):
			создано += frappe.get_doc("Course Allocation", имя).выдать_зачисления(
				участники=[self.user]
			)
		return создано

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
