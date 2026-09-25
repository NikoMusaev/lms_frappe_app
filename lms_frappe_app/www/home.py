# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Куда попадает вошедший человек."""

import frappe

УЧЕБНАЯ = "lms"
РАБОЧАЯ = "desk/agent-learning"


def домашняя_страница(user: str) -> str:
	"""Ученику — каталог курсов, сотруднику платформы — воркспейс Agent Learning.

	`Why:` `get_home_page_via_hooks` вызывается для всех подряд и не смотрит
	на тип пользователя. Прежний строковый хук уводил в `/lms` и
	администратора: он входил и оказывался в ученическом интерфейсе вместо
	desk. Отдельной веткой сотрудник попадал на общий `/desk` — стартовый
	экран приложений, откуда до курсов, учеников и организаций ещё нужно
	дойти (learning-services#302). Воркспейс ведёт ко всему этому сразу.
	"""
	if frappe.db.get_value("User", user, "user_type") == "System User":
		return РАБОЧАЯ
	return УЧЕБНАЯ
