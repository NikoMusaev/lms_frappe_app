# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt

"""Карта декомпозиции: проверка записи и сверка с курсом на платформе.

`Why:` карта — замысел курса, и расходиться с собранным она начинает сразу:
агент переписал цели урока, переставил уроки, завёл блок документа другим
уроком. Сверку делал скрипт по файлам, а на платформе её не видел никто
(lms-high-time/learning-services#264).

Уровни и обязательность проверок приходят в данных: код не знает ни одного
названия столбца, и тесты держат это — флаг уровня включает проверку, его
отсутствие выключает.
"""

import copy

from frappe.tests import UnitTestCase

from lms_frappe_app.agent_learning.course_map import НЕВЕРНАЯ_КАРТА, нормализовать, сверить
from lms_frappe_app.agent_learning.errors import Отказ

УРОВНИ = [
	{"key": "result", "title": "Результат"},
	{"key": "condition", "title": "Условия", "needs_children": True},
	{"key": "skill", "title": "Умения", "needs_children": True},
	{"key": "thesis", "title": "Тезисы", "needs_lesson": True},
]
УЗЛЫ = [
	{"id": "R", "level": "result", "text": "Живой реестр рисков"},
	{"id": "C1", "level": "condition", "text": "Риск записан событием", "parents": ["R"]},
	{"id": "S1", "level": "skill", "text": "Записать риск формулой", "parents": ["C1"]},
	{
		"id": "T1",
		"level": "thesis",
		"text": "Риск это событие",
		"parents": ["S1"],
		"lesson": "u1",
		"objective": True,
		"note": "Hillson: …",
	},
	{
		"id": "T2",
		"level": "thesis",
		"text": "Последствие не риск",
		"parents": ["S1"],
		"lesson": "u1",
		"objective": True,
		"tags": ["ours"],
	},
	{"id": "T3", "level": "thesis", "text": "Цель проекта", "parents": ["S1"], "lesson": "u2", "objective": True},
	{"id": "T4", "level": "thesis", "text": "Справка о шкалах", "parents": ["S1"], "lesson": "u2"},
]
ПЛАН = [
	{"key": "u1", "title": "Риск как событие", "chapter": "Рамка"},
	{"key": "u2", "title": "Цели и источники", "chapter": "Рамка"},
]
БЛОКИ = [
	{"artifact": "register", "key": "risks", "lesson": "u1", "criteria": ["пять-десять записей"]},
]

УРОКИ_ПЛАТФОРМЫ = [
	{"id": "L-1", "title": "Риск как событие", "chapter": "Рамка", "objectives": ["Риск это событие", "Последствие не риск"]},
	{"id": "L-2", "title": "Цели и источники", "chapter": "Рамка", "objectives": ["Цель проекта"]},
]
БЛОКИ_ПЛАТФОРМЫ = [
	{
		"artifact": "register",
		"key": "risks",
		"title": "Риски",
		"lesson": "L-1",
		"hint": "Таблица рисков.  Готов, когда  Пять-десять  записей и у каждой причина.",
	},
]


def карта(levels=None, nodes=None, lessons=None, blocks=None) -> dict:
	return нормализовать(
		copy.deepcopy(УРОВНИ if levels is None else levels),
		copy.deepcopy(УЗЛЫ if nodes is None else nodes),
		copy.deepcopy(ПЛАН if lessons is None else lessons),
		copy.deepcopy(БЛОКИ if blocks is None else blocks),
	)


def с_правкой(список_: list[dict], ключ: str, значение: str, **правки) -> list[dict]:
	"""Копия списка, где у элемента с `ключ == значение` заменены поля."""
	return [{**элемент, **правки} if элемент.get(ключ) == значение else dict(элемент) for элемент in список_]


