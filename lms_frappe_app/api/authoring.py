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

from lms_frappe_app.agent_learning import course_builder, quiz, structure
from lms_frappe_app.agent_learning.errors import Отказ
from lms_frappe_app.api import контракт, текущий_пользователь

#: Роли, которым разрешено собирать курсы. Совпадают с административными в
#: `permissions`: там они уже дают полный доступ к учебным записям.
АВТОРСКИЕ_РОЛИ = frozenset({"Course Creator", "Moderator", "System Manager", "Administrator"})

КУРС_НЕ_НАЙДЕН = "course_not_found"
УРОК_НЕ_НАЙДЕН = "lesson_not_found"
ГЛАВА_НЕ_НАЙДЕНА = "chapter_not_found"
КУРС_НЕ_ГОТОВ = "course_not_ready"
КВИЗ_УЖЕ_ЕСТЬ = "quiz_exists"
КВИЗА_НЕТ = "quiz_missing"
ВОПРОС_НЕ_НАЙДЕН = "question_not_found"
УРОК_В_РАБОТЕ = "lesson_in_use"
ГЛАВА_НЕ_ПУСТА = "chapter_not_empty"
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


@frappe.whitelist()
@контракт
def list_courses(published: bool | None = None) -> dict:
	"""Курсы платформы: черновики и опубликованные.

	Без этого метода сборка разваливается на второй сессии: все остальные
	инструменты требуют идентификатор, а взять его было негде — куратор,
	вернувшийся назавтра, не мог найти собственный курс.

	Курсы общие, поэтому список полный, а не «мои». Фильтр `published`
	сужает до одного состояния.
	"""
	_автор()
	отбор = {}
	if published is not None:
		отбор["published"] = 1 if published in (True, 1, "1", "true") else 0
	курсы = frappe.get_all(
		"LMS Course",
		filters=отбор,
		fields=["name", "title", "short_introduction", "published", "modified"],
		order_by="modified desc",
	)
	return {
		"courses": [
			{
				"id": курс.name,
				"title": курс.title,
				"summary": курс.short_introduction,
				"published": bool(курс.published),
				"lessons_total": len(structure.уроки_курса(курс.name)),
				"updated_at": курс.modified.isoformat() if курс.modified else None,
			}
			for курс in курсы
		]
	}


@frappe.whitelist(methods=["POST"])
@контракт
def update_course(
	course: str, title: str | None = None, summary: str | None = None, description: str | None = None
) -> dict:
	"""Правит название, краткое описание или полное описание курса."""
	_автор()
	_должен_существовать("LMS Course", course, КУРС_НЕ_НАЙДЕН)
	документ = frappe.get_doc("LMS Course", course)
	for поле, значение in (
		("title", title),
		("short_introduction", summary),
		("description", description),
	):
		if значение is not None:
			документ.set(поле, значение)
	документ.save()
	return {"id": документ.name, "title": документ.title, "summary": документ.short_introduction}


@frappe.whitelist(methods=["POST"])
@контракт
def update_chapter(chapter: str, title: str) -> dict:
	"""Правит название главы."""
	_автор()
	_должен_существовать("Course Chapter", chapter, ГЛАВА_НЕ_НАЙДЕНА)
	документ = frappe.get_doc("Course Chapter", chapter)
	документ.title = title
	документ.save()
	return {"id": документ.name, "title": документ.title}


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
def move_lesson(lesson: str, chapter: str | None = None, position: int | None = None) -> dict:
	"""Переносит урок в другую главу или на другое место в своей.

	`position` считается с единицы; без него урок встаёт в конец. Без
	`chapter` меняется только место внутри текущей главы.

	`Why:` без этого метода перестановка одного урока требовала передать
	порядок всей главы целиком, а перенос между главами был невозможен вовсе
	— ошибка в структуре чинилась пересборкой курса.
	"""
	_автор()
	_должен_существовать("Course Lesson", lesson, УРОК_НЕ_НАЙДЕН)
	откуда = frappe.db.get_value("Course Lesson", lesson, "chapter")
	куда = chapter or откуда
	_должен_существовать("Course Chapter", куда, ГЛАВА_НЕ_НАЙДЕНА)

	if куда != откуда:
		structure.отвязать(откуда, "Course Chapter", lesson)
		frappe.db.set_value("Course Lesson", lesson, "chapter", куда)
		frappe.db.set_value(
			"Course Lesson", lesson, "course", frappe.db.get_value("Course Chapter", куда, "course")
		)
		structure.привязать(куда, "Course Chapter", lesson)

	порядок = [урок for урок in structure.уроки_главы(куда) if урок != lesson]
	место = len(порядок) if position is None else max(0, min(int(position) - 1, len(порядок)))
	порядок.insert(место, lesson)
	structure.переставить(куда, "Course Chapter", порядок)

	return {"id": lesson, "chapter": куда, "lessons": порядок}


