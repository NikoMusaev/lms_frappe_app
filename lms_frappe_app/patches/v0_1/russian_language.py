# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Русский языком платформы — один раз, а не на каждую миграцию (#42).

`Why:` первая попытка ставила язык из `after_migrate` с проверкой «поле
пусто». На стенде оно оказалось не пустым: Frappe при установке пишет туда
`en`, и хук молча выходил — интерфейс оставался английским после трёх
выкаток. Патч выполняется однажды и записывается как выполненный, поэтому
и ставит своё значение, и не спорит с администратором дальше.
"""

import frappe

ЯЗЫК = "ru"


def execute():
	if not frappe.db.exists("Language", ЯЗЫК):
		# `sync_languages` заводит запись на каждой миграции; если её нет,
		# ссылка указывала бы в пустоту.
		return
	frappe.db.set_single_value("System Settings", "language", ЯЗЫК)
	frappe.clear_document_cache("System Settings", "System Settings")
	frappe.cache.delete_key("merged_translations")
