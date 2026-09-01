# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from lms_agent.agent_learning.access import (
	НЕ_ЗАЧИСЛЕН,
	ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА,
	доступен_курс,
	курсы_ученика,
	политика_квиза_для_курса,
)
from lms_agent.agent_learning.sample_data import (
	политика_по_умолчанию,
	добавить_в_организацию,
	создать_курс,
	создать_организацию,
	создать_ученика,
)


class IntegrationTestAccess(IntegrationTestCase):
	"""Доступ там, где счастливый путь кончается."""

	def setUp(self):
		политика_по_умолчанию()
		self.курс = создать_курс(f"Курс {frappe.generate_hash(length=6)}")
		self.ученик = создать_ученика(f"uch-{frappe.generate_hash(length=6)}@example.com")

	def организация(self, **поля):
		return создать_организацию(f"Компания {frappe.generate_hash(length=6)}", **поля)

	def назначить(self, организация, **поля):
		return frappe.get_doc(
			{
				"doctype": "Course Allocation",
				"organization": организация,
				"course": self.курс,
				**поля,
			}
		).insert(ignore_permissions=True)

	def записать_самостоятельно(self):
		frappe.get_doc(
			{
				"doctype": "LMS Enrollment",
				"member": self.ученик,
				"course": self.курс,
				"member_type": "Student",
			}
		).insert(ignore_permissions=True)

	def мой_курс(self):
		return next((к for к in курсы_ученика(self.ученик) if к["course"] == self.курс), None)

	# --- 1. частный ученик ---

	def test_ученик_без_организации_видит_свои_курсы(self):
		# Источник списка — зачисление. Иначе самозаписавшийся ученик не
		# увидел бы ничего: назначений у него нет вовсе.
		self.записать_самостоятельно()

		курс = self.мой_курс()

		self.assertIsNotNone(курс)
		self.assertIsNone(курс["organization"])
		self.assertIsNone(курс["deadline"])
		self.assertFalse(курс["mandatory"])

	def test_частному_ученику_политика_из_общих_настроек(self):
		self.записать_самостоятельно()
		self.assertEqual(политика_квиза_для_курса(self.ученик, self.курс)["pass_threshold"], 0.8)

	def test_назначение_добавляет_дедлайн_и_обязательность(self):
		организация = self.организация()
		добавить_в_организацию(self.ученик, организация)
		self.назначить(организация, deadline="2026-12-31", mandatory=1)

		курс = self.мой_курс()

		self.assertEqual(str(курс["deadline"]), "2026-12-31")
		self.assertTrue(курс["mandatory"])
		self.assertFalse(курс["overdue"])

	def test_прошедший_дедлайн_помечается_просрочкой(self):
		организация = self.организация()
		добавить_в_организацию(self.ученик, организация)
		self.назначить(организация, deadline="2020-01-01")

		self.assertTrue(self.мой_курс()["overdue"])

	# --- 2. две организации ---

	def test_из_двух_политик_берётся_строжайшая(self):
		мягкая = self.организация(pass_threshold=0.6, max_attempts=5, retry_delay_hours=1)
		строгая = self.организация(pass_threshold=0.95, max_attempts=2, retry_delay_hours=24)
		добавить_в_организацию(self.ученик, мягкая)
		добавить_в_организацию(self.ученик, строгая)
		self.назначить(мягкая)
		self.назначить(строгая)

		политика = политика_квиза_для_курса(self.ученик, self.курс)

		self.assertEqual(политика["pass_threshold"], 0.95)
		self.assertEqual(политика["max_attempts"], 2)
		self.assertEqual(политика["retry_delay_hours"], 24)

	def test_ближайший_дедлайн_из_двух_назначений(self):
		первая = self.организация()
		вторая = self.организация()
		добавить_в_организацию(self.ученик, первая)
		добавить_в_организацию(self.ученик, вторая)
		self.назначить(первая, deadline="2026-12-31")
		self.назначить(вторая, deadline="2026-06-30")

		self.assertEqual(str(self.мой_курс()["deadline"]), "2026-06-30")

	# --- 3. приостановка ---

	def test_курс_приостановленной_организации_скрывается(self):
		организация = self.организация()
		добавить_в_организацию(self.ученик, организация)
		self.назначить(организация)
		frappe.db.set_value("Learning Organization", организация, "status", "Suspended")

		self.assertIsNone(self.мой_курс())

		можно, причина = доступен_курс(self.ученик, self.курс)
		self.assertFalse(можно)
		self.assertEqual(причина, ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА)

	def test_доступ_возвращается_вместе_со_статусом_организации(self):
		"""Зачисление переживает приостановку — иначе потеряется прогресс.

		Прежняя редакция проверяла только наличие записи, которую ни одна
		ветка кода и не трогает: такой assert не мог покраснеть.
		"""
		организация = self.организация()
		добавить_в_организацию(self.ученик, организация)
		self.назначить(организация)

		frappe.db.set_value("Learning Organization", организация, "status", "Suspended")
		self.assertIsNone(self.мой_курс(), "курс приостановленной организации виден")

		frappe.db.set_value("Learning Organization", организация, "status", "Active")
		self.assertIsNotNone(self.мой_курс(), "доступ не вернулся после возобновления")

	def test_действующее_назначение_перекрывает_приостановленное(self):
		приостановленная = self.организация()
		действующая = self.организация()
		добавить_в_организацию(self.ученик, приостановленная)
		добавить_в_организацию(self.ученик, действующая)
		self.назначить(приостановленная)
		self.назначить(действующая, deadline="2026-12-31")
		frappe.db.set_value("Learning Organization", приостановленная, "status", "Suspended")

		курс = self.мой_курс()

		self.assertIsNotNone(курс)
		self.assertEqual(курс["organization"], действующая)

	def test_приостановленная_организация_не_влияет_на_политику(self):
		строгая_но_приостановленная = self.организация(pass_threshold=0.99, max_attempts=1)
		добавить_в_организацию(self.ученик, строгая_но_приостановленная)
		self.назначить(строгая_но_приостановленная)
		frappe.db.set_value(
			"Learning Organization", строгая_но_приостановленная, "status", "Suspended"
		)

		политика = политика_квиза_для_курса(self.ученик, self.курс)

		self.assertEqual(политика["pass_threshold"], 0.8)

	# --- отказы ---

	def test_незачисленный_ученик_получает_внятный_код(self):
		можно, причина = доступен_курс(self.ученик, self.курс)
		self.assertFalse(можно)
		self.assertEqual(причина, НЕ_ЗАЧИСЛЕН)
