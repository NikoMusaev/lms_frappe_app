# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Данные для тестов: минимальная цепочка курса и учебные пользователи.

Живёт отдельным модулем, потому что нужна и тестам директивы, и тестам
занятий, и всему, что придёт следом.
"""

import frappe


def создать_урок(название: str = "Урок") -> str:
	"""Минимальная цепочка курс → глава → урок, возвращает имя урока."""
	course = frappe.get_doc(
		{
			"doctype": "LMS Course",
			"title": f"Курс для тестов ({название})",
			"short_introduction": "Курс для тестов",
			"description": "<p>Курс для тестов</p>",
			"published": 0,
			# instructors обязателен у LMS Course — без него вставка падает
			# с MandatoryError, а сообщение указывает на таблицу, а не на поле.
			"instructors": [{"instructor": "Administrator"}],
		}
	).insert(ignore_permissions=True)
	chapter = frappe.get_doc(
		{"doctype": "Course Chapter", "title": "Глава", "course": course.name}
	).insert(ignore_permissions=True)
	lesson = frappe.get_doc(
		{"doctype": "Course Lesson", "title": название, "chapter": chapter.name}
	).insert(ignore_permissions=True)
	return lesson.name


def создать_ученика(почта: str) -> str:
	"""Пользователь с ролью ученика."""
	if not frappe.db.exists("User", почта):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": почта,
				"first_name": почта.split("@")[0],
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		user.add_roles("LMS Student")
	return почта


def создать_организацию(название: str, **поля) -> str:
	"""Организация с политикой по умолчанию."""
	if frappe.db.exists("Learning Organization", название):
		return название
	return frappe.get_doc(
		{"doctype": "Learning Organization", "organization_name": название, **поля}
	).insert(ignore_permissions=True).name


def добавить_в_организацию(user: str, organization: str, role: str = "Member") -> str:
	return frappe.get_doc(
		{
			"doctype": "Organization Membership",
			"user": user,
			"organization": organization,
			"role": role,
		}
	).insert(ignore_permissions=True).name


def создать_курс(название: str) -> str:
	"""Курс без глав — когда урок не нужен, а курс нужен."""
	return frappe.get_doc(
		{
			"doctype": "LMS Course",
			"title": название,
			"short_introduction": "Курс для тестов",
			"description": "<p>Курс для тестов</p>",
			"published": 0,
			"instructors": [{"instructor": "Administrator"}],
		}
	).insert(ignore_permissions=True).name


def создать_менеджера(почта: str, organization: str) -> str:
	"""Пользователь с ролью менеджера и членством в организации.

	Роль Frappe даёт возможность смотреть отчёты, членство — определяет, по
	каким именно организациям. Без второго роль не открывает ничего.
	"""
	создать_ученика(почта)
	пользователь = frappe.get_doc("User", почта)
	пользователь.add_roles("Organization Manager")
	if not frappe.db.exists(
		"Organization Membership", {"user": почта, "organization": organization}
	):
		frappe.get_doc(
			{
				"doctype": "Organization Membership",
				"user": почта,
				"organization": organization,
				"role": "Manager",
			}
		).insert(ignore_permissions=True)
	return почта