class TestCourseMapValidation(UnitTestCase):
	"""Запись карты: что платформа отклоняет и к какому виду приводит."""

	def отказ(self, **части) -> Отказ:
		with self.assertRaises(Отказ) as пойманный:
			карта(**части)
		self.assertEqual(пойманный.exception.код, НЕВЕРНАЯ_КАРТА)
		return пойманный.exception

	def test_карта_приводится_к_одному_виду(self):
		к = карта()

		корень = к["nodes"][0]
		self.assertEqual(
			корень,
			{
				"id": "R",
				"level": "result",
				"text": "Живой реестр рисков",
				"parents": [],
				"note": "",
				"tags": [],
				"lesson": None,
				"objective": False,
			},
		)
		self.assertEqual(к["levels"][0], {"key": "result", "title": "Результат", "needs_children": False, "needs_lesson": False})
		self.assertEqual(к["lessons"][0], {"key": "u1", "title": "Риск как событие", "chapter": "Рамка", "lesson": None})
		self.assertEqual(
			к["blocks"][0],
			{"artifact": "register", "key": "risks", "title": "", "lesson": "u1", "criteria": ["пять-десять записей"]},
		)

	def test_ключи_числами_принимаются_строками(self):
		"""Уроки в картах привычно нумеруют числами; сравнивать их со строкой
		агент не обязан помнить."""
		к = карта(
			nodes=с_правкой(с_правкой(УЗЛЫ, "id", "T3", lesson=2), "id", "T4", lesson=2),
			lessons=с_правкой(ПЛАН, "key", "u2", key=2),
			blocks=[],
		)

		self.assertEqual(к["lessons"][1]["key"], "2")
		self.assertEqual(next(у for у in к["nodes"] if у["id"] == "T3")["lesson"], "2")

	def test_ключ_блока_сравнивается_как_в_схеме_документа(self):
		к = карта(blocks=[{"artifact": " Register ", "key": "RISKS", "lesson": "u1"}])

		self.assertEqual((к["blocks"][0]["artifact"], к["blocks"][0]["key"]), ("register", "risks"))

	def test_неверные_карты_отклоняются_с_указанием_места(self):
		случаи = {
			"нет уровней": ({"levels": []}, "levels"),
			"повтор уровня": ({"levels": УРОВНИ + [{"key": "thesis", "title": "Ещё"}]}, "levels[thesis]"),
			"флаг у последнего уровня": (
				{"levels": с_правкой(УРОВНИ, "key", "thesis", needs_children=True)},
				"levels[thesis].needs_children",
			),
			"неизвестное поле уровня": (
				{"levels": с_правкой(УРОВНИ, "key", "skill", need_children=True)},
				"levels[skill].need_children",
			),
			"неизвестный уровень узла": ({"nodes": с_правкой(УЗЛЫ, "id", "S1", level="decision")}, "nodes[S1].level"),
			"повтор узла": ({"nodes": УЗЛЫ + [{"id": "T1", "level": "thesis", "text": "Ещё"}]}, "nodes[T1]"),
			"пустой текст": ({"nodes": с_правкой(УЗЛЫ, "id", "T2", text="  ")}, "nodes[T2].text"),
			"несуществующий родитель": ({"nodes": с_правкой(УЗЛЫ, "id", "T1", parents=["S9"])}, "nodes[T1].parents"),
			"родитель не с соседнего уровня": (
				{"nodes": с_правкой(УЗЛЫ, "id", "T1", parents=["C1"])},
				"nodes[T1].parents",
			),
			"родитель у корня": ({"nodes": с_правкой(УЗЛЫ, "id", "R", parents=["C1"])}, "nodes[R].parents"),
			"урок не из плана": ({"nodes": с_правкой(УЗЛЫ, "id", "T3", lesson="u9")}, "nodes[T3].lesson"),
			"повтор пункта плана": ({"lessons": ПЛАН + [{"key": "u1", "title": "Ещё"}]}, "lessons[u1]"),
			"два пункта на один урок": (
				{"lessons": [{**ПЛАН[0], "lesson": "L-1"}, {**ПЛАН[1], "lesson": "L-1"}]},
				"lessons[u2].lesson",
			),
			"повтор блока": ({"blocks": БЛОКИ + [{"artifact": "register", "key": "RISKS"}]}, "blocks[register/risks]"),
			"блок без ключа": ({"blocks": [{"artifact": "register", "key": " "}]}, "blocks[0].key"),
			"урок блока не из плана": ({"blocks": с_правкой(БЛОКИ, "key", "risks", lesson="u9")}, "blocks[register/risks].lesson"),
			"критерии не списком": (
				{"blocks": с_правкой(БЛОКИ, "key", "risks", criteria="пять записей")},
				"blocks[register/risks].criteria",
			),
		}
		for имя, (части, место) in случаи.items():
			with self.subTest(имя):
				self.assertEqual(self.отказ(**части).подробности.get("where"), место)


