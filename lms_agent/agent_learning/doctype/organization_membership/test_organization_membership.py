# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_agent.agent_learning.doctype.course_allocation.course_allocation import (
	сверить_зачисления,
)
from lms_agent.agent_learning.sample_data import (
	добавить_в_организацию,
	создать_курс,
	создать_организацию,
	создать_ученика,
)

НОВИЧОК = "novichok@example.com"
СТАРОЖИЛ = "starozhil@example.com"


class IntegrationTestOrganizationMembership(IntegrationTestCase):
	"""Доприём: курсы, назначенные до прихода сотрудника."""

	def setUp(self):
		self.организация = создать_организацию(f"Компания {frappe.generate_hash(length=6)}")
		self.курс = создать_курс(f"Курс {frappe.generate_hash(length=6)}")
		создать_ученика(НОВИЧОК)
		создать_ученика(СТАРОЖИЛ)
		добавить_в_организацию(СТАРОЖИЛ, self.организация)

	def назначить(self, **поля):
		return frappe.get_doc(
			{
				"doctype": "Course Allocation",
				"organization": self.организация,
				"course": self.курс,
				**поля,
			}
		).insert(ignore_permissions=True)

	def записан(self, user: str, course: str | None = None) -> bool:
		return bool(
			frappe.db.exists("LMS Enrollment", {"member": user, "course": course or self.курс})
		)

	def test_новый_участник_получает_назначенный_ранее_курс(self):
		self.назначить()
		self.assertFalse(self.записан(НОВИЧОК))

		добавить_в_организацию(НОВИЧОК, self.организация)

		self.assertTrue(self.записан(НОВИЧОК))

	def test_поимённое_назначение_новичку_не_достаётся(self):
		# У поимённого назначения адресат задан явно: человека, которого в
		# списке нет, курс не касается.
		self.назначить(audience="Selected Members", members=[{"user": СТАРОЖИЛ}])

		добавить_в_организацию(НОВИЧОК, self.организация)

		self.assertFalse(self.записан(НОВИЧОК))

	def test_участник_приостановленной_организации_курс_не_получает(self):
		self.назначить()
		frappe.db.set_value("Learning Organization", self.организация, "status", "Suspended")

		добавить_в_организацию(НОВИЧОК, self.организация)

		self.assertFalse(self.записан(НОВИЧОК))

	def test_сверка_догоняет_членство_созданное_в_обход_хука(self):
		self.назначить()
		# Имитируем импорт: строка появляется прямо в базе, хуки не выполняются.
		frappe.db.sql(
			"""insert into `tabOrganization Membership`
			(name, user, organization, role, creation, modified, owner, modified_by, docstatus, idx)
			values (%s, %s, %s, 'Member', now(), now(), 'Administrator', 'Administrator', 0, 0)""",
			(frappe.generate_hash(length=10), НОВИЧОК, self.организация),
		)
		self.assertFalse(self.записан(НОВИЧОК))

		сверить_зачисления()

		self.assertTrue(self.записан(НОВИЧОК))

	def test_повторная_сверка_не_плодит_зачисления(self):
		self.назначить()
		добавить_в_организацию(НОВИЧОК, self.организация)

		сверить_зачисления()
		сверить_зачисления()

		записи = frappe.get_all(
			"LMS Enrollment", filters={"member": НОВИЧОК, "course": self.курс}
		)
		self.assertEqual(len(записи), 1)
