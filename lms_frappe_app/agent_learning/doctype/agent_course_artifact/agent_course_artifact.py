# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

import frappe

from lms_frappe_app.agent_learning.directives import ВерсионированнаяДиректива

РАСКЛАДКИ = ("sections", "canvas")


def нормализовать_ключ(значение: str | None) -> str:
	"""Ключи блоков и документов сравниваются без учёта регистра и пробелов."""
	return (значение or "").strip().lower()


class AgentCourseArtifact(ВерсионированнаяДиректива):
	"""Схема артефакта: из каких блоков он состоит и как рисуется.

	Версионируется как директива: правка схемы не должна менять смысл того,
	что ученик уже заполнил. Содержимое хранится по ключу блока, поэтому
	добавленный блок появится пустым, а убранный — исчезнет со страницы, не
	стирая написанного.

	Схема адресована автору: роль `LMS Student` прав на неё не имеет, ученик
	получает блоки вместе с содержимым через whitelisted-метод.
	"""

	ПОЛЯ_ВЛАДЕЛЬЦА = ("course", "slug")

	def validate(self):
		super().validate()
		self.slug = нормализовать_ключ(self.slug)
		if not self.slug:
			frappe.throw(frappe._("Ключ артефакта обязателен"))
		if self.layout not in РАСКЛАДКИ:
			self.layout = РАСКЛАДКИ[0]

		ключи = [нормализовать_ключ(блок.block_key) for блок in self.blocks]
		if any(not ключ for ключ in ключи):
			frappe.throw(frappe._("У каждого блока артефакта есть ключ"))
		if len(ключи) != len(set(ключи)):
			frappe.throw(frappe._("Ключи блоков в артефакте не повторяются"))
		for блок, ключ in zip(self.blocks, ключи, strict=True):
			блок.block_key = ключ
			# Ширина меньше единицы — блок, которого на канвасе не видно.
			блок.span = max(1, int(блок.span or 1))
