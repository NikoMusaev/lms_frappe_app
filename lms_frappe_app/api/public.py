# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Витрина курса — методы контракта, доступные без входа.

`Why:` карту курса показывают и гостю, которому курс открывают до
регистрации. Остальные методы требуют входа: у них есть ученик, чьи данные
они отдают, а здесь наружу идёт только состав курса и цели его уроков.
"""

import frappe

from lms_frappe_app.agent_learning import directives
from lms_frappe_app.agent_learning.errors import Отказ
from lms_frappe_app.agent_learning.structure import уроки_по_главам
from lms_frappe_app.api import контракт
from lms_frappe_app.api.authoring import КУРС_НЕ_НАЙДЕН


@frappe.whitelist(allow_guest=True, methods=["GET"])
@контракт
def course_map(course: str) -> dict:
	"""Карта курса: главы, уроки, цели уроков и покрытие целей.

	Покрытие приходит только зачисленному и только его собственное: у цели
	появляется поле `status`. Прочим поля нет вовсе — `null` был бы
	неотличим от «цель не разобрана», а отсутствие ключа спутать не с чем.

	Из директивы наружу выходят ровно две вещи: цели и иконка. Всё
	остальное — как вести урок, проверочные вопросы, заблуждения, критерии —
	остаётся на сервере.
	"""
	зачислен = _зачислен(course)
	if not зачислен and not frappe.db.get_value("LMS Course", course, "published"):
		# Непубликованный курс для постороннего не существует. Отказ доменный,
		# а не 404: тем же кодом отвечают методы авторинга на чужой курс.
		raise Отказ(КУРС_НЕ_НАЙДЕН, "Курс не найден", id=course)

	структура = уроки_по_главам(course)
	порядок = [урок for глава in структура for урок in глава["lessons"]]
	названия = _названия(порядок)
	из_директив = {урок: _директива_карты(урок) for урок in порядок}
	покрытие = _покрытие(порядок) if зачислен else {}
	номера = {урок: номер for номер, урок in enumerate(порядок, start=1)}

	return {
		"course": course,
		"title": frappe.db.get_value("LMS Course", course, "title"),
		"chapters": [
			{
				"title": глава["title"],
				"lessons": [
					{
						"id": урок,
						"number": номера[урок],
						"title": названия.get(урок),
						"icon": из_директив[урок]["icon"],
						"objectives": [
							_цель(цель, покрытие.get(урок, {}))
							for цель in из_директив[урок]["objectives"]
						],
					}
					for урок in глава["lessons"]
				],
			}
			for глава in структура
		],
	}


def _цель(цель: str, покрытие_урока: dict[str, str]) -> dict:
	"""Цель карты: текст всегда, статус — только если по ней был отчёт."""
	если_есть = {"status": покрытие_урока[цель]} if цель in покрытие_урока else {}
	return {"text": цель, **если_есть}


def _зачислен(course: str) -> bool:
	"""Записан ли вызывающий на курс. Гость — никогда."""
	пользователь = frappe.session.user
	if not пользователь or пользователь == "Guest":
		return False
	return bool(frappe.db.exists("LMS Enrollment", {"member": пользователь, "course": course}))


def _названия(уроки: list[str]) -> dict[str, str]:
	"""Названия уроков одним запросом на весь курс."""
	if not уроки:
		return {}
	return {
		урок.name: урок.title
		for урок in frappe.get_all(
			"Course Lesson", filters={"name": ("in", уроки)}, fields=["name", "title"]
		)
	}


def _директива_карты(урок: str) -> dict:
	"""Цели и иконка действующей директивы урока — то немногое, что видно снаружи."""
	найденная = directives.запись(
		"Agent Lesson Directive", {"lesson": урок}, ("objectives", "map_icon")
	)
	if not найденная:
		return {"objectives": [], "icon": None}
	return {
		"objectives": directives.строки(найденная.objectives),
		"icon": найденная.map_icon or None,
	}


def _покрытие(уроки: list[str]) -> dict[str, dict[str, str]]:
	"""Покрытие целей вызывающего по урокам курса: `{урок: {цель: статус}}`.

	Занятий по одному уроку может быть несколько — урок открывают повторно.
	Побеждает более позднее: карта показывает, как дела обстоят сейчас, а не
	как обстояли на первом заходе.
	"""
	if not уроки:
		return {}
	занятия = frappe.get_all(
		"Agent Learning Session",
		filters={"student": frappe.session.user, "lesson": ("in", уроки)},
		fields=["name", "lesson"],
		order_by="creation asc",
	)
	if not занятия:
		return {}

	урок_занятия = {занятие.name: занятие.lesson for занятие in занятия}
	порядок = {занятие.name: номер for номер, занятие in enumerate(занятия)}
	строки = frappe.get_all(
		"Agent Objective Outcome",
		filters={"parent": ("in", list(урок_занятия)), "parenttype": "Agent Learning Session"},
		fields=["parent", "objective", "status"],
	)

	покрытие: dict[str, dict[str, str]] = {}
	# Сортировка по времени занятия, а не по имени: имена — хеши, и порядок по
	# ним случаен. От него зависит, чей статус останется последним.
	for строка in sorted(строки, key=lambda строка: порядок[строка.parent]):
		покрытие.setdefault(урок_занятия[строка.parent], {})[строка.objective] = строка.status
	return покрытие
