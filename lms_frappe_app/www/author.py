# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Кабинет автора: курс таким, каким его собрал агент куратора.

Зеркало, а не редактор: пишет только агент, через авторские методы, а человек
здесь смотрит собранное — структуру и наполненность, урок целиком, документ
курса — и говорит правки агенту. Данные берутся из тех же методов, что
отвечают агенту (`course_draft`, `get_lesson`): второй путь к ним разошёлся
бы с первым молча.

Здесь только раскладка для отрисовки. Норм методики — сколько знаков, сколько
вопросов — страница не знает и не показывает: это закрытая часть (спека, §3).
"""

from urllib.parse import quote

import frappe
from frappe.utils import md_to_html, sanitize_html

from lms_frappe_app.agent_learning import directives, normalizer, notes
from lms_frappe_app.api import authoring

no_cache = 1

СТРАНИЦА = "/author"
МЕТОД_РЕВИЗИИ = "lms_frappe_app.api.authoring.course_revision"
МЕТОДЫ_ЗАМЕЧАНИЙ = {
	"add": "lms_frappe_app.api.authoring.add_note",
	"reply": "lms_frappe_app.api.authoring.reply_note",
	"status": "lms_frappe_app.api.authoring.set_note_status",
}

#: Цветов глав в палитре страницы; дальше они идут по кругу.
ЦВЕТОВ_ГЛАВ = 5

#: Вкладки экрана курса: собранное, сверка с картой декомпозиции, замечания.
СБОРКА, КАРТА, ЗАМЕЧАНИЯ = "build", "map", "notes"

#: Поля директивы урока в порядке, в каком их читает агент ученика; второе
#: значение — список ли это по строке на пункт.
ПОЛЯ_УРОКА = (
	("teaching_directive", False),
	("objectives", True),
	("probing_questions", True),
	("success_criteria", True),
	("common_misconceptions", True),
)
ПОЛЯ_КУРСА = (
	("teaching_directive", False),
	("objectives", True),
	("student_profile", False),
	("glossary", True),
	("remember_about_student", True),
)


def сведения(
	пользователь: str, course: str | None = None, lesson: str | None = None, view: str | None = None
) -> dict:
	"""Что показать на странице этому пользователю.

	Без `course` — все курсы: они общие, видимость по роли, а не по
	авторству. С `course` — экран курса: вкладка сборки или, с `view=map`,
	сверка с картой декомпозиции; с `lesson` — урок. Неизвестный курс или урок
	не из этого курса дают пометку, а не ошибку: ссылку могли прислать до того,
	как агент урок перенёс или удалил.
	"""
	основа = {
		"is_guest": пользователь == "Guest",
		"login_url": f"/login?redirect-to={СТРАНИЦА}",
		"page_url": СТРАНИЦА,
		"revision_method": МЕТОД_РЕВИЗИИ,
		"allowed": True,
		"courses": [],
		"course": None,
		"lesson": None,
		"view": СБОРКА,
		"map_check": None,
		"map_notes": {},
		"notes_queue": None,
		"note_methods": МЕТОДЫ_ЗАМЕЧАНИЙ,
		"missing": False,
	}
	if основа["is_guest"]:
		return основа
	if not set(frappe.get_roles(пользователь)) & authoring.АВТОРСКИЕ_РОЛИ:
		основа["allowed"] = False
		return основа
	if not course:
		основа["courses"] = authoring.list_courses()["data"]["courses"]
		return основа

	черновик = authoring.course_draft(course=course)
	if not черновик["ok"]:
		основа["missing"] = True
		return основа
	основа["course"] = _курс(черновик["data"])
	замечания = _замечания(course)
	_замечания_курса(основа["course"], замечания)
	if lesson:
		основа["lesson"] = _урок(основа["course"], lesson)
		основа["missing"] = основа["lesson"] is None
		if основа["lesson"]:
			_замечания_урока(основа["lesson"], замечания)
	elif view == КАРТА:
		основа["view"] = КАРТА
		основа["map_check"] = _сверка(course)
		основа["map_notes"] = _по_местам(
			(з for з in замечания if з["target"].startswith("map.") and з["status"] != "accepted"),
			lambda з: з["target"].partition(".")[2],
		)
	elif view == ЗАМЕЧАНИЯ:
		основа["view"] = ЗАМЕЧАНИЯ
		основа["notes_queue"] = _очередь(замечания)
	return основа


def _замечания(course: str) -> list[dict]:
	"""Замечания курса — ровно то, что получает агент в `list_notes`, плюс
	ссылка на место: по ней из очереди открывается урок на нужном разделе."""
	замечания = authoring.list_notes(course=course)["data"]["notes"]
	for з in замечания:
		з["anchor"] = якорь(з["target"])
		if з["target"].startswith("map."):
			з["url"] = f"{адрес(course)}&view={КАРТА}&node={quote(з['target'].partition('.')[2])}"
		elif з["lesson"] and not з["missing"]:
			з["url"] = f"{адрес(course, з['lesson'])}#{з['anchor']}"
		else:
			з["url"] = f"{адрес(course)}#{з['anchor']}"
	return замечания


def якорь(target: str) -> str:
	"""Якорь места на странице: `directive.teaching_directive` →
	`note-directive-teaching_directive`."""
	return "note-" + target.replace(".", "-").replace("/", "-")


def _по_местам(замечания, ключ) -> dict[str, list[dict]]:
	собранное: dict[str, list[dict]] = {}
	for з in замечания:
		собранное.setdefault(ключ(з), []).append(з)
	return собранное


def _замечания_курса(курс: dict, замечания: list[dict]) -> None:
	"""Счётчики для вкладки и таблицы, замечания мест курса вне уроков."""
	курс["notes_attention"] = sum(з["waiting_on"] == "author" for з in замечания)
	курс["notes_revision"] = authoring.ревизия_замечаний(курс["id"])
	открытые = [з for з in замечания if з["status"] != "accepted"]
	for глава in курс["chapters"]:
		for урок in глава["lessons"]:
			урок["open_notes"] = sum(з["lesson"] == урок["id"] for з in открытые)
	курс["notes"] = _по_местам(
		(з for з in замечания if not з["lesson"] and not з["target"].startswith("map.")), lambda з: з["target"]
	)


def _замечания_урока(урок: dict, замечания: list[dict]) -> None:
	свои = [з for з in замечания if з["lesson"] == урок["id"]]
	урок["notes"] = _по_местам(свои, lambda з: з["target"])
	урок["open_notes"] = sum(з["status"] != "accepted" for з in свои)


def _очередь(замечания: list[dict]) -> dict[str, list[dict]]:
	"""Очередь по тому, что ждёт человека: проверить сделанное, ответить
	агенту, ждать агента, принятые."""
	очередь: dict[str, list[dict]] = {"check": [], "question": [], "agent": [], "accepted": []}
	for з in замечания:
		очередь[notes.группа(з["status"], з["waiting_on"])].append(з)
	return очередь


def _сверка(course: str) -> dict:
	"""Сверка с картой — ровно то, что отдаёт агенту `course_map_check`, плюс
	ссылки на уроки кабинета: из карточки узла урок открывается целиком."""
	сверка = authoring.course_map_check(course=course)["data"]
	for урок in сверка["platform"]["lessons"]:
		урок["url"] = адрес(course, урок["id"])
	return сверка


def адрес(course: str, lesson: str | None = None) -> str:
	путь = f"{СТРАНИЦА}?course={quote(course)}"
	return f"{путь}&lesson={quote(lesson)}" if lesson else путь


def _курс(курс: dict) -> dict:
	"""Черновик, разложенный для отрисовки: номера, цвета глав, блоки уроков."""
	блоки_урока: dict[str, list[str]] = {}
	for документ in курс["artifacts"]:
		for блок in документ["blocks"]:
			if блок["lesson"]:
				блоки_урока.setdefault(блок["lesson"], []).append(блок["key"])

	номер = 0
	названия = {}
	for индекс, глава in enumerate(курс["chapters"]):
		глава["color"] = индекс % ЦВЕТОВ_ГЛАВ + 1
		for урок in глава["lessons"]:
			номер += 1
			урок["number"] = номер
			урок["url"] = адрес(курс["id"], урок["id"])
			урок["blocks"] = блоки_урока.get(урок["id"], [])
			урок["chapter_title"] = глава["title"]
			названия[урок["id"]] = урок["title"]

	уроки = [урок for глава in курс["chapters"] for урок in глава["lessons"]]
	курс["counts"] = {
		"lessons": len(уроки),
		"with_body": sum(у["has_body"] for у in уроки),
		"with_directive": sum(у["has_directive"] for у in уроки),
		"with_quiz": sum(у["quiz"] is not None for у in уроки),
	}
	for вид in ("blocking", "warnings"):
		for пункт in курс["readiness"][вид]:
			if пункт.get("lesson"):
				пункт["lesson_title"] = названия.get(пункт["lesson"])
				пункт["url"] = адрес(курс["id"], пункт["lesson"])
	for документ in курс["artifacts"]:
		for блок in документ["blocks"]:
			блок["artifact"] = документ["artifact"]
			блок["lesson_title"] = названия.get(блок["lesson"]) if блок["lesson"] else None
			блок["lesson_url"] = адрес(курс["id"], блок["lesson"]) if блок["lesson"] else None
	курс["directive_fields"] = _поля(курс["directive"], ПОЛЯ_КУРСА)
	курс["url"] = адрес(курс["id"])
	return курс


def _урок(курс: dict, lesson: str) -> dict | None:
	уроки = [урок for глава in курс["chapters"] for урок in глава["lessons"]]
	место = next((индекс for индекс, урок in enumerate(уроки) if урок["id"] == lesson), None)
	if место is None:
		return None
	сводка = уроки[место]
	полный = authoring.get_lesson(lesson=lesson)["data"]
	сегменты = normalizer.нормализовать_урок(lesson).segments
	return {
		"id": lesson,
		"title": полный["title"],
		"number": сводка["number"],
		"chapter_title": сводка["chapter_title"],
		"facts": сводка,
		"segments_html": [sanitize_html(md_to_html(сегмент)) for сегмент in сегменты],
		"directive": _директива(полный["directive"]),
		"quiz": _квиз(полный["quiz"]),
		"blocks": [
			блок
			for документ in курс["artifacts"]
			for блок in документ["blocks"]
			if блок["lesson"] == lesson
		],
		"prev": _сосед(уроки, место - 1),
		"next": _сосед(уроки, место + 1),
	}


def _директива(директива: dict | None) -> dict | None:
	if not директива:
		return None
	return {
		"version": директива["version"],
		"created_at": директива["created_at"],
		"objectives": directives.строки(директива.get("objectives")),
		"fields": _поля(директива, ПОЛЯ_УРОКА),
	}


def _поля(директива: dict | None, поля: tuple) -> list[dict]:
	"""Поля директивы для отрисовки: текст — разметкой, список — пунктами."""
	if not директива:
		return []
	собранное = []
	for имя, списком in поля:
		значение = директива.get(имя)
		if not значение:
			continue
		собранное.append(
			{
				"name": имя,
				"items": directives.строки(значение) if списком else None,
				"html": None if списком else sanitize_html(md_to_html(значение)),
			}
		)
	return собранное


def _квиз(квиз: dict | None) -> dict | None:
	"""Квиз с эталонами. Вопрос без текста или без верного варианта помечен —
	это те же беды, что блокируют публикацию."""
	if not квиз:
		return None
	for вопрос in квиз["questions"]:
		без_эталона = not any(вариант["correct"] for вариант in вопрос["options"]) and not вопрос["answers"]
		вопрос["broken"] = not (вопрос["text"] or "").strip() or без_эталона
	return квиз


def _сосед(уроки: list[dict], индекс: int) -> dict | None:
	if 0 <= индекс < len(уроки):
		урок = уроки[индекс]
		return {"id": урок["id"], "title": урок["title"], "number": урок["number"], "url": урок["url"]}
	return None


def get_context(context):
	context.no_breadcrumbs = True
	context.update(
		сведения(
			frappe.session.user,
			frappe.form_dict.get("course"),
			frappe.form_dict.get("lesson"),
			frappe.form_dict.get("view"),
		)
	)
	if context.lesson:
		context.title = f"{context.lesson['title']} — кабинет автора"
	elif context.course and context.view == КАРТА:
		context.title = f"{context.course['title']} — карта — кабинет автора"
	elif context.course and context.view == ЗАМЕЧАНИЯ:
		context.title = f"{context.course['title']} — замечания — кабинет автора"
	elif context.course:
		context.title = f"{context.course['title']} — кабинет автора"
	else:
		context.title = "Кабинет автора"
	if context.course:
		# Замечания пишутся с этой страницы whitelisted-методами, а POST без
		# токена Frappe отклоняет.
		context.csrf_token = frappe.sessions.get_csrf_token()
	return context
