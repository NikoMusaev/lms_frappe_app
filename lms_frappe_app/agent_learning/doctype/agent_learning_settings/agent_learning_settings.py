# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AgentLearningSettings(Document):
	pass


#: Запасное число пробных уроков веб-чата, если настройки почему-то недоступны.
ПРОБНЫХ_УРОКОВ = 2


def пробных_уроков() -> int:
	"""Сколько уроков ученик проходит в веб-чате платформы без своего агента.

	`Why:` число читали из настройки дважды — метод, который лимит проверяет,
	и страница `/agent`, которая его обещает. Страница ради этого импортировала
	константу из API-слоя, то есть знала про методы контракта ради одной цифры;
	разойдясь, обещание и проверка показали бы ученику разное.
	"""
	return (
		frappe.get_cached_value(
			"Agent Learning Settings", "Agent Learning Settings", "web_demo_lessons"
		)
		or ПРОБНЫХ_УРОКОВ
	)
