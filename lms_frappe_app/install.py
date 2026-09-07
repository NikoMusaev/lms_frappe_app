# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Настройка при установке и миграции."""

import frappe

#: Web Page — обязательное поле пункта, а `route` и `title` пункт берёт из неё
#: (`fetch_from`). Заглушка не публикуется: сама страница живёт в коде по
#: адресу /agent, а с /agent-sidebar на неё ведёт `website_redirects` в hooks.
ЗАГЛУШКА = {"title": "Подключить агента", "route": "agent-sidebar"}
ИКОНКА = "bot"


def обеспечить_пункт_сайдбара() -> None:
	"""Пункт «Подключить агента» в сайдбаре Frappe Learning.

	Сайдбар читает дочернюю таблицу `LMS Settings.sidebar_items` и ведёт по
	`route` обычной ссылкой. Идемпотентно: вызывается и при установке, и при
	каждой миграции.
	"""
	заглушка = _заглушка()
	фильтры = {
		"parenttype": "LMS Settings",
		"parentfield": "sidebar_items",
		"parent": "LMS Settings",
		"web_page": заглушка,
	}
	if frappe.db.exists("LMS Sidebar Item", фильтры):
		return
	настройки = frappe.get_single("LMS Settings")
	настройки.append("sidebar_items", {"web_page": заглушка, "icon": ИКОНКА})
	настройки.save(ignore_permissions=True)


def _заглушка() -> str:
	имя = frappe.db.get_value("Web Page", {"route": ЗАГЛУШКА["route"]})
	if имя:
		return имя
	return (
		frappe.get_doc(
			{
				"doctype": "Web Page",
				"published": 0,
				"content_type": "Rich Text",
				"main_section": "<p>Страница живёт в приложении: /agent.</p>",
				**ЗАГЛУШКА,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def after_install() -> None:
	обеспечить_пункт_сайдбара()


def after_migrate() -> None:
	обеспечить_пункт_сайдбара()
