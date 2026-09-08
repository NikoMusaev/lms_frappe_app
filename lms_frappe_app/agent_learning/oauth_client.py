# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Роли OAuth-клиентов агентов.

Агент ученика или куратора регистрирует OAuth-клиента во Frappe сам
(динамическая регистрация) и авторизуется им от имени пользователя. Frappe
при этом разрешает клиент только `Desk User`, и ученик без desk-доступа
получал на странице авторизации «Invalid client_id parameter value» —
то есть не мог подключить агента вообще. Роли платформы добавляются каждому
клиенту; `Desk User` не отнимается.
"""

import frappe

РОЛИ_ПЛАТФОРМЫ = ("LMS Student", "Course Creator")


def разрешить_роли_платформы(doc, method=None) -> None:
	"""Хук `validate` OAuth Client: идёт после `add_default_role` Frappe."""
	есть = {р.role for р in doc.allowed_roles}
	for роль in РОЛИ_ПЛАТФОРМЫ:
		if роль not in есть:
			doc.append("allowed_roles", {"role": роль})


def добить_роли_существующим() -> None:
	"""Клиенты, созданные до хука. Идемпотентно: используется патчем."""
	for имя in frappe.get_all("OAuth Client", pluck="name"):
		клиент = frappe.get_doc("OAuth Client", имя)
		было = len(клиент.allowed_roles)
		разрешить_роли_платформы(клиент)
		if len(клиент.allowed_roles) != было:
			клиент.save(ignore_permissions=True)
