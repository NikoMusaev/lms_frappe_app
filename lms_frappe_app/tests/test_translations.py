# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Свой файл переводов интерфейса.

`Why:` в `frappe/lms` часть строк не переведена, а править её `ru.po` значит
потерять работу при первом обновлении чужого приложения. Frappe читает
`<app>/translations/<lang>.csv` без компиляции и обходит приложения в порядке
установки — наше последнее, поэтому его переводы перекрывают LMS.

Битую строку Frappe не роняет, а молча пишет в лог: без теста испорченный
файл выглядел бы как «часть интерфейса вдруг снова по-английски».
"""

import csv
import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from frappe.translate import get_all_translations

ФАЙЛ = Path(frappe.get_app_path("lms_frappe_app", "translations", "ru.csv"))

ПЛЕЙСХОЛДЕР = re.compile(r"\{[^}]*\}")


def _строки() -> list[list[str]]:
	with ФАЙЛ.open(encoding="utf-8") as ф:
		return list(csv.reader(ф))


class IntegrationTestTranslations(IntegrationTestCase):
	def test_файл_разбирается_и_не_пуст(self):
		строки = _строки()

		self.assertTrue(строки)
		for строка in строки:
			self.assertIn(len(строка), (2, 3), f"неверное число полей: {строка[:1]}")
			self.assertTrue(строка[1].strip(), f"пустой перевод: {строка[0]!r}")

	def test_плейсхолдеры_не_потеряны(self):
		"""`{0}` в переводе подставляется по номеру: потеря ломает фразу."""
		for оригинал, перевод, *_ in _строки():
			self.assertEqual(
				sorted(ПЛЕЙСХОЛДЕР.findall(оригинал)),
				sorted(ПЛЕЙСХОЛДЕР.findall(перевод)),
				f"разошлись плейсхолдеры: {оригинал!r}",
			)

	def test_строк_с_краевыми_пробелами_нет(self):
		"""`Why:` Frappe обрезает перевод (`strip` в `get_translation_dict_from_file`),
		и краевой пробел до платформы не доедет. Такие строки — куски
		предложений из писем: переведёшь — слова слипнутся («опубликован
		наFrappe Learning»). Пусть остаются английскими, это заметно меньше.
		Проверено CI: тест на доставку перевода падал именно на них."""
		с_пробелами = [
			о for о, *_ in _строки() if о[:1] == " " or о[-1:] == " "
		]

		self.assertEqual(с_пробелами, [], "такую строку Frappe обрежет")

	def test_переводы_доезжают_до_платформы(self):
		"""Проверка всей цепочки: файл найден Frappe и попал в общий словарь."""
		словарь = get_all_translations("ru")
		оригинал, перевод = _строки()[0][0], _строки()[0][1]

		self.assertEqual(словарь.get(оригинал), перевод)
