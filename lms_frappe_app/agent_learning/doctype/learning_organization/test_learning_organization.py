# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Организация-клиент: политика квиза, домены и список курсов.

`Why:` строгость зачёта у корпоративных клиентов разная, и задаётся она
здесь — одним набором полей, где пустое значит «как в общих настройках».
Правило про пустое живёт в одной функции, но ошибиться в нём можно тихо:
организация, «унаследовавшая» ноль попыток, заблокировала бы курс целиком.
"""

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.doctype.learning_organization.learning_organization import (
	политика_квиза,
)
from lms_frappe_app.tests.sample_data import политика_по_умолчанию, создать_курс, создать_организацию


class IntegrationTestLearningOrganization(IntegrationTestCase):
	def setUp(self):
		политика_по_умолчанию()
		self.организация = создать_организацию(f"Компания {frappe.generate_hash(length=6)}")

	def правка(self, **поля):
		организация = frappe.get_doc("Learning Organization", self.организация)
		организация.update(поля)
		организация.save(ignore_permissions=True)
		return организация

	# --- политика квиза ---

	def test_организация_перекрывает_только_заданные_поля(self):
		# Пустое поле означает «как в общих настройках»: организация не обязана
		# дублировать значения, которые её устраивают.
		политика = политика_квиза(self.организация)
		self.assertEqual(политика["pass_threshold"], 0.8)
		self.assertEqual(политика["max_attempts"], 3)

		self.правка(pass_threshold=0.9)

		политика = политика_квиза(self.организация)
		self.assertEqual(политика["pass_threshold"], 0.9)
		self.assertEqual(политика["max_attempts"], 3)

	def test_ноль_попыток_читается_как_наследование(self):
		"""`Why:` Frappe отдаёт незаполненный Int нулём, и отличить «не трогали»
		от «выставили ноль» негде. Выбрано безопасное при недосмотре: унаследовать
		ограничение, а не снять его — «без лимита» задаётся в общих настройках."""
		self.правка(max_attempts=0, retry_delay_hours=0)

		политика = политика_квиза(self.организация)

		self.assertEqual(политика["max_attempts"], 3)
		self.assertEqual(политика["retry_delay_hours"], 1)

	def test_требование_квиза_перекрывается_и_наследуется(self):
		self.правка(quiz_required="No")
		self.assertFalse(политика_квиза(self.организация)["quiz_required"])

		self.правка(quiz_required="Yes")
		self.assertTrue(политика_квиза(self.организация)["quiz_required"])

		# Пустое — как в общих настройках, где квиз обязателен.
		self.правка(quiz_required="")
		self.assertTrue(политика_квиза(self.организация)["quiz_required"])

	def test_без_организации_политика_общая(self):
		"""Частный ученик учится по общим настройкам, а не без правил вовсе."""
		политика = политика_квиза()

		self.assertEqual(политика["pass_threshold"], 0.8)
		self.assertEqual(политика["max_attempts"], 3)

	# --- проверки при сохранении ---

	def test_недопустимый_порог_отклоняется(self):
		with self.assertRaises(frappe.ValidationError):
			self.правка(pass_threshold=80)

	def test_отрицательное_число_попыток_отклоняется(self):
		with self.assertRaises(frappe.ValidationError):
			self.правка(max_attempts=-1)

	def test_домены_приводятся_к_единому_виду(self):
		организация = self.правка(email_domains="@Example.COM\n\n example.com \nzavod.ru")

		self.assertEqual(организация.email_domains, "example.com\nzavod.ru")

	# --- список курсов ---

	def test_пустой_список_курсов_означает_весь_каталог(self):
		"""`Why:` у большинства клиентов ограничений нет, и перечислять курс за
		курсом они не обязаны — список рано или поздно разъедется с каталогом."""
		организация = frappe.get_doc("Learning Organization", self.организация)

		self.assertTrue(организация.разрешает_курс(создать_курс("Любой курс")))

	def test_непустой_список_закрывает_остальные_курсы(self):
		разрешённый = создать_курс(f"Разрешённый {frappe.generate_hash(length=6)}")
		посторонний = создать_курс(f"Посторонний {frappe.generate_hash(length=6)}")
		организация = self.правка(allowed_courses=[{"course": разрешённый}])

		self.assertTrue(организация.разрешает_курс(разрешённый))
		self.assertFalse(организация.разрешает_курс(посторонний))
