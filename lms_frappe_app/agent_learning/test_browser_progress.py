# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Просмотр урока в браузере не закрывает урок.

`Why:` запись `LMS Course Progress` со статусом `Complete` — единственный
признак пройденного урока для агента и отчёта руководителя. Пока её ставил
таймер страницы урока, агент пропускал урок, который ученик только пролистал
(lms-platform#305).
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning import browser_progress
from lms_frappe_app.tests.sample_data import зачислить, создать_урок, создать_ученика


class IntegrationTestBrowserProgress(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.урок = создать_урок("Урок в браузере")
		self.ученик = создать_ученика(f"browser-{frappe.generate_hash(length=6)}@example.com")
		self.курс = зачислить(self.ученик, self.урок)

	def вызвать(self, **параметры):
		"""Тем путём, которым идёт запрос страницы: через подмену хуком."""
		метод = frappe.override_whitelisted_method(browser_progress.ПОДМЕНЯЕМЫЙ)
		return frappe.call(метод, lesson=self.урок, course=self.курс, **параметры)

	def test_запрос_страницы_уходит_в_подмену(self):
		"""`Why:` без хука страница снова зовёт метод Learning, и урок
		закрывается просмотром — молча, тест на сам модуль этого не заметит."""
		self.assertEqual(
			frappe.override_whitelisted_method(browser_progress.ПОДМЕНЯЕМЫЙ),
			"lms_frappe_app.agent_learning.browser_progress.save_progress",
		)

	def test_просмотр_урока_не_закрывает_урок(self):
		frappe.set_user(self.ученик)

		with self.assertRaises(frappe.ValidationError):
			self.вызвать()

		self.assertFalse(
			frappe.db.exists("LMS Course Progress", {"member": self.ученик, "lesson": self.урок}),
			"урок закрыт без занятия — агент его пропустит",
		)

	def test_прогресс_scorm_идёт_в_learning(self):
		"""SCORM-глава другого пути к прогрессу не имеет — отказ её заморозил бы."""
		frappe.set_user(self.ученик)
		сведения = {"is_complete": True}

		with patch.object(browser_progress, "save_progress_learning", return_value=100) as learning:
			self.assertEqual(self.вызвать(scorm_details=сведения), 100)

		learning.assert_called_once_with(self.урок, self.курс, сведения)