@frappe.whitelist(methods=["POST"])
@контракт
def remove_lesson(lesson: str) -> dict:
	"""Удаляет урок — пока по нему никто не занимался.

	`Why:` собирая курс впервые, агент создаёт лишние уроки, и без удаления
	они остаются в программе навсегда. Но урок, по которому есть прогресс или
	попытки, не удаляется ни при каких условиях: стирание испортило бы
	историю ученика, а курс от лишнего урока не рушится.

	Отвязать вместо удаления нельзя: чтение структуры намеренно подбирает
	уроки без строк-ссылок и показывает их в конце — иначе терялись бы курсы,
	собранные импортом. Отвязанный урок вернулся бы в программу.

	Требует роли `Moderator`: Frappe Learning не даёт `Course Creator` право
	удалять уроки, хотя главу, квиз и директиву — даёт. Асимметрия чужая, но
	обходить её через `ignore_permissions` нельзя: агент получил бы то, чего
	не может тот же человек в браузере.
	"""
	_автор()
	_должен_существовать("Course Lesson", lesson, УРОК_НЕ_НАЙДЕН)
	if следы := _следы_учеников(lesson):
		raise Отказ(
			УРОК_В_РАБОТЕ,
			"По этому уроку уже занимались: его можно только переписать",
			lesson=lesson,
			**следы,
		)

	глава = frappe.db.get_value("Course Lesson", lesson, "chapter")
	structure.отвязать(глава, "Course Chapter", lesson)
	if квиз := quiz._квиз_урока(lesson):
		frappe.delete_doc("LMS Quiz", квиз, ignore_permissions=True)
	for директива in frappe.get_all("Agent Lesson Directive", filters={"lesson": lesson}, pluck="name"):
		frappe.delete_doc("Agent Lesson Directive", директива, ignore_permissions=True)
	frappe.delete_doc("Course Lesson", lesson)
	return {"removed": lesson, "chapter": глава, "lessons": structure.уроки_главы(глава)}


@frappe.whitelist(methods=["POST"])
@контракт
def remove_chapter(chapter: str) -> dict:
	"""Удаляет пустую главу.

	Непустая отклоняется: уроки удаляются поштучно и с проверкой прогресса,
	и обходить её каскадом нельзя.
	"""
	_автор()
	_должен_существовать("Course Chapter", chapter, ГЛАВА_НЕ_НАЙДЕНА)
	if уроки := structure.уроки_главы(chapter):
		raise Отказ(
			ГЛАВА_НЕ_ПУСТА,
			"В главе есть уроки: удалите их по одному",
			chapter=chapter,
			lessons=уроки,
		)

	курс = frappe.db.get_value("Course Chapter", chapter, "course")
	structure.отвязать(курс, "LMS Course", chapter)
	frappe.delete_doc("Course Chapter", chapter)
	return {"removed": chapter, "course": курс}


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

	# Второй квиз на уроке — это не «ещё один квиз», а потерянный первый:
	# урок отдаёт агенту ровно один, остальные становятся невидимым мусором.
	# Правится вопросами существующего квиза, а не созданием нового.
	if существующий := quiz._квиз_урока(lesson):
		raise Отказ(
			КВИЗ_УЖЕ_ЕСТЬ,
			"У урока уже есть квиз: правьте его вопросы",
			lesson=lesson,
			quiz=существующий,
		)

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


@frappe.whitelist(methods=["POST"])
@контракт
def add_question(lesson: str, question: dict | str) -> dict:
	"""Добавляет вопрос в существующий квиз урока."""
	_автор()
	квиз = _квиз_урока_или_отказ(lesson)
	идентификатор, тип = _создать_вопрос_или_отказ(question, lesson)
	документ = frappe.get_doc("LMS Quiz", квиз)
	документ.append(
		"questions",
		{"question": идентификатор, "type": тип, "marks": (_как_словарь(question).get("marks") or 1)},
	)
	документ.save()
	return {"quiz": квиз, "question": идентификатор, "questions_total": len(документ.questions)}


@frappe.whitelist(methods=["POST"])
@контракт
def update_question(question: str, text: str | None = None, options=None, answers=None) -> dict:
	"""Правит текст вопроса, варианты или образцы ответа.

	Правка разрешена и после того, как по квизу отвечали: блокировать
	исправление опечатки в опубликованном курсе хуже, чем оставить её. Но
	число затронутых попыток возвращается — куратор должен знать, что меняет
	вопрос, который кто-то уже видел.
	"""
	_автор()
	_должен_существовать("LMS Question", question, ВОПРОС_НЕ_НАЙДЕН)
	документ = frappe.get_doc("LMS Question", question)

	if text is not None:
		документ.question = text
	if options is not None:
		course_builder.заменить_варианты(документ, _список(options))
	if answers is not None:
		course_builder.заменить_образцы(документ, _список(answers))

	frappe.db.savepoint("agent_question_edit")
	try:
		документ.save()
	except Отказ:
		raise
	except frappe.ValidationError as причина:
		# Правка, ломающая состав вариантов, отменяется целиком: иначе вопрос
		# остался бы наполовину переписанным.
		frappe.db.rollback(save_point="agent_question_edit")
		raise Отказ(НЕВЕРНЫЙ_ВОПРОС, str(причина), question=question) from причина

	return {
		"id": question,
		"text": документ.question,
		"affects_attempts": frappe.db.count("Agent Quiz Answer", {"question": question}),
	}


