# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Настройка при установке и миграции."""

import frappe

ПУНКТ = {"route": "agent", "title": "Подключить агента", "icon": "bot"}


def обеспечить_пункт_сайдбара() -> None:
	"""Пункт «Подключить агента» в сайдбаре Frappe Learning.

	Сайдбар читает дочернюю таблицу `LMS Settings.sidebar_items`; строка с
	`route` уводит на страницу обычной ссылкой. Идемпотентно: вызывается и
	при установке, и при каждой миграции.
	"""
	фильтры = {
		"parenttype": "LMS Settings",
		"parentfield": "sidebar_items",
		"parent": "LMS Settings",
		"route": ПУНКТ["route"],
	}
	if frappe.db.exists("LMS Sidebar Item", фильтры):
		return
	настройки = frappe.get_single("LMS Settings")
	настройки.append("sidebar_items", ПУНКТ)
	настройки.save(ignore_permissions=True)


def after_install() -> None:
	обеспечить_пункт_сайдбара()


def after_migrate() -> None:
	обеспечить_пункт_сайдбара()
