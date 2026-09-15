# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Заглушка пункта «Заниматься в браузере» уходит из-под пути `/chat` (lms-platform#142).

`Why:` Traefik отдаёт сервису mcp всё, что начинается с `/chat`, и заглушка
`/chat-sidebar` отвечала «Not Found» MCP-сервиса вместо переадресации в чат.
Пункт с маршрутом `study-in-browser` заводит `after_migrate`; заглушка
`chat-sidebar` и её строка в сайдбаре удаляются здесь один раз.
"""

import frappe

МАРШРУТ = "chat-sidebar"


def execute():
	for заглушка in frappe.get_all("Web Page", filters={"route": МАРШРУТ}, pluck="name"):
		настройки = frappe.get_single("LMS Settings")
		строки = [строка for строка in настройки.sidebar_items if строка.web_page != заглушка]
		if len(строки) != len(настройки.sidebar_items):
			настройки.set("sidebar_items", строки)
			настройки.save(ignore_permissions=True)
		frappe.delete_doc("Web Page", заглушка, ignore_permissions=True, force=True)
