# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Куда попадает вошедший человек."""

import frappe

УЧЕБНАЯ = "lms"


def домашняя_страница(user: str) -> str | None:
	"""Ученику — каталог курсов, сотруднику платформы — ничего.

	`Why:` `get_home_page_via_hooks` вызывается для всех подряд и не смотрит
	на тип пользователя. Прежний строковый хук уводил в `/lms` и
	администратора: он входил и оказывался в ученическом интерфейсе вместо
	desk, потому что до ветки «`me` для System User» дело уже не доходило.

	`None` означает «решай сам»: Frappe продолжит перебор и приведёт
	сотрудника платформы туда, куда привёл бы без нас.
	"""
	if frappe.db.get_value("User", user, "user_type") == "System User":
		return None
	return УЧЕБНАЯ
