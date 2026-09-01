# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from lms_agent.agent_learning.access import НЕ_ЗАЧИСЛЕН, ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА
from lms_agent.agent_learning.quiz import (
	ВОПРОС_БЕЗ_ЭТАЛОНА,
	КВИЗА_НЕТ,
	ПОПЫТКА_ЗАВЕРШЕНА,
	ПОПЫТКИ_ИСЧЕРПАНЫ,
	СЛИШКОМ_РАНО,
	НЕЧЕГО_ПРОВЕРЯТЬ,
	ЧУЖОЙ_ВОПРОС,
	начать_попытку,
	принять_ответ,
)
from lms_agent.agent_learning.errors import Отказ
from lms_agent.agent_learning.sample_data import (
	добавить_в_организацию,
	создать_занятие,
	создать_вопрос,
	создать_занятие,
	создать_квиз,
	создать_организацию,
	создать_ученика,
	создать_урок,
	зачислить,
)

ЭТАЛОННЫЕ_ПОЛЯ = ("is_correct", "possibility", "explanation_")


class IntegrationTestQuiz(IntegrationTestCase):
	"""Серверный квиз: выдача вопросов, сверка, итог, лимиты."""

	def setUp(self):
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"q-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.вопрос_выбор = создать_вопрос(
			"Что выведет цикл?",
			варианты=[("раз", False), ("два", True), ("три", False)],
			пояснение="Потому что счётчик начинается с нуля",
		)
		self.вопрос_ввод = создать_вопрос(
			"Как называется оператор повторения?", возможные_ответы=["цикл", "loop"]
		)
		self.квиз = создать_квиз(self.урок, [self.вопрос_выбор, self.вопрос_ввод])
		# Зачисление обязательно: начать_попытку проверяет доступ к курсу —
		# раньше квиз сдавался и без него.
		зачислить(self.ученик, self.урок)
		self.занятие = создать_занятие(self.ученик, self.урок)

	def начать(self):
		return начать_попытку(self.занятие)

	def пройти_целиком(self, верно_выбор=True, верно_ввод=True):
		начало = self.начать()
		попытка = начало["attempt"]
		принять_ответ(попытка, self.вопрос_выбор, "2" if верно_выбор else "1")
		итог = принять_ответ(попытка, self.вопрос_ввод, "цикл" if верно_ввод else "мимо")
		return попытка, итог

	# --- главное: эталоны не покидают сервер ---

	def test_в_выданном_вопросе_нет_ни_одного_поля_эталона(self):
		"""Несущая проверка всей схемы зачёта.

		Утечка эталона обесценивает серверный квиз целиком, а с ним и
		устойчивость к пересказу директивы агентом.
		"""
		выдано = json.dumps(self.начать(), ensure_ascii=False, default=str)

		for поле in ЭТАЛОННЫЕ_ПОЛЯ:
			self.assertNotIn(поле, выдано)

	def test_варианты_выдаются_без_признака_правильности(self):
		вопрос = self.начать()["question"]
		self.assertEqual([в["id"] for в in вопрос["options"]], ["1", "2", "3"])
		for вариант in вопрос["options"]:
			self.assertEqual(set(вариант), {"id", "text"})

	def test_пояснение_приходит_только_вместе_с_вердиктом(self):
		# До ответа пояснение было бы подсказкой.
		вопрос = self.начать()["question"]
		self.assertNotIn("explanation", json.dumps(вопрос, ensure_ascii=False))

		попытка, _ = self.пройти_целиком()
		# пояснение уже отдано в вердикте первого ответа — проверено ниже

	# --- сверка ---

	def test_верный_выбор_засчитывается_с_пояснением(self):
		попытка = self.начать()["attempt"]
		ответ = принять_ответ(попытка, self.вопрос_выбор, "2")

		self.assertTrue(ответ["verdict"]["correct"])
		self.assertIn("счётчик", ответ["verdict"]["explanation"])
		self.assertIsNotNone(ответ["next_question"])

	def test_неверный_выбор_не_засчитывается(self):
		попытка = self.начать()["attempt"]
		self.assertFalse(принять_ответ(попытка, self.вопрос_выбор, "1")["verdict"]["correct"])

	def test_свободный_ввод_сверяется_без_учёта_регистра_и_пробелов(self):
		попытка = self.начать()["attempt"]
		принять_ответ(попытка, self.вопрос_выбор, "2")
		ответ = принять_ответ(попытка, self.вопрос_ввод, "  ЦИКЛ ")
		self.assertTrue(ответ["verdict"]["correct"])

	def test_множественный_выбор_требует_полного_совпадения(self):
		вопрос = создать_вопрос(
			"Выберите чётные",
			варианты=[("2", True), ("3", False), ("4", True)],
		)
		урок = создать_урок(f"Урок {frappe.generate_hash(length=6)}")
		создать_квиз(урок, [вопрос])
		зачислить(self.ученик, урок)
		попытка = начать_попытку(создать_занятие(self.ученик, урок))["attempt"]

		частично = принять_ответ(попытка, вопрос, "1")
		self.assertFalse(частично["verdict"]["correct"])

	def test_ответ_принимается_и_строкой_и_списком(self):
		# Агенты форматируют по-разному; отказ из-за запятой выглядел бы как
		# неверный ответ.
		# Два отдельных квиза: две попытки подряд на одном упёрлись бы в паузу
		# перед повтором — и это правильное поведение, а не помеха тесту.
		for ответ in ("1,3", ["1", "3"]):
			вопрос = создать_вопрос(
				"Чётные", варианты=[("2", True), ("3", False), ("4", True)]
			)
			урок = создать_урок(f"Урок {frappe.generate_hash(length=6)}")
			создать_квиз(урок, [вопрос])
			зачислить(self.ученик, урок)
			попытка = начать_попытку(создать_занятие(self.ученик, урок))["attempt"]

			self.assertTrue(принять_ответ(попытка, вопрос, ответ)["verdict"]["correct"])

	# --- итог ---

	def test_пройденный_квиз_закрывает_занятие_и_пишет_прогресс(self):
		попытка, итог = self.пройти_целиком()

		self.assertTrue(итог["attempt_finished"])
		self.assertTrue(итог["result"]["passed"])
		self.assertEqual(итог["result"]["session_status"], "Completed")
		self.assertTrue(
			frappe.db.exists(
				"LMS Course Progress",
				{"member": self.ученик, "lesson": self.урок, "status": "Complete"},
			)
		)

	def test_итог_виден_в_стандартной_записи_frappe(self):
		# Оба канала обязаны сходиться в одной записи: ученик занимается с
		# агентом, а результат видит в браузере.
		попытка, _ = self.пройти_целиком()
		submission = frappe.db.get_value("Agent Quiz Attempt", попытка, "submission")

		self.assertTrue(submission)
		запись = frappe.get_doc("LMS Quiz Submission", submission)
		self.assertEqual(запись.member, self.ученик)
		self.assertEqual(запись.score, 2)
		self.assertEqual(запись.score_out_of, 2)
		self.assertEqual(len(запись.result), 2)

	def test_проваленный_квиз_не_закрывает_занятие(self):
		попытка, итог = self.пройти_целиком(верно_выбор=False, верно_ввод=False)

		self.assertFalse(итог["result"]["passed"])
		self.assertNotEqual(итог["result"]["session_status"], "Completed")
		self.assertFalse(
			frappe.db.exists(
				"LMS Course Progress",
				{"member": self.ученик, "lesson": self.урок, "status": "Complete"},
			)
		)

	# --- отказы ---

	def test_повторный_ответ_на_вопрос_отклоняется(self):
		попытка = self.начать()["attempt"]
		принять_ответ(попытка, self.вопрос_выбор, "2")

		with self.assertRaises(Отказ) as отказ:
			принять_ответ(попытка, self.вопрос_выбор, "1")
		self.assertEqual(отказ.exception.код, ЧУЖОЙ_ВОПРОС)

	def test_чужой_вопрос_отклоняется(self):
		# Минимум два варианта: Frappe Learning иначе не сохранит вопрос.
		чужой = создать_вопрос("Не из этого квиза", варианты=[("да", True), ("нет", False)])
		попытка = self.начать()["attempt"]

		with self.assertRaises(Отказ) as отказ:
			принять_ответ(попытка, чужой, "1")
		self.assertEqual(отказ.exception.код, ЧУЖОЙ_ВОПРОС)

	def test_ответ_в_завершённую_попытку_отклоняется(self):
		попытка, _ = self.пройти_целиком()

		with self.assertRaises(Отказ) as отказ:
			принять_ответ(попытка, self.вопрос_выбор, "2")
		self.assertEqual(отказ.exception.код, ПОПЫТКА_ЗАВЕРШЕНА)

	def test_урок_без_квиза_даёт_внятный_код(self):
		урок = создать_урок(f"Без квиза {frappe.generate_hash(length=6)}")
		зачислить(self.ученик, урок)
		занятие = создать_занятие(self.ученик, урок)

		with self.assertRaises(Отказ) as отказ:
			начать_попытку(занятие)
		self.assertEqual(отказ.exception.код, КВИЗА_НЕТ)

	# --- политика организации ---

	def test_исчерпанные_попытки_отклоняются_с_числом(self):
		организация = создать_организацию(
			f"Строгая {frappe.generate_hash(length=6)}", max_attempts=1, retry_delay_hours=0
		)
		добавить_в_организацию(self.ученик, организация)
		frappe.get_doc(
			{
				"doctype": "Course Allocation",
				"organization": организация,
				"course": frappe.db.get_value("LMS Quiz", self.квиз, "course"),
			}
		).insert(ignore_permissions=True)

		self.пройти_целиком(верно_выбор=False, верно_ввод=False)

		with self.assertRaises(Отказ) as отказ:
			начать_попытку(создать_занятие(self.ученик, self.урок))
		self.assertEqual(отказ.exception.код, ПОПЫТКИ_ИСЧЕРПАНЫ)
		self.assertEqual(отказ.exception.подробности["attempts_used"], 1)

	def test_повтор_раньше_паузы_отклоняется_с_временем(self):
		организация = создать_организацию(
			f"С паузой {frappe.generate_hash(length=6)}", max_attempts=5, retry_delay_hours=24
		)
		добавить_в_организацию(self.ученик, организация)
		frappe.get_doc(
			{
				"doctype": "Course Allocation",
				"organization": организация,
				"course": frappe.db.get_value("LMS Quiz", self.квиз, "course"),
			}
		).insert(ignore_permissions=True)

		self.пройти_целиком(верно_выбор=False, верно_ввод=False)

		with self.assertRaises(Отказ) as отказ:
			начать_попытку(создать_занятие(self.ученик, self.урок))
		self.assertEqual(отказ.exception.код, СЛИШКОМ_РАНО)
		self.assertIn("retry_after", отказ.exception.подробности)

	# --- открытые вопросы ---

	def test_квиз_из_открытых_вопросов_даёт_внятный_отказ(self):
		"""Их проверка требует человека, а зачёт от агента — не зачёт.

		Смешать открытые вопросы с проверяемыми Frappe Learning не позволяет:
		«make sure each question in the quiz is of open ended type». Значит
		квиз либо весь открытый, либо проверяемый целиком.
		"""
		открытый = frappe.get_doc(
			{"doctype": "LMS Question", "question": "Расскажите своими словами", "type": "Open Ended"}
		).insert(ignore_permissions=True)
		урок = создать_урок(f"Открытый {frappe.generate_hash(length=6)}")
		создать_квиз(урок, [открытый.name])
		зачислить(self.ученик, урок)

		with self.assertRaises(Отказ) as отказ:
			начать_попытку(создать_занятие(self.ученик, урок))
		self.assertEqual(отказ.exception.код, НЕЧЕГО_ПРОВЕРЯТЬ)