@frappe.whitelist(methods=["POST"])
@контракт
def remove_question(lesson: str, question: str) -> dict:
	"""Убирает вопрос из квиза урока.

	Сам вопрос не удаляется: на него ссылаются ответы прошлых попыток, и
	стирание записи испортило бы историю зачётов.
	"""
	_автор()
	квиз = _квиз_урока_или_отказ(lesson)
	документ = frappe.get_doc("LMS Quiz", квиз)
	осталось = [строка for строка in документ.questions if строка.question != question]
	if len(осталось) == len(документ.questions):
		raise Отказ(ВОПРОС_НЕ_НАЙДЕН, "В этом квизе такого вопроса нет", quiz=квиз, question=question)

	документ.questions = []
	for строка in осталось:
		документ.append("questions", {"question": строка.question, "type": строка.type, "marks": строка.marks})
	документ.save()
	return {"quiz": квиз, "questions_total": len(документ.questions)}


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


@frappe.whitelist()
@контракт
def get_lesson(lesson: str) -> dict:
	"""Урок целиком: материал, действующая директива и квиз с эталонами.

	`Why:` материал попадает на платформу вызовом `add_lesson`, а `course_draft`
	показывает лишь признак `has_body` — сверить, что на платформе лежит ровно
	утверждённый текст, было нечем, кроме как открыть урок глазами на сайте.

	Отдельный инструмент, а не поле черновика: полные тексты всех уроков в
	одном ответе — десятки килобайт на каждый вызов, а сверяют поурочно.
	"""
	_автор()
	_должен_существовать("Course Lesson", lesson, УРОК_НЕ_НАЙДЕН)
	сведения = frappe.db.get_value(
		"Course Lesson", lesson, ["title", "body", "chapter", "course"], as_dict=True
	)
	квиз = quiz._квиз_урока(lesson)
	return {
		"id": lesson,
		"title": сведения.title,
		"chapter": сведения.chapter,
		"course": сведения.course,
		"body": сведения.body,
		"directive": _действующая_директива(lesson),
		"quiz": _вопросы_с_эталонами(квиз) if квиз else None,
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
	from lms_frappe_app.agent_learning import quiz

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


def _действующая_директива(lesson: str) -> dict | None:
	"""Директива, которую сейчас получает агент ученика, со своей версией."""
	записи = frappe.get_all(
		"Agent Lesson Directive",
		filters={"lesson": lesson, "is_active": 1},
		fields=[
			"name",
			"version",
			"objectives",
			"teaching_directive",
			"probing_questions",
			"common_misconceptions",
			"success_criteria",
		],
		limit=1,
	)
	if not записи:
		return None
	запись = записи[0]
	return {
		"id": запись.name,
		"version": запись.version,
		"objectives": запись.objectives,
		"teaching_directive": запись.teaching_directive,
		"probing_questions": запись.probing_questions,
		"common_misconceptions": запись.common_misconceptions,
		"success_criteria": запись.success_criteria,
	}


def _следы_учеников(lesson: str) -> dict:
	"""Чем занимались по уроку. Пусто — значит урок никто не открывал."""
	следы = {
		"progress": frappe.db.count("LMS Course Progress", {"lesson": lesson}),
		"sessions": frappe.db.count("Agent Learning Session", {"lesson": lesson}),
		"attempts": frappe.db.count("Agent Quiz Attempt", {"lesson": lesson}),
	}
	return {ключ: значение for ключ, значение in следы.items() if значение}


def _как_словарь(вопрос) -> dict:
	return json.loads(вопрос) if isinstance(вопрос, str) else dict(вопрос or {})


def _квиз_урока_или_отказ(lesson: str) -> str:
	_должен_существовать("Course Lesson", lesson, УРОК_НЕ_НАЙДЕН)
	квиз = quiz._квиз_урока(lesson)
	if not квиз:
		raise Отказ(КВИЗА_НЕТ, "У урока нет квиза: создайте его целиком", lesson=lesson)
	return квиз


def _создать_вопрос_или_отказ(вопрос, lesson: str) -> tuple[str, str]:
	frappe.db.savepoint("agent_question_build")
	try:
		return course_builder.создать_вопрос(_как_словарь(вопрос))
	except Отказ:
		raise
	except frappe.ValidationError as причина:
		frappe.db.rollback(save_point="agent_question_build")
		raise Отказ(НЕВЕРНЫЙ_ВОПРОС, str(причина), lesson=lesson) from причина


def _должен_существовать(doctype: str, имя: str, код: str) -> None:
	if not frappe.db.exists(doctype, имя):
		raise Отказ(код, f"{doctype} не найден", id=имя)
