# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AgentLessonDirective(Document):
	"""Инструкция преподавателю по конкретному уроку.

	Не контент для ученика: тексты отсюда адресованы агенту, который ведёт
	занятие. Ученику директива не показывается, и роль `LMS Student` не имеет
	к этому DocType никаких прав.

	Директивы переписываются чаще самих уроков, поэтому у урока может быть
	несколько версий — действующей считается ровно одна.
	"""

	def before_insert(self):
		# Версию всегда считает система: поле read_only, и переданное значение
		# намеренно затирается. Иначе импорт директивы с проставленной версией
		# тихо создаст вторую «версию 1» на тот же урок.
		self.version = self._next_version()

	def validate(self):
		if self.version < 1:
			frappe.throw(frappe._("Версия директивы начинается с единицы"))

	def on_update(self):
		if self.is_active:
			self._deactivate_others()

	def _next_version(self) -> int:
		"""Следующий номер версии для этого урока."""
		previous = frappe.get_all(
			self.doctype,
			filters={"lesson": self.lesson},
			pluck="version",
			order_by="version desc",
			limit=1,
		)
		return (previous[0] if previous else 0) + 1

	def _deactivate_others(self) -> None:
		"""Снимает признак действующей с прочих версий этого урока.

		Инвариант «на урок ровно одна действующая директива» держится здесь, а
		не в вызывающем коде: иначе агент однажды получит две директивы разом и
		молча возьмёт любую.
		"""
		others = frappe.get_all(
			self.doctype,
			filters={"lesson": self.lesson, "is_active": 1, "name": ("!=", self.name)},
			pluck="name",
		)
		for name in others:
			# set_value, а не сохранение документа: чужие версии трогаем точечно
			# и без повторного запуска хуков, иначе получим рекурсию.
			frappe.db.set_value(self.doctype, name, "is_active", 0, update_modified=False)