class IntegrationTestQuizIntegrity(IntegrationTestCase):
	"""Целостность зачёта: лимиты, доступ, порог, кривой контент."""

	def setUp(self):
		суффикс = frappe.generate_hash(length=6)
		self.ученик = создать_ученика(f"qi-{суффикс}@example.com")
		self.урок = создать_урок(f"Урок {суффикс}")
		self.курс = frappe.db.get_value(
			"Course Chapter", frappe.db.get_value("Course Lesson", self.урок, "chapter"), "course"
		)
		self.вопрос = создать_вопрос(
			"Столица?", варианты=[("Москва", True), ("Тула", False), ("Клин", False)]
		)
		self.квиз = создать_квиз(self.урок, [self.вопрос])
		зачислить(self.ученик, self.урок)

	def занятие(self):
		return создать_занятие(self.ученик, self.урок)

	def организация_с_политикой(self, **поля):
		организация = создать_организацию(f"Компания {frappe.generate_hash(length=6)}", **поля)
		добавить_в_организацию(self.ученик, организация)
		frappe.get_doc(
			{"doctype": "Course Allocation", "organization": организация, "course": self.курс}
		).insert(ignore_permissions=True)
		return организация

	# --- лимит попыток ---

	def test_брошенная_попытка_расходует_лимит(self):
		"""Иначе ответы перебираются: ответил, увидел вердикт, бросил, начал заново."""
		self.организация_с_политикой(max_attempts=1, retry_delay_hours=1)

		первая = начать_попытку(self.занятие())["attempt"]
		принять_ответ(первая, self.вопрос, "2")  # неверно, попытка остаётся открытой

		with self.assertRaises(Отказ) as отказ:
			начать_попытку(self.занятие())
		self.assertEqual(отказ.exception.код, ПОПЫТКИ_ИСЧЕРПАНЫ)

	def test_повторный_запрос_возвращает_ту_же_попытку(self):
		# Не новую: иначе счётчик попыток растёт от каждого переподключения.
		занятие = self.занятие()
		первая = начать_попытку(занятие)["attempt"]
		вторая = начать_попытку(занятие)["attempt"]
		self.assertEqual(первая, вторая)

	def test_возвращённая_попытка_помнит_отвеченное(self):
		# Квиз из двух вопросов: после одного ответа попытка ещё открыта, и
		# повторное подключение агента обязано продолжить её, а не начать
		# заново с первого вопроса.
		второй = создать_вопрос("Крупнейший город?", варианты=[("Москва", True), ("Клин", False)])
		урок = создать_урок(f"Два вопроса {frappe.generate_hash(length=6)}")
		создать_квиз(урок, [self.вопрос, второй])
		зачислить(self.ученик, урок)
		занятие = создать_занятие(self.ученик, урок)

		попытка = начать_попытку(занятие)["attempt"]
		принять_ответ(попытка, self.вопрос, "1")

		повтор = начать_попытку(занятие)

		self.assertEqual(повтор["attempt"], попытка)
		self.assertEqual(повтор["question"]["id"], второй)

	# --- доступ ---

	def test_квиз_по_курсу_приостановленной_организации_не_начать(self):
		организация = self.организация_с_политикой()
		занятие = self.занятие()
		frappe.db.set_value("Learning Organization", организация, "status", "Suspended")

		with self.assertRaises(Отказ) as отказ:
			начать_попытку(занятие)
		self.assertEqual(отказ.exception.код, ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА)

	def test_квиз_без_зачисления_не_начать(self):
		посторонний = создать_ученика(f"qx-{frappe.generate_hash(length=6)}@example.com")
		занятие = создать_занятие(посторонний, self.урок)

		with self.assertRaises(Отказ) as отказ:
			начать_попытку(занятие)
		self.assertEqual(отказ.exception.код, НЕ_ЗАЧИСЛЕН)

	# --- брошенное занятие ---

	def test_квиз_завершается_даже_если_занятие_закрыли_по_бездействию(self):
		"""Ученик вернулся к последнему вопросу через сутки — результат не теряется."""
		self.организация_с_политикой()
		занятие = self.занятие()
		попытка = начать_попытку(занятие)["attempt"]
		frappe.db.set_value("Agent Learning Session", занятие, "status", "Abandoned")

		итог = принять_ответ(попытка, self.вопрос, "1")

		self.assertTrue(итог["result"]["passed"])
		self.assertTrue(frappe.db.get_value("Agent Quiz Attempt", попытка, "submission"))

	# --- порог ---

	def test_порог_в_стандартной_записи_совпадает_с_политикой(self):
		# Иначе в нашей записи «зачтено», а в браузерной — ниже проходного.
		self.организация_с_политикой(pass_threshold=0.5)
		попытка = начать_попытку(self.занятие())["attempt"]
		принять_ответ(попытка, self.вопрос, "1")

		submission = frappe.db.get_value("Agent Quiz Attempt", попытка, "submission")
		self.assertEqual(
			frappe.db.get_value("LMS Quiz Submission", submission, "passing_percentage"), 50
		)

	# --- кривой контент ---

	def test_вопрос_без_верного_варианта_даёт_ошибку_а_не_балл(self):
		"""Защита от данных, пришедших в обход валидации.

		Сам Frappe Learning вопрос без верного варианта сохранить не даёт, но
		запись может приехать импортом или миграцией. Без проверки пустой
		ответ совпал бы с пустым множеством эталонов и принёс балл.
		"""
		вопрос = создать_вопрос("Кривой", варианты=[("раз", True), ("два", False)])
		урок = создать_урок(f"Кривой {frappe.generate_hash(length=6)}")
		создать_квиз(урок, [вопрос])
		зачислить(self.ученик, урок)
		попытка = начать_попытку(создать_занятие(self.ученик, урок))["attempt"]
		# Портим данные мимо валидации — так же, как это сделал бы импорт.
		frappe.db.set_value("LMS Question", вопрос, "is_correct_1", 0)
		frappe.clear_document_cache("LMS Question", вопрос)

		with self.assertRaises(Отказ) as отказ:
			принять_ответ(попытка, вопрос, "")
		self.assertEqual(отказ.exception.код, ВОПРОС_БЕЗ_ЭТАЛОНА)

	# --- множественный выбор ---

	def test_выбор_всех_вариантов_не_засчитывается(self):
		"""Защита от очевидного чита: сверка требует точного совпадения."""
		вопрос = создать_вопрос(
			"Чётные", варианты=[("2", True), ("3", False), ("4", True)]
		)
		урок = создать_урок(f"Множественный {frappe.generate_hash(length=6)}")
		создать_квиз(урок, [вопрос])
		зачислить(self.ученик, урок)
		попытка = начать_попытку(создать_занятие(self.ученик, урок))["attempt"]

		ответ = принять_ответ(попытка, вопрос, "1,2,3")

		self.assertFalse(ответ["verdict"]["correct"])