class TestCourseMapCheck(UnitTestCase):
	"""Сверка карты с курсом: каждая группа расхождений отдельно."""

	def сверка(self, к=None, уроки=None, блоки=None) -> dict:
		return сверить(
			к or карта(),
			copy.deepcopy(УРОКИ_ПЛАТФОРМЫ if уроки is None else уроки),
			copy.deepcopy(БЛОКИ_ПЛАТФОРМЫ if блоки is None else блоки),
		)

	def группа(self, итог: dict, группа: str) -> list[dict]:
		return [р for р in итог["discrepancies"] if р["group"] == группа]

	def test_согласованный_курс_расхождений_не_даёт(self):
		итог = self.сверка()

		self.assertEqual(итог["discrepancies"], [])
		self.assertEqual(итог["counts"], {"objectives": 0, "lessons": 0, "blocks": 0, "integrity": 0, "total": 0})
		self.assertEqual(итог["matches"], {"u1": "L-1", "u2": "L-2"})
		self.assertEqual(итог["tags"], {"ours": ["T2"]})

	# --- уроки ---

	def test_урок_плана_без_урока_платформы_и_наоборот(self):
		уроки = [УРОКИ_ПЛАТФОРМЫ[0], {"id": "L-9", "title": "Лишний", "chapter": "Рамка", "objectives": []}]

		итог = self.сверка(уроки=уроки)

		self.assertEqual(
			[(р["code"], р.get("plan_lesson"), р.get("lesson")) for р in self.группа(итог, "lessons")],
			[("missing", "u2", None), ("extra", None, "L-9")],
		)
		self.assertIsNone(итог["matches"]["u2"])

	def test_привязанный_урок_переименован_и_перенесён_в_другую_главу(self):
		к = карта(lessons=[{**ПЛАН[0], "lesson": "L-1"}, ПЛАН[1]])
		уроки = с_правкой(УРОКИ_ПЛАТФОРМЫ, "id", "L-1", title="Риск — это событие", chapter="Основы")

		итог = self.сверка(к, уроки=уроки)

		self.assertEqual(
			[(р["code"], р["expected"], р["actual"]) for р in self.группа(итог, "lessons")],
			[("title", "Риск как событие", "Риск — это событие"), ("chapter", "Рамка", "Основы")],
		)
		self.assertEqual(итог["matches"]["u1"], "L-1")

	def test_без_привязки_урок_ищется_по_названию(self):
		уроки = с_правкой(УРОКИ_ПЛАТФОРМЫ, "id", "L-1", title="Риск — это событие")

		итог = self.сверка(уроки=уроки)

		self.assertEqual(
			[(р["code"], р.get("plan_lesson"), р.get("lesson")) for р in self.группа(итог, "lessons")],
			[("missing", "u1", None), ("extra", None, "L-1")],
		)

	def test_переставленный_урок_помечается_один(self):
		"""Помечается урок, который сдвинули, а не все, что сдвинулись из-за него."""
		план = [{"key": f"u{н}", "title": f"Урок {н}", "chapter": "Рамка"} for н in range(1, 5)]
		узлы = [у for у in УЗЛЫ if у["level"] != "thesis"]
		уроки = [
			{"id": f"L-{н}", "title": f"Урок {н}", "chapter": "Рамка", "objectives": []}
			for н in (1, 4, 2, 3)
		]

		итог = self.сверка(карта(nodes=узлы, lessons=план, blocks=[]), уроки=уроки)

		self.assertEqual(
			[(р["code"], р["plan_lesson"]) for р in self.группа(итог, "lessons")],
			[("order", "u4")],
		)

	# --- цели урока ---

	def test_цели_урока_расходятся_с_узлами_целями(self):
		уроки = с_правкой(УРОКИ_ПЛАТФОРМЫ, "id", "L-1", objectives=["Риск это событие", "Новая цель"])

		итог = self.сверка(уроки=уроки)

		(расхождение,) = self.группа(итог, "objectives")
		self.assertEqual(расхождение["code"], "mismatch")
		self.assertEqual((расхождение["plan_lesson"], расхождение["lesson"]), ("u1", "L-1"))
		self.assertEqual(расхождение["missing"], ["Последствие не риск"])
		self.assertEqual(расхождение["extra"], ["Новая цель"])
		self.assertEqual(расхождение["nodes"], ["T2"])

	def test_цели_в_другом_порядке(self):
		уроки = с_правкой(УРОКИ_ПЛАТФОРМЫ, "id", "L-1", objectives=["Последствие не риск", "Риск это событие"])

		итог = self.сверка(уроки=уроки)

		self.assertEqual([р["code"] for р in self.группа(итог, "objectives")], ["order"])

	def test_справочный_тезис_целью_не_считается(self):
		"""T4 привязан к уроку, но не цель: в objectives его быть не должно."""
		уроки = с_правкой(УРОКИ_ПЛАТФОРМЫ, "id", "L-2", objectives=["Цель проекта", "Справка о шкалах"])

		итог = self.сверка(уроки=уроки)

		(расхождение,) = self.группа(итог, "objectives")
		self.assertEqual(расхождение["extra"], ["Справка о шкалах"])

	def test_урок_без_директивы_теряет_все_цели(self):
		уроки = с_правкой(УРОКИ_ПЛАТФОРМЫ, "id", "L-2", objectives=[])

		итог = self.сверка(уроки=уроки)

		(расхождение,) = self.группа(итог, "objectives")
		self.assertEqual(расхождение["missing"], ["Цель проекта"])

	# --- блоки документа ---

	def test_блок_плана_не_заведён_в_схеме_а_в_схеме_лишний(self):
		блоки = [{**БЛОКИ_ПЛАТФОРМЫ[0], "key": "goals"}]

		итог = self.сверка(блоки=блоки)

		self.assertEqual(
			[(р["code"], р["key"]) for р in self.группа(итог, "blocks")],
			[("missing", "risks"), ("extra", "goals")],
		)

	def test_блок_собирается_другим_уроком(self):
		блоки = [{**БЛОКИ_ПЛАТФОРМЫ[0], "lesson": "L-2"}]

		итог = self.сверка(блоки=блоки)

		(расхождение,) = self.группа(итог, "blocks")
		self.assertEqual((расхождение["code"], расхождение["expected"], расхождение["actual"]), ("lesson", "L-1", "L-2"))

	def test_критерий_не_дошёл_до_подсказки(self):
		к = карта(blocks=с_правкой(БЛОКИ, "key", "risks", criteria=["пять-десять записей", "у каждой владелец"]))

		итог = self.сверка(к)

		(расхождение,) = self.группа(итог, "blocks")
		self.assertEqual((расхождение["code"], расхождение["missing"]), ("criteria", ["у каждой владелец"]))

	# --- целостность карты ---

	def test_узел_без_пути_к_результату(self):
		узлы = УЗЛЫ + [
			{"id": "S2", "level": "skill", "text": "Умение без условия", "parents": []},
			{"id": "T5", "level": "thesis", "text": "Тезис под ним", "parents": ["S2"], "lesson": "u2"},
		]

		итог = self.сверка(карта(nodes=узлы))

		сироты = [р["node"] for р in self.группа(итог, "integrity") if р["code"] == "orphan"]
		self.assertEqual(сироты, ["S2", "T5"])

	def test_не_развёрнутый_узел_и_флаг_из_данных(self):
		узлы = УЗЛЫ + [{"id": "C2", "level": "condition", "text": "Реестр пересматривается", "parents": ["R"]}]

		с_флагом = self.сверка(карта(nodes=узлы))
		без_флага = self.сверка(карта(levels=с_правкой(УРОВНИ, "key", "condition", needs_children=False), nodes=узлы))

		self.assertEqual(
			[(р["code"], р["node"]) for р in self.группа(с_флагом, "integrity")], [("unexpanded", "C2")]
		)
		self.assertEqual(self.группа(без_флага, "integrity"), [])

	def test_нужен_урок_а_урока_нет(self):
		узлы = УЗЛЫ + [{"id": "T5", "level": "thesis", "text": "Урока пока нет", "parents": ["S1"]}]

		итог = self.сверка(карта(nodes=узлы))

		self.assertEqual(
			[(р["code"], р["node"]) for р in self.группа(итог, "integrity")], [("no_lesson", "T5")]
		)

	def test_счётчики_по_группам(self):
		уроки = с_правкой(УРОКИ_ПЛАТФОРМЫ, "id", "L-1", objectives=["Риск это событие"])
		узлы = УЗЛЫ + [{"id": "T5", "level": "thesis", "text": "Урока пока нет", "parents": ["S1"]}]

		итог = self.сверка(карта(nodes=узлы), уроки=уроки)

		self.assertEqual(итог["counts"], {"objectives": 1, "lessons": 0, "blocks": 0, "integrity": 1, "total": 2})
		self.assertTrue(all(р["message"] for р in итог["discrepancies"]))
