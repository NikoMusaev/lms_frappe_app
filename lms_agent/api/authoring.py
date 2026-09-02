# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Методы сборки курса.

Куратор собирает курс в диалоге со своим агентом. Методы отвечают за хранение
и нормализацию; чем курс хорош — дело агента куратора, не этого файла.

Удаления здесь нет намеренно: снятая с публикации ошибка обратима, удалённый
урок с прогрессом учеников — нет.
"""

import json

import frappe

from lms_agent.agent_learning import course_builder, structure
from lms_agent.agent_learning.errors import Отказ
from lms_agent.api import контракт, текущий_пользователь

#: Роли, которым разрешено собирать курсы. Совпадают с административными в
#: `permissions`: там они уже дают полный доступ к учебным записям.
АВТОРСКИЕ_РОЛИ = frozenset({"Course Creator", "Moderator", "System Manager", "Administrator"})

КУРС_НЕ_НАЙДЕН = "course_not_found"
УРОК_НЕ_НАЙДЕН = "lesson_not_found"
ГЛАВА_НЕ_НАЙДЕНА = "chapter_not_found"
КУРС_НЕ_ГОТОВ = "course_not_ready"
НЕВЕРНЫЙ_ВОПРОС = "invalid_question"


def _автор() -> str:
	"""Пользователь с правом собирать курсы.

	Отдельный эндпоинт `/authoring` не защищает ничего — адрес известен, токен
	у ученика тот же. Единственная настоящая граница здесь.

	`Why:` отказ идёт ошибкой прав, а не кодом контракта: у агента ученика
	нет сценария, в котором он что-то с этим сделает, а 403 однозначен и
	попадает в журнал Frappe как нарушение доступа.
	"""
	пользователь = текущий_пользователь()
	if not set(frappe.get_roles(пользователь)) & АВТОРСКИЕ_РОЛИ:
		frappe.throw(frappe._("Сборка курсов доступна кураторам"), frappe.PermissionError)
	return пользователь


def _список(значение) -> list:
	"""Аргумент, который мог приехать строкой JSON.

	`Why:` Frappe отдаёт тело запроса как форму, и список превращается в
	строку. Без разбора `reorder_lessons` получал бы строку и молча считал
	её посимвольно.
	"""
	if isinstance(значение, str):
		значение = json.loads(значение)
	return list(значение or [])


# --- курс ---


@frappe.whitelist(methods=["POST"])
@контракт
def create_course(title: str, summary: str, description: str | None = None) -> dict:
	"""Заводит черновик курса. Публикуется отдельным вызовом."""
	автор = _автор()
	курс = frappe.get_doc(
		{
			"doctype": "LMS Course",
			"title": title,
			"short_introduction": summary,
			"description": description or summary,
			"published": 0,
			"instructors": [{"instructor": автор}],
		}
	).insert()
	return {"id": курс.name, "title": курс.title, "published": False}


@frappe.whitelist(methods=["POST"])
@контракт
def add_chapter(course: str, title: str) -> dict:
	"""Добавляет главу в конец курса."""
	_автор()
	_должен_существовать("LMS Course", course, КУРС_НЕ_НАЙДЕН)
	глава = frappe.get_doc({"doctype": "Course Chapter", "course": course, "title": title}).insert()
	structure.привязать(course, "LMS Course", глава.name)
	return {"id": глава.name, "title": глава.title, "course": course}


@frappe.whitelist(methods=["POST"])
@контракт
def add_lesson(chapter: str, title: str, body: str) -> dict:
	"""Добавляет урок в конец главы."""
	_автор()
	_должен_существовать("Course Chapter", chapter, ГЛАВА_НЕ_НАЙДЕНА)
	курс = frappe.db.get_value("Course Chapter", chapter, "course")
	урок = frappe.get_doc(
		{"doctype": "Course Lesson", "title": title, "body": body, "chapter": chapter, "course": курс}
	).insert()
	structure.привязать(chapter, "Course Chapter", урок.name)
	return {"id": урок.name, "title": урок.title, "chapter": chapter, "course": курс}


@frappe.whitelist(methods=["POST"])
@контракт
def update_lesson(lesson: str, title: str | None = None, body: str | None = None) -> dict:
	"""Правит название или материал урока."""
	_автор()
	_должен_существовать("Course Lesson", lesson, УРОК_НЕ_НАЙДЕН)
	документ = frappe.get_doc("Course Lesson", lesson)
	if title is not None:
		документ.title = title
	if body is not None:
		документ.body = body
	документ.save()
	return {"id": документ.name, "title": документ.title}


@frappe.whitelist(methods=["POST"])
@контракт
def reorder_lessons(chapter: str, lessons) -> dict:
	"""Задаёт порядок уроков главы полным списком."""
	_автор()
	_должен_существовать("Course Chapter", chapter, ГЛАВА_НЕ_НАЙДЕНА)
	structure.переставить(chapter, "Course Chapter", _список(lessons))
	return {"chapter": chapter, "lessons": _список(lessons)}


@frappe.whitelist(methods=["POST"])
@контракт
def reorder_chapters(course: str, chapters) -> dict:
	"""Задаёт порядок глав курса полным списком."""
	_автор()
	_должен_существовать("LMS Course", course, КУРС_НЕ_НАЙДЕН)
	structure.переставить(course, "LMS Course", _список(chapters))
	return {"course": course, "chapters": _список(chapters)}


# --- директива и квиз ---


@frappe.whitelist(methods=["POST"])
@контракт
def set_directive(
	lesson: str,
	teaching_directive: str,
	objectives: str | None = None,
	probing_questions: str | None = None,
	common_misconceptions: str | None = None,
	success_criteria: str | None = None,
) -> dict:
	"""Задаёт директиву преподавателя новой версией.

	Прошлые версии не удаляются, а снимаются с действия: занятие, идущее
	прямо сейчас, уже получило свою директиву, и стирать её из истории
	значит потерять основание выставленного зачёта.
	"""
	_автор()
	_должен_существовать("Course Lesson", lesson, УРОК_НЕ_НАЙДЕН)

	прошлые = frappe.get_all("Agent Lesson Directive", filters={"lesson": lesson}, fields=["name", "version"])
	for прошлая in прошлые:
		frappe.db.set_value("Agent Lesson Directive", прошлая.name, "is_active", 0)

	версия = max([п.version or 0 for п in прошлые], default=0) + 1
	директива = frappe.get_doc(
		{
			"doctype": "Agent Lesson Directive",
			"lesson": lesson,
			"version": версия,
			"is_active": 1,
			"objectives": objectives,
			"teaching_directive": teaching_directive,
			"probing_questions": probing_questions,
			"common_misconceptions": common_misconceptions,
			"success_criteria": success_criteria,
		}
	).insert()
	return {"id": директива.name, "lesson": lesson, "version": версия}


@frappe.whitelist(methods=["POST"])
@контракт
def add_quiz(lesson: str, questions, title: str | None = None, passing_percentage: int = 70) -> dict:
	"""Создаёт квиз урока со всеми вопросами.

	Квиз заводится целиком одним вызовом: квиз без вопросов — состояние, в
	котором ученик упирается в зачёт из ничего, и оставлять его достижимым
	между двумя вызовами незачем.
	"""
	_автор()
	_должен_существовать("Course Lesson", lesson, УРОК_НЕ_НАЙДЕН)
	вопросы = _список(questions)
	if not вопросы:
		raise Отказ(course_builder.КВИЗ_БЕЗ_ВОПРОСОВ, "Квизу нужен хотя бы один вопрос", lesson=lesson)

	квиз = frappe.get_doc(
		{
			"doctype": "LMS Quiz",
			"title": title or frappe.db.get_value("Course Lesson", lesson, "title"),
			"lesson": lesson,
			"course": frappe.db.get_value("Course Lesson", lesson, "course"),
			"passing_percentage": passing_percentage,
		}
	)
	созданы = []
	# Точка сохранения, а не откат всей транзакции: сбойный вопрос обязан
	# отменить только уже созданные вопросы этого квиза. `frappe.db.rollback()`
	# без неё сносил и курс, и главы, созданные тем же процессом, — поймано
	# на живом прогоне сборки.
	frappe.db.savepoint("agent_quiz_build")
	for номер, вопрос in enumerate(вопросы, start=1):
		try:
			идентификатор, тип = course_builder.создать_вопрос(вопрос)
		except Отказ:
			raise
		except frappe.ValidationError as причина:
			# Проверку состава вариантов делает сам Frappe Learning, и её текст
			# полезен — но агенту нужен машинный код, а не HTTP 500.
			frappe.db.rollback(save_point="agent_quiz_build")
			raise Отказ(НЕВЕРНЫЙ_ВОПРОС, str(причина), lesson=lesson, question_index=номер) from причина
		квиз.append("questions", {"question": идентификатор, "type": тип, "marks": вопрос.get("marks") or 1})
		созданы.append(идентификатор)
	квиз.insert()

	# Привязка с обеих сторон: Frappe Learning допускает обе, а урок,
	# связанный только полем квиза, в интерфейсе выглядит без квиза.
	frappe.db.set_value("Course Lesson", lesson, "quiz_id", квиз.name)
	return {"id": квиз.name, "lesson": lesson, "questions": созданы}


# --- обзор и публикация ---


@frappe.whitelist()
@контракт
def course_draft(course: str) -> dict:
	"""Курс целиком, как его собрали, — с эталонами и проблемами.

	Эталоны видит роль, а не эндпоинт: без них куратор не проверит
	собственный квиз. Ученику они не достаются ни здесь, ни где-либо ещё —
	`_автор` отклонит вызов до всякого чтения.
	"""
	_автор()
	_должен_существовать("LMS Course", course, КУРС_НЕ_НАЙДЕН)
	сведения = frappe.db.get_value(
		"LMS Course", course, ["title", "short_introduction", "published"], as_dict=True
	)
	return {
		"id": course,
		"title": сведения.title,
		"summary": сведения.short_introduction,
		"published": bool(сведения.published),
		"chapters": [
			{"id": глава["name"], "title": глава["title"], "lessons": _уроки_главы(глава["name"])}
			for глава in structure.главы_курса(course)
		],
		"readiness": course_builder.проверить_готовность(course),
	}


@frappe.whitelist(methods=["POST"])
@контракт
def publish_course(course: str) -> dict:
	"""Открывает курс ученикам, если он к этому готов."""
	_автор()
	_должен_существовать("LMS Course", course, КУРС_НЕ_НАЙДЕН)
	готовность = course_builder.проверить_готовность(course)
	if готовность["blocking"]:
		raise Отказ(
			КУРС_НЕ_ГОТОВ,
			"Курс не готов к публикации",
			course=course,
			problems=готовность["blocking"],
		)
	frappe.db.set_value("LMS Course", course, "published", 1)
	return {"id": course, "published": True, "warnings": готовность["warnings"]}


@frappe.whitelist(methods=["POST"])
@контракт
def unpublish_course(course: str) -> dict:
	"""Снимает курс с публикации. Прогресс учеников остаётся."""
	_автор()
	_должен_существовать("LMS Course", course, КУРС_НЕ_НАЙДЕН)
	frappe.db.set_value("LMS Course", course, "published", 0)
	return {"id": course, "published": False}


# --- вспомогательное ---


def _уроки_главы(глава: str) -> list[dict]:
	from lms_agent.agent_learning import quiz

	уроки = structure.уроки_главы(глава)
	собранное = []
	for урок in уроки:
		сведения = frappe.db.get_value("Course Lesson", урок, ["title", "body"], as_dict=True)
		квиз = quiz._квиз_урока(урок)
		собранное.append(
			{
				"id": урок,
				"title": сведения.title,
				"has_body": bool((сведения.body or "").strip()),
				"has_directive": bool(
					frappe.db.exists("Agent Lesson Directive", {"lesson": урок, "is_active": 1})
				),
				"quiz": _вопросы_с_эталонами(квиз) if квиз else None,
			}
		)
	return собранное


def _вопросы_с_эталонами(квиз: str) -> dict:
	вопросы = []
	for строка in frappe.get_all(
		"LMS Quiz Question", filters={"parent": квиз}, fields=["question", "type"], order_by="idx asc"
	):
		документ = frappe.get_doc("LMS Question", строка.question)
		вопросы.append(
			{
				"id": документ.name,
				"text": документ.question,
				"type": строка.type,
				"options": [
					{
						"text": документ.get(f"option_{н}"),
						"correct": bool(документ.get(f"is_correct_{н}")),
					}
					for н in range(1, course_builder.ВАРИАНТОВ_МАКСИМУМ + 1)
					if документ.get(f"option_{н}")
				],
				"answers": [
					документ.get(f"possibility_{н}")
					for н in range(1, course_builder.ВАРИАНТОВ_МАКСИМУМ + 1)
					if документ.get(f"possibility_{н}")
				],
			}
		)
	return {"id": квиз, "questions": вопросы}


def _должен_существовать(doctype: str, имя: str, код: str) -> None:
	if not frappe.db.exists(doctype, имя):
		raise Отказ(код, f"{doctype} не найден", id=имя)
