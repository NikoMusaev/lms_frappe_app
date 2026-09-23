# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Снимки мест курса — «как было» для разницы в кабинете автора.

Снимок — текст места в форме, удобной для сравнения, и режим разбиения:
`{"text", "mode"}`, где режим — абзацы или строки (`agent_learning.diffs`).
У урока — снимки всех его мест: `{"places": {адрес: снимок}}`, в порядке, в
каком их показывает кабинет.

Кабинет запоминает снимок, когда ставят замечание, и сравнивает его с
нынешним, когда агент отметил «сделано» (lms-high-time/learning-services#271).
`Why:` снимок показывает ровно то, что видел человек, — не важно, каким путём
агент записал правку и попала ли она в историю платформы.
"""

import json

import frappe

from lms_frappe_app.agent_learning import course_builder, directives, quiz
from lms_frappe_app.agent_learning.diffs import РЕЖИМ_СТРОКИ, РЕЖИМ_ТЕКСТ

#: Поля директив в порядке, в каком их показывает кабинет.
ПОЛЯ_УРОКА = ("teaching_directive", "objectives", "probing_questions", "success_criteria", "common_misconceptions")
ПОЛЯ_КУРСА = ("teaching_directive", "objectives", "student_profile", "glossary", "remember_about_student")
#: Поля, которые пишут связным текстом; прочие — по строке на пункт.
ТЕКСТОМ = frozenset({"teaching_directive", "student_profile"})
#: Места внутри урока: без урока снимка нет.
С_УРОКОМ = frozenset({"lesson", "material", "directive", "question"})
#: У курса целиком снимка нет: разница курса — это его структура, а она за
#: рамками (lms-high-time/learning-services#271).
БЕЗ_СНИМКА = frozenset({"course"})


def бывает_снимок(target: str) -> bool:
	return target.partition(".")[0] not in БЕЗ_СНИМКА


def снимок(course: str, lesson: str | None, target: str) -> dict | None:
	"""Снимок места замечания; `None` — у места снимка не бывает (курс
	целиком) или места больше нет: урок удалён, вопрос убран, блока нет в
	схеме, узла — в карте."""
	вид, _, ключ = target.partition(".")
	if вид in С_УРОКОМ and not (lesson and frappe.db.exists("Course Lesson", lesson)):
		return None
	if вид == "lesson":
		return {"places": места_урока(course, lesson)}
	if вид == "material":
		return _место(frappe.db.get_value("Course Lesson", lesson, "body"), РЕЖИМ_ТЕКСТ)
	if вид == "directive":
		return _поле("Agent Lesson Directive", {"lesson": lesson}, ключ)
	if вид == "course_directive":
		return _поле("Agent Course Directive", {"course": course}, ключ)
	if вид == "question":
		return _вопрос(ключ) if ключ in quiz.вопросы_урока(lesson) else None
	if вид == "block":
		return _блок(course, ключ)
	if вид == "map":
		return _узел(course, ключ)
	return None


def места_урока(course: str, lesson: str) -> dict[str, dict]:
	"""Снимки мест урока: материал, заполненные поля директивы, вопросы
	квиза, блоки документа, которые урок собирает."""
	места = {"material": _место(frappe.db.get_value("Course Lesson", lesson, "body"), РЕЖИМ_ТЕКСТ)}
	директива = directives.запись("Agent Lesson Directive", {"lesson": lesson}, ПОЛЯ_УРОКА)
	for поле in ПОЛЯ_УРОКА:
		if директива and (директива.get(поле) or "").strip():
			места[f"directive.{поле}"] = _место(директива.get(поле), _режим_поля(поле))
	квиз = quiz._квиз_урока(lesson)
	for вопрос in frappe.get_all("LMS Quiz Question", filters={"parent": квиз}, pluck="question", order_by="idx asc") if квиз else []:
		места[f"question.{вопрос}"] = _вопрос(вопрос)
	for документ, блок in _блоки_курса(course):
		if блок.lesson == lesson:
			места[f"block.{документ}/{блок.block_key}"] = _место_блока(блок)
	return места


def в_json(снимок_места: dict | None) -> str | None:
	return json.dumps(снимок_места, ensure_ascii=False) if снимок_места is not None else None


def из_json(текст: str | None) -> dict | None:
	return json.loads(текст) if текст else None


def _место(текст: str | None, режим: str) -> dict:
	return {"text": текст or "", "mode": режим}


def _режим_поля(поле: str) -> str:
	return РЕЖИМ_ТЕКСТ if поле in ТЕКСТОМ else РЕЖИМ_СТРОКИ


def _поле(doctype: str, владелец: dict, поле: str) -> dict:
	"""Поле действующей директивы; директивы нет — поле пустое, но место
	есть: агент может её завести."""
	запись = directives.запись(doctype, владелец, (поле,))
	return _место(запись.get(поле) if запись else "", _режим_поля(поле))


def _вопрос(вопрос: str) -> dict:
	"""Вопрос строками: текст, варианты («✓» — верный, «·» — нет) с
	пояснениями, образцы ответа."""
	документ = frappe.get_doc("LMS Question", вопрос)
	строки = [документ.question or ""]
	for номер, текст in course_builder.заполненные(документ, "option"):
		знак = "✓" if документ.get(f"is_correct_{номер}") else "·"
		пояснение = документ.get(f"explanation_{номер}") or ""
		строки.append(f"{знак} {текст}" + (f" — {пояснение}" if пояснение else ""))
	строки += [f"Образец: {эталон}" for _, эталон in course_builder.заполненные(документ, "possibility")]
	return _место("\n".join(строки), РЕЖИМ_СТРОКИ)


def _блоки_курса(course: str) -> list[tuple[str, frappe._dict]]:
	"""Блоки действующих схем документов курса — парами «документ, блок»."""
	блоки = []
	for документ in frappe.get_all(
		"Agent Course Artifact", filters={"course": course, "is_active": 1}, fields=["name", "slug"], order_by="creation asc"
	):
		for блок in frappe.get_all(
			"Agent Artifact Block",
			filters={"parent": документ.name},
			fields=["block_key", "title", "hint", "lesson"],
			order_by="idx asc",
		):
			блоки.append((документ.slug, блок))
	return блоки


def _место_блока(блок) -> dict:
	return _место("\n\n".join(часть for часть in (блок.title, блок.hint) if (часть or "").strip()), РЕЖИМ_ТЕКСТ)


def _блок(course: str, ключ: str) -> dict | None:
	документ, _, блок = ключ.partition("/")
	for slug, запись in _блоки_курса(course):
		if slug == документ and запись.block_key == блок:
			return _место_блока(запись)
	return None


def _узел(course: str, ключ: str) -> dict | None:
	карта = directives.запись("Agent Course Map", {"course": course}, ("nodes",))
	for узел in json.loads(карта.nodes or "[]") if карта else []:
		if узел.get("id") == ключ:
			return _место("\n".join(часть for часть in (узел.get("text"), узел.get("note")) if часть), РЕЖИМ_СТРОКИ)
	return None
