# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Страница «Подключить агента»: адреса MCP и шаги подключения под роль.

Здесь только механика платформы — куда подключаться и как войти. Чему учить
и как вести занятие, страница не знает: это закрытая часть.
"""

import frappe
from frappe.utils import get_url

no_cache = 1

ИСХОДНИКИ = "https://github.com/NikoMusaev/lms_frappe_app"
#: Frappe пускает не больше стольких регистраций OAuth-клиентов; клиент
#: регистрируется при каждом новом подключении.
ЛИМИТ_РЕГИСТРАЦИЙ = "5 подключений за 10 минут"
РОЛИ_КУРАТОРА = {"Course Creator", "Moderator"}


def сведения(пользователь: str) -> dict:
	"""Что показать на странице этому пользователю."""
	сайт = get_url().rstrip("/")
	гость = пользователь == "Guest"
	роли = set() if гость else set(frappe.get_roles(пользователь))
	куратор = bool(роли & РОЛИ_КУРАТОРА)
	подключения = []
	if not гость:
		подключения.append(
			{
				"role": "student",
				"title": "Учиться",
				"url": f"{сайт}/mcp",
				"first_step": "Попросите агента показать ваши курсы и начать урок.",
			}
		)
	if куратор:
		подключения.append(
			{
				"role": "curator",
				"title": "Собирать курсы",
				"url": f"{сайт}/authoring",
				"first_step": (
					"Первым вызовом попросите агента вызвать authoring_guide: "
					"это порядок сборки и правила платформы."
				),
			}
		)
	return {
		"site_url": сайт,
		"is_guest": гость,
		"is_curator": куратор,
		"connections": подключения,
		"login_url": "/login?redirect-to=/agent",
		"registration_limit": ЛИМИТ_РЕГИСТРАЦИЙ,
		"source_url": ИСХОДНИКИ,
	}


def get_context(context):
	context.no_breadcrumbs = True
	context.title = "Подключить агента"
	context.update(сведения(frappe.session.user))
	return context
