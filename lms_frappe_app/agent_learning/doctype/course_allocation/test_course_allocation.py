# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_frappe_app.agent_learning.doctype.course_allocation.course_allocation import (
	назначения_пользователя,
)
from lms_frappe_app.agent_learning.doctype.learning_organization.learning_organization import (
	политика_квиза,
)
from lms_frappe_app.agent_learning.sample_data import (
	политика_по_умолчанию,
	добавить_в_организацию,
	создать_курс,
	создать_организацию,
	создать_ученика,
)

ПЕРВЫЙ = "sotrudnik-odin@example.com"
ВТОРОЙ = "sotrudnik-dva@example.com"


class IntegrationTestCourseAllocation(IntegrationTestCase):
	"""Организации, членство, назначение курсов и политика квиза."""

	def setUp(self):
		политика_по_умолчанию()
		self.организация = создать_организацию(f"Компания {frappe.generate_hash(length=6)}")
		self.курс = создать_курс(f"Курс {frappe.generate_hash(length=6)}")
		создать_ученика(ПЕРВЫЙ)
		создать_ученика(ВТОРОЙ)

	def назначить(self, **поля):
		return frappe.get_doc(
			{
				"doctype": "Course Allocation",
				"organization": self.организация,
				"course": self.курс,
				**поля,
			}
		).insert(ignore_permissions=True)

	# --- членство ---

	def test_повторное_членство_отклоняется(self):
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		with self.assertRaises(frappe.DuplicateEntryError):
			добавить_в_организацию(ПЕРВЫЙ, self.организация)

	def test_пользователь_состоит_в_нескольких_организациях(self):
		другая = создать_организацию(f"Компания {frappe.generate_hash(length=6)}")
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		добавить_в_организацию(ПЕРВЫЙ, другая)  # не должно падать

	# --- назначение порождает зачисление ---

	def test_назначение_на_организацию_записывает_всех_участников(self):
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		добавить_в_организацию(ВТОРОЙ, self.организация, role="Manager")

		self.назначить(audience="Whole Organization", mandatory=1)

		for участник in (ПЕРВЫЙ, ВТОРОЙ):
			self.assertTrue(
				frappe.db.exists("LMS Enrollment", {"member": участник, "course": self.курс}),
				f"{участник} не записан на курс",
			)

	def test_поимённое_назначение_не_задевает_остальных(self):
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		добавить_в_организацию(ВТОРОЙ, self.организация)

		self.назначить(audience="Selected Members", members=[{"user": ПЕРВЫЙ}])

		self.assertTrue(frappe.db.exists("LMS Enrollment", {"member": ПЕРВЫЙ, "course": self.курс}))
		self.assertFalse(frappe.db.exists("LMS Enrollment", {"member": ВТОРОЙ, "course": self.курс}))

	def test_повторное_сохранение_не_плодит_зачисления(self):
		# У зачисления свой прогресс: пересоздание обнулило бы пройденное.
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		назначение = self.назначить()
		назначение.deadline = "2026-12-31"
		назначение.save(ignore_permissions=True)

		записи = frappe.get_all("LMS Enrollment", filters={"member": ПЕРВЫЙ, "course": self.курс})
		self.assertEqual(len(записи), 1)

	# --- ограничения ---

	def test_курс_вне_списка_организации_не_назначается(self):
		организация = frappe.get_doc("Learning Organization", self.организация)
		организация.append("allowed_courses", {"course": создать_курс("Единственный доступный")})
		организация.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			self.назначить()

	def test_пустой_список_курсов_означает_весь_каталог(self):
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		self.назначить()  # не должно падать

	def test_приостановленной_организации_курс_не_назначить(self):
		frappe.db.set_value("Learning Organization", self.организация, "status", "Suspended")
		frappe.clear_document_cache("Learning Organization", self.организация)
		with self.assertRaises(frappe.ValidationError):
			self.назначить()

	# --- дедлайны ---

	def test_назначение_видно_участнику_с_дедлайном(self):
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		назначение = self.назначить(deadline="2026-12-31", mandatory=1)

		# Проверяем конкретную запись, а не длину списка: тестовые пользователи
		# переиспользуются между тестами, и назначения накапливаются.
		мои = {н.name: н for н in назначения_пользователя(ПЕРВЫЙ)}

		self.assertIn(назначение.name, мои)
		self.assertEqual(str(мои[назначение.name].deadline), "2026-12-31")
		self.assertTrue(мои[назначение.name].mandatory)

	def test_чужое_поимённое_назначение_не_попадает_в_список(self):
		добавить_в_организацию(ПЕРВЫЙ, self.организация)
		добавить_в_организацию(ВТОРОЙ, self.организация)
		назначение = self.назначить(audience="Selected Members", members=[{"user": ПЕРВЫЙ}])

		имена = lambda user: [н.name for н in назначения_пользователя(user)]

		self.assertIn(назначение.name, имена(ПЕРВЫЙ))
		self.assertNotIn(назначение.name, имена(ВТОРОЙ))

	# --- политика квиза ---

	def test_политика_по_умолчанию_из_общих_настроек(self):
		политика = политика_квиза(self.организация)
		self.assertEqual(политика["pass_threshold"], 0.8)
		self.assertEqual(политика["max_attempts"], 3)

	def test_организация_перекрывает_только_заданные_поля(self):
		# Пустое поле означает «как в общих настройках»: организация не обязана
		# дублировать значения, которые её устраивают.
		организация = frappe.get_doc("Learning Organization", self.организация)
		организация.pass_threshold = 0.9
		организация.save(ignore_permissions=True)

		политика = политика_квиза(self.организация)

		self.assertEqual(политика["pass_threshold"], 0.9)
		self.assertEqual(политика["max_attempts"], 3)

	def test_недопустимый_порог_отклоняется(self):
		организация = frappe.get_doc("Learning Organization", self.организация)
		организация.pass_threshold = 80
		with self.assertRaises(frappe.ValidationError):
			организация.save(ignore_permissions=True)

	def test_домены_приводятся_к_единому_виду(self):
		организация = frappe.get_doc("Learning Organization", self.организация)
		организация.email_domains = "@Example.COM\n\n example.com \nzavod.ru"
		организация.save(ignore_permissions=True)
		self.assertEqual(организация.email_domains, "example.com\nzavod.ru")
