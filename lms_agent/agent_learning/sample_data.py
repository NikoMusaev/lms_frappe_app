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


def создать_вопрос(
	текст: str,
	варианты: list[tuple[str, bool]] | None = None,
	возможные_ответы: list[str] | None = None,
	пояснение: str | None = None,
) -> str:
	"""Вопрос с вариантами (Choices) или со свободным вводом (User Input)."""
	поля = {"doctype": "LMS Question", "question": текст}
	if возможные_ответы is not None:
		поля["type"] = "User Input"
		for номер, ответ in enumerate(возможные_ответы, start=1):
			поля[f"possibility_{номер}"] = ответ
	else:
		поля["type"] = "Choices"
		верных = sum(1 for _, верный in варианты or [] if верный)
		поля["multiple"] = int(верных > 1)
		for номер, (вариант, верный) in enumerate(варианты or [], start=1):
			поля[f"option_{номер}"] = вариант
			поля[f"is_correct_{номер}"] = int(верный)
			if верный and пояснение:
				поля[f"explanation_{номер}"] = пояснение
	return frappe.get_doc(поля).insert(ignore_permissions=True).name


def создать_квиз(lesson: str, вопросы: list[str], баллов_за_вопрос: int = 1) -> str:
	"""Квиз урока. Привязывается и через quiz_id урока — так его ищет Frappe."""
	курс = frappe.db.get_value(
		"Course Chapter", frappe.db.get_value("Course Lesson", lesson, "chapter"), "course"
	)
	квиз = frappe.get_doc(
		{
			"doctype": "LMS Quiz",
			"title": f"Квиз {frappe.generate_hash(length=6)}",
			"lesson": lesson,
			"course": курс,
			"total_marks": len(вопросы) * баллов_за_вопрос,
			"passing_percentage": 80,
			"questions": [
				{"question": вопрос, "marks": баллов_за_вопрос} for вопрос in вопросы
			],
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("Course Lesson", lesson, "quiz_id", квиз.name)
	return квиз.name


def создать_занятие(student: str, lesson: str) -> str:
	return frappe.get_doc(
		{"doctype": "Agent Learning Session", "student": student, "lesson": lesson}
	).insert(ignore_permissions=True).name
