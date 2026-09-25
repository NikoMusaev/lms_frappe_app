# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Окно «Установить Frappe Learning» на телефоне больше не всплывает.

`Why:` при первом заходе с телефона окно закрывало собой каталог курсов —
лишний экран на пути ученика и чужое имя продукта (learning-services#301).
Флаг `LMS Settings.disable_pwa` в Learning прячет только это окно: манифест и
установка из меню браузера остаются.

Патч, а не `after_migrate`: включить флаг нужно один раз. Админ, вернувший
окно галочкой в настройках Learning, миграцией не переспорен.
"""

import frappe


def execute():
	frappe.db.set_single_value("LMS Settings", "disable_pwa", 1)
