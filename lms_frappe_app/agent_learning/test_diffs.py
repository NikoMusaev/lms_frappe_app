# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Разница «было → стало» для кабинета автора.

`Why:` автор проверяет «сделано» и правки агента по разнице, а не
перечитывая раздел (lms-high-time/learning-services#271). Правка должна быть
видна точно — какие слова ушли, какие пришли, — а неизменённое не должно
заслонять её.
"""

from frappe.tests import UnitTestCase

from lms_frappe_app.agent_learning.diffs import РЕЖИМ_СТРОКИ, разница, сравнить


def было_стало(блок: dict) -> tuple[str, str]:
	"""Абзац до и после правки, собранный из частей изменённого блока."""
	было = "".join(текст for знак, текст in блок["parts"] if знак in "=-")
	стало = "".join(текст for знак, текст in блок["parts"] if знак in "=+")
	return было, стало


class TestDiffs(UnitTestCase):
	def test_одинаковые_тексты(self):
		self.assertEqual(разница("Первый.\n\nВторой.", "Первый.\n\nВторой."), {"state": "same"})

	def test_пробелы_по_краям_не_правка(self):
		self.assertEqual(разница("Первый.\n\n\nВторой.  \n", "Первый.\n\nВторой."), {"state": "same"})

	def test_правка_слов_внутри_абзаца(self):
		было = "Спроси, какой риск выше порога, и попроси назвать меру."
		стало = "Спроси, какой риск выше порога, и попроси назвать меру с датой."

		р = разница(было, стало)

		self.assertEqual(р["state"], "changed")
		self.assertFalse(р["rewritten"])
		(блок,) = р["blocks"]
		self.assertEqual(блок["kind"], "changed")
		self.assertEqual(было_стало(блок), (было, стало))
		удалено = "".join(текст for знак, текст in блок["parts"] if знак == "-")
		self.assertNotIn("Спроси", удалено)
		self.assertIn("датой", "".join(текст for знак, текст in блок["parts"] if знак == "+"))

	def test_новый_и_удалённый_абзацы(self):
		р = разница("Один.\n\nДва.\n\nТри.", "Один.\n\nНовый абзац.\n\nДва.")

		виды = [(б["kind"], б.get("text")) for б in р["blocks"]]
		self.assertEqual(виды, [("same", "Один."), ("added", "Новый абзац."), ("same", "Два."), ("removed", "Три.")])

	def test_неизменённое_сворачивается_вокруг_правки(self):
		абзацы = ["А.", "Б.", "В.", "Г.", "Д.", "Е."]
		стало = [*абзацы[:4], "Д — новый.", "Е."]

		р = разница("\n\n".join(абзацы), "\n\n".join(стало))

		виды = [б["kind"] for б in р["blocks"]]
		self.assertEqual(виды, ["gap", "same", "changed", "same"])
		self.assertEqual(р["blocks"][0]["texts"], ["А.", "Б.", "В."])
		self.assertEqual(р["blocks"][1]["text"], "Г.")

	def test_непохожий_абзац_не_размазывается_по_словам(self):
		р = разница("Один.\n\nСовсем другой смысл был тут.", "Один.\n\nНичего общего с прежним.")

		виды = [б["kind"] for б in р["blocks"]]
		self.assertEqual(виды, ["same", "removed", "added"])

	def test_переписан_почти_целиком(self):
		р = разница(
			"Риск это событие.\n\nУ него есть причина и последствие.",
			"Сегодня про деньги.\n\nБюджет считается по статьям.\n\nРезерв — отдельно.",
		)

		self.assertEqual(р["state"], "changed")
		self.assertTrue(р["rewritten"])

	def test_из_пустого_всё_новое_но_не_переписано(self):
		р = разница("", "Первый абзац.")

		self.assertFalse(р["rewritten"])
		self.assertEqual([б["kind"] for б in р["blocks"]], ["added"])

	def test_таблица_и_список_в_тексте_сравниваются_по_строкам(self):
		"""Таблица или список — один абзац без пустых строк; правка одной
		строки не должна показывать их целиком."""
		таблица = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n| 7 | 8 |"

		р = разница("Текст.\n\n" + таблица, "Текст.\n\n" + таблица.replace("| 7 | 8 |", "| 7 | 9 |"))

		self.assertEqual([б["kind"] for б in р["blocks"]], ["gap", "same", "changed"])
		self.assertEqual(было_стало(р["blocks"][-1]), ("| 7 | 8 |", "| 7 | 9 |"))
		список = разница("- один\n- два\n- три", "- один\n- два с правкой\n- три")
		self.assertEqual([б["kind"] for б in список["blocks"]], ["same", "changed", "same"])

	def test_список_по_пунктам(self):
		р = разница("Цель один\nЦель два", "Цель один\nЦель два с уточнением\nЦель три", РЕЖИМ_СТРОКИ)

		виды = [б["kind"] for б in р["blocks"]]
		self.assertEqual(виды, ["same", "changed", "added"])
		self.assertEqual(было_стало(р["blocks"][1]), ("Цель два", "Цель два с уточнением"))


class TestCompareSnapshots(UnitTestCase):
	"""Сравнение снимков мест: разница текста, а у урока — по местам."""

	def test_без_снимка_разница_недоступна(self):
		self.assertEqual(сравнить(None, {"text": "а", "mode": "text"}), {"state": "unavailable"})

	def test_места_больше_нет(self):
		self.assertEqual(сравнить({"text": "а", "mode": "text"}, None), {"state": "missing"})

	def test_текст_места(self):
		self.assertEqual(сравнить({"text": "а", "mode": "text"}, {"text": "а", "mode": "text"}), {"state": "same"})
		р = сравнить({"text": "Один", "mode": "lines"}, {"text": "Один\nДва", "mode": "lines"})
		self.assertEqual([б["kind"] for б in р["blocks"]], ["same", "added"])

	def test_урок_по_местам(self):
		было = {"places": {"material": {"text": "А.", "mode": "text"}, "question.Q1": {"text": "В?", "mode": "lines"}}}
		стало = {"places": {"material": {"text": "А.", "mode": "text"}, "directive.objectives": {"text": "Цель", "mode": "lines"}}}

		р = сравнить(было, стало)

		self.assertEqual(р["state"], "changed")
		self.assertEqual(
			[(м["target"], [б["kind"] for б in м["blocks"]]) for м in р["places"]],
			[("directive.objectives", ["added"]), ("question.Q1", ["removed"])],
		)

	def test_урок_без_изменений(self):
		снимок_урока = {"places": {"material": {"text": "А.", "mode": "text"}}}
		self.assertEqual(сравнить(снимок_урока, снимок_урока), {"state": "same"})
