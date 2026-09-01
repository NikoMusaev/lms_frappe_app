# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from lms_agent.agent_learning.doctype.learning_organization.learning_organization import (
	LearningOrganization,
)

ВСЕ_РОЛИ_УЧАСТНИКОВ = ("Member", "Manager", "Org Admin")


class CourseAllocation(Document):
	"""Назначение курса организации или отдельным её участникам.

	Названо не `Assignment`: в Frappe Learning `LMS Assignment` — это домашнее
	задание ученика, и совпадение имён путало бы при каждом чтении кода.

	Сохранение порождает `LMS Enrollment` — зачисление остаётся единственным
	основанием доступа к курсу, и второго источника правды о том, кто на что
	записан, не появляется.
	"""

	def validate(self):
		self._проверить_курс_разрешён()
		if self.audience == "Whole Organization":
			# Список адресатов при назначении на всю организацию только
			# вводит в заблуждение: состав считается на момент выдачи.
			self.members = []

	def on_update(self):
		self.выдать_зачисления()

	def _проверить_курс_разрешён(self) -> None:
		организация: LearningOrganization = frappe.get_doc(
			"Learning Organization", self.organization
		)
		if организация.status != "Active":
			frappe.throw(
				frappe._("Организация {0} приостановлена").format(self.organization)
			)
		if not организация.разрешает_курс(self.course):
			frappe.throw(
				frappe._("Курс {0} не открыт организации {1}").format(
					self.course, self.organization
				)
			)

	def адресаты(self) -> list[str]:
		"""Кому предназначено назначение."""
		if self.audience == "Selected Members":
			return [строка.user for строка in self.members]
		return frappe.get_all(
			"Organization Membership",
			filters={"organization": self.organization, "role": ("in", ВСЕ_РОЛИ_УЧАСТНИКОВ)},
			pluck="user",
		)

	def выдать_зачисления(self, участники: list[str] | None = None) -> int:
		"""Создаёт недостающие зачисления, возвращает число созданных.

		Существующие не трогает: у зачисления есть свой прогресс, и
		пересоздание обнулило бы пройденное.

		`участники` сужает выдачу до конкретных людей — так доприём одного
		сотрудника не заставляет перебирать всю организацию.
		"""
		создано = 0
		цели = участники if участники is not None else self.адресаты()
		for участник in цели:
			уже_записан = frappe.db.exists(
				"LMS Enrollment", {"member": участник, "course": self.course}
			)
			if уже_записан:
				continue
			frappe.get_doc(
				{
					"doctype": "LMS Enrollment",
					"member": участник,
					"course": self.course,
					"member_type": "Student",
				}
			).insert(ignore_permissions=True)
			создано += 1
		return создано


def досрочные_назначения_организации(organization: str) -> list[str]:
	"""Назначения на всю организацию — те, что достаются и новичкам.

	Поимённые сюда не входят: у них адресат задан явно, и человек, которого
	в списке нет, курс получить не должен.
	"""
	return frappe.get_all(
		"Course Allocation",
		filters={"organization": organization, "audience": "Whole Organization"},
		pluck="name",
	)


def сверить_зачисления() -> int:
	"""Ежесуточная сверка: выдаёт зачисления, которые не выдал хук.

	`Why:` членство может появиться в обход хука — импортом, миграцией или
	правкой в базе. Тогда сотрудник тихо остаётся без обязательного курса, и
	обнаруживается это в день дедлайна.

	Приостановленные организации пропускаются: их доступ отозван осознанно.
	"""
	действующие = frappe.get_all(
		"Learning Organization", filters={"status": "Active"}, pluck="name"
	)
	if not действующие:
		return 0

	создано = 0
	назначения = frappe.get_all(
		"Course Allocation", filters={"organization": ("in", действующие)}, pluck="name"
	)
	for имя in назначения:
		создано += frappe.get_doc("Course Allocation", имя).выдать_зачисления()
	return создано


def назначения_пользователя(user: str, course: str | None = None) -> list[dict]:
	"""Действующие назначения пользователя — с дедлайнами и обязательностью.

	Нужна и инструменту `list_my_courses`, и отчёту менеджера: дедлайн живёт
	в назначении, а не в зачислении, и без этой связки просрочку не показать.
	"""
	from lms_agent.agent_learning.doctype.learning_organization.learning_organization import (
		организации_пользователя,
	)

	организации = организации_пользователя(user)
	if not организации:
		return []

	фильтры = {"organization": ("in", организации)}
	if course:
		фильтры["course"] = course

	назначения = frappe.get_all(
		"Course Allocation",
		filters=фильтры,
		fields=["name", "organization", "course", "audience", "deadline", "mandatory"],
	)
	свои = []
	for назначение in назначения:
		if назначение.audience == "Whole Organization" or frappe.db.exists(
			"Course Allocation Member", {"parent": назначение.name, "user": user}
		):
			свои.append(назначение)
	return свои
