# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.normalizer import нормализовать_урок
from lms_frappe_app.agent_learning.sample_data import создать_урок


class IntegrationTestNormalizer(IntegrationTestCase):
	"""Нормализация урока, прочитанного из базы."""

	def test_урок_из_базы_приводится_к_markdown(self):
		lesson = создать_урок("Урок с содержимым")
		frappe.db.set_value(
			"Course Lesson",
			lesson,
			"content",
			json.dumps(
				{
					"blocks": [
						{"type": "header", "data": {"text": "Что такое цикл", "level": 2}},
						{"type": "paragraph", "data": {"text": "Повторяет <b>действие</b>."}},
						{
							"type": "embed",
							"data": {"service": "youtube", "source": "https://youtu.be/x"},
						},
					]
				}
			),
		)

		урок = нормализовать_урок(lesson)

		self.assertEqual(урок.title, "Урок с содержимым")
		self.assertIn("## Что такое цикл", урок.сегмент(1))
		self.assertIn("Повторяет действие.", урок.сегмент(1))
		self.assertEqual([м.kind for м in урок.media], ["video"])

	def test_несуществующий_урок_отклоняется(self):
		with self.assertRaises(frappe.DoesNotExistError):
			нормализовать_урок("такого-урока-нет")
