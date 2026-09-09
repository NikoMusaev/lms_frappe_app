# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Методы учебного потока.

Спроектированы вокруг занятия, а не вокруг таблиц: универсального доступа к
записям здесь нет и не будет — иначе агент начнёт изобретать собственные
сценарии в обход педагогики и прав.
"""

import frappe
from frappe.utils import now_datetime

from lms_frappe_app.agent_learning import quiz
from lms_frappe_app.agent_learning.access import (
	НЕ_ЗАЧИСЛЕН,
	организация_приостановлена,
	доступен_курс,
	ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА,
	каталог_для,
	курсы_ученика,
	можно_записаться,
	политика_квиза_для_курса,
)
from lms_frappe_app.agent_learning.errors import Отказ
from lms_frappe_app.agent_learning.normalizer import нормализовать_урок
from lms_frappe_app.agent_learning.structure import главы_курса, уроки_курса
from lms_frappe_app.api import контракт, список, текущий_пользователь

НЕЧЕГО_УЧИТЬ = "nothing_to_study"
НЕТ_ОТЧЁТА = "outcomes_required"
ЦЕЛИ_НЕ_СОВПАЛИ = "objectives_mismatch"
НУЖЕН_КВИЗ = "quiz_required"
УРОК_НЕ_НАЙДЕН = "lesson_not_found"
ЧУЖОЕ_ЗАНЯТИЕ = "not_your_session"

#: Как прошла цель на занятии. Промежуточного «почти разобрали» нет намеренно:
#: шкала из трёх делений заполняется одинаково разными агентами, из пяти —
#: по-разному.
СТАТУСЫ_ЦЕЛЕЙ = ("covered", "touched", "skipped")

ПЕРЕПОЛНЕНО = "note_limit_reached"
ЗАМЕТКА_НЕ_НАЙДЕНА = "note_not_found"
НЕИЗВЕСТНЫЙ_ВИД = "unknown_note_kind"

#: Наружу вид заметки зовётся строчными словами, внутри — значениями Select.
ВИДЫ_ЗАМЕТОК = {"fact": "Fact", "observation": "Observation"}

#: Сколько ключей помещается в один набор. `Why:` предел вместо фоновой
#: уборки: он держит профиль читаемым без второй движущейся части, а упор в
#: него агент разрешает сам — заменой записи по существующему ключу.
ЛИМИТ_ЗАМЕТОК = 20


@frappe.whitelist()
@контракт
def list_my_courses() -> dict:
	"""Назначенные курсы с прогрессом, дедлайнами и просрочками."""
	ученик = текущий_пользователь()
	курсы = []
	for запись in курсы_ученика(ученик):
		# Уроки и пройденное читаются один раз на курс: прежняя редакция
		# строила их заново для прогресса и для следующего урока.
		уроки = уроки_курса(запись["course"])
		пройдены = _пройденные(ученик, запись["course"])
		пройдено = len([урок for урок in уроки if урок in пройдены])
		всего = len(уроки)
		следующий = _первый_непройденный(уроки, пройдены)
		курсы.append(
			{
				"id": запись["course"],
				"title": frappe.db.get_value("LMS Course", запись["course"], "title"),
				"organization": запись["organization"],
				"mandatory": запись["mandatory"],
				"deadline": запись["deadline"],
				"overdue": запись["overdue"],
				"progress": {"lessons_total": всего, "lessons_completed": пройдено},
				"next_lesson": следующий,
			}
		)
	return {"courses": курсы}


@frappe.whitelist()
@контракт
def list_catalog() -> dict:
	"""Курсы, на которые ученик может записаться сам."""
	return {"courses": каталог_для(текущий_пользователь())}


@frappe.whitelist(methods=["POST"])
@контракт
def enroll(course: str) -> dict:
	"""Записывает ученика на курс из каталога."""
	ученик = текущий_пользователь()
	можно, причина = можно_записаться(ученик, course)
	if not можно:
		raise Отказ(причина, "На этот курс записаться нельзя", course=course)

	frappe.get_doc(
		{
			"doctype": "LMS Enrollment",
			"member": ученик,
			"course": course,
			"member_type": "Student",
		}
	).insert(ignore_permissions=True)

	return {
		"course": course,
		"title": frappe.db.get_value("LMS Course", course, "title"),
		"first_lesson": _следующий_урок(ученик, course),
	}


@frappe.whitelist()
@контракт
def course_outline(course: str) -> dict:
	"""Структура курса: главы, уроки и что из них пройдено.

	`Why:` без этого агент видит только следующий незакрытый урок и не может
	вернуться к пройденному — идентификатор взять неоткуда. «Повторим
	прошлую тему перед экзаменом» было невыполнимо при живом доступе к
	материалу.
	"""
	ученик = текущий_пользователь()
	можно, причина = доступен_курс(ученик, course)
	if not можно:
		raise Отказ(причина, "Этот курс сейчас недоступен", course=course)

	пройдены = _пройденные(ученик, course)
	следующий = _следующий_урок(ученик, course)
	# Порядок берётся тот же, что у остального кода: через ссылки глав и
	# уроков, иначе структура разойдётся с тем, что считает «следующим уроком».
	порядок = уроки_курса(course)
	названия = {
		урок.name: урок.title
		for урок in frappe.get_all(
			"Course Lesson", filters={"name": ("in", порядок)}, fields=["name", "title"]
		)
	} if порядок else {}

	главы = []
	for глава in главы_курса(course):
		уроки_главы = [
			урок
			for урок in порядок
			if frappe.db.get_value("Course Lesson", урок, "chapter") == глава["name"]
		]
		главы.append(
			{
				"title": глава["title"],
				"lessons": [
					{
						"id": урок,
						"title": названия.get(урок),
						"completed": урок in пройдены,
						"current": bool(следующий and следующий["id"] == урок),
					}
					for урок in уроки_главы
				],
			}
		)
	return {"course": course, "chapters": главы}


@frappe.whitelist(methods=["POST"])
@контракт
def start_lesson(lesson: str | None = None, segment: int = 1) -> dict:
	"""Начинает занятие: создаёт сессию и отдаёт всё нужное для урока.

	`segment` — часть длинного урока, считая с единицы. Без него агент видел
	бы только начало: материал режется по заголовкам, а способа попросить
	продолжение не было вовсе.
	"""
	ученик = текущий_пользователь()
	lesson = lesson or _выбрать_урок(ученик)

	курс = _курс_урока(lesson)
	# Один обход вместо трёх: доступ, сведения о курсе и просрочка берутся
	# из одного и того же списка.
	доступные = {запись["course"]: запись for запись in курсы_ученика(ученик)}
	if курс not in доступные:
		причина = (
			ОРГАНИЗАЦИЯ_ПРИОСТАНОВЛЕНА
			if frappe.db.exists("LMS Enrollment", {"member": ученик, "course": курс})
			else НЕ_ЗАЧИСЛЕН
		)
		raise Отказ(причина, "Этот курс сейчас недоступен", course=курс)

	# Продолжение урока не заводит второе занятие: иначе на один урок копились
	# бы незакрытые сессии, которые потом закрывает фоновая задача.
	занятие = _текущее_занятие(ученик, lesson) or frappe.get_doc(
		{
			"doctype": "Agent Learning Session",
			"student": ученик,
			"lesson": lesson,
			"course": курс,
			"via_trusted_service": 1,
		}
	).insert(ignore_permissions=True)

	материал = нормализовать_урок(lesson)
	segment = max(1, int(segment or 1))
	директива = _директива(lesson)
	курсовая = _директива_курса(курс)
	# Событие одно: занятие выдало инструкцию, а из скольких она частей — деталь,
	# за которой в журнале нет смысла следить.
	занятие.записать_событие("Directive Issued", f"урок {lesson}")

	политика = политика_квиза_для_курса(ученик, курс)
	сведения = доступные[курс]

	return {
		"session": занятие.name,
		"lesson": {
			"id": lesson,
			"title": материал.title,
			"course": курс,
			"overdue": bool(сведения.get("overdue")),
		},
		"content": {
			"markdown": материал.сегмент(segment),
			"segment_index": min(segment, материал.total_segments or 1),
			"total_segments": материал.total_segments,
		},
		"media": [
			{"kind": м.kind, "title": м.title, "url": м.url} for м in материал.media
		],
		"objectives": директива.get("objectives", []),
		"directive": директива.get("directive"),
		"course_objectives": курсовая.get("objectives", []),
		"course_directive": курсовая.get("directive"),
		"quiz": {
			"required": политика["quiz_required"],
			"pass_threshold": политика["pass_threshold"],
			"attempts_left": _осталось_попыток(ученик, lesson, политика),
		},
		# Отдельным полем, а не внутри директивы: заметки ведутся об ученике
		# и доступны ему, грифа «не показывать» на них нет. Смешать одно с
		# другим значило бы соврать агенту про режим обращения.
		"student_context": {
			**_заметки(ученик, курс),
			"carried_over": _незакрытые_цели(ученик, курс, кроме=lesson),
		},
	}


@frappe.whitelist(methods=["POST"])
@контракт
def remember(kind: str, key: str, text: str, session: str | None = None) -> dict:
	"""Записывает об ученике то, что пригодится на следующих занятиях.

	Ключ короткий и повторяемый: запись по существующему ключу замещает
	текст. Наблюдение привязывается к курсу занятия, факт живёт у ученика
	целиком — роль и отрасль от предмета не зависят.
	"""
	ученик = текущий_пользователь()
	вид = ВИДЫ_ЗАМЕТОК.get((kind or "").strip().lower())
	if not вид:
		raise Отказ(НЕИЗВЕСТНЫЙ_ВИД, "Вид заметки — fact или observation", kind=kind)

	# Пустая строка, а не None: ею Frappe хранит незаполненный Link, и фильтр
	# по None искал бы `course is null`, не находя ни одной записи.
	курс = ""
	занятие = None
	if вид == "Observation":
		if not session:
			raise Отказ(
				ЧУЖОЕ_ЗАНЯТИЕ,
				"Наблюдение записывается в рамках занятия: передайте session",
			)
		занятие = _своё_занятие(session)
		курс = занятие.course

	ключ = (key or "").strip().lower()
	if not ключ:
		raise Отказ(НЕИЗВЕСТНЫЙ_ВИД, "Ключ заметки обязателен", key=key)

	существующая = frappe.db.exists(
		"Agent Student Note", {"student": ученик, "course": курс, "note_key": ключ}
	)
	if not существующая:
		сколько = frappe.db.count(
			"Agent Student Note", {"student": ученик, "course": курс, "kind": вид}
		)
		if сколько >= ЛИМИТ_ЗАМЕТОК:
			raise Отказ(
				ПЕРЕПОЛНЕНО,
				"Заметок уже предельно много: замените запись по существующему ключу",
				limit=ЛИМИТ_ЗАМЕТОК,
			)

	значения = {
		"text": text,
		"kind": вид,
		"source_session": занятие.name if занятие else None,
	}
	if существующая:
		запись = frappe.get_doc("Agent Student Note", существующая)
		запись.update(значения)
		запись.save(ignore_permissions=True)
	else:
		запись = frappe.get_doc(
			{
				"doctype": "Agent Student Note",
				"student": ученик,
				"course": курс,
				"note_key": ключ,
				**значения,
			}
		).insert(ignore_permissions=True)

	return {"key": запись.note_key, "kind": kind}


@frappe.whitelist(methods=["POST"])
@контракт
def forget(key: str, course: str | None = None) -> dict:
	"""Удаляет заметку об ученике по ключу.

	Ученик вправе стереть о себе всё: заметки ведутся о нём и доступны ему.
	"""
	имя = frappe.db.exists(
		"Agent Student Note",
		{
			"student": текущий_пользователь(),
			"course": course or "",
			"note_key": (key or "").strip().lower(),
		},
	)
	if not имя:
		raise Отказ(ЗАМЕТКА_НЕ_НАЙДЕНА, "Такой заметки нет", key=key)
	frappe.delete_doc("Agent Student Note", имя, ignore_permissions=True)
	return {"key": key}


@frappe.whitelist()
@контракт
def whoami() -> dict:
	"""Под какой учётной записью вошёл ученик и в каких он организациях.

	`Why:` пустой список курсов сам по себе ничего не объясняет — вошли не
	тем аккаунтом или тем, но без зачислений, выглядит одинаково. Наружу идут
	только собственные данные ученика: своё имя он и так знает. Ролей Frappe
	здесь нет — это устройство платформы, а не сведения о человеке.
	"""
	ученик = текущий_пользователь()
	организации = []
	for членство in frappe.get_all(
		"Organization Membership",
		filters={"user": ученик},
		fields=["organization", "role"],
		ignore_permissions=True,
	):
		организации.append(
			{
				"id": членство.organization,
				"title": frappe.db.get_value(
					"Learning Organization", членство.organization, "organization_name"
				),
				"role": членство.role,
				# Приостановленная организация закрывает доступ к своим курсам,
				# и без этого признака пустой каталог необъясним.
				"suspended": организация_приостановлена(членство.organization),
			}
		)
	return {
		"login": ученик,
		"full_name": frappe.db.get_value("User", ученик, "full_name"),
		"organizations": организации,
	}


@frappe.whitelist()
@контракт
def my_notes(course: str | None = None) -> dict:
	"""Что агент запомнил об ученике. Ученик вправе это видеть."""
	return _заметки(текущий_пользователь(), course)


@frappe.whitelist(methods=["POST"])
@контракт
def report_outcomes(session: str, outcomes) -> dict:
	"""Отчёт о покрытии целей урока — граница занятия.

	Сдаётся до квиза и до закрытия урока: проверять знания или закрывать
	урок, не сказав, что разобрано, бессмысленно. Состав сверяется с целями
	действующей директивы — без сверки обязательный отчёт вырождается в
	пустой список.
	"""
	занятие = _своё_занятие(session)
	цели = _цели_урока(занятие.lesson)
	сданные = {}
	for пункт in список(outcomes):
		цель = (пункт.get("objective") or "").strip()
		статус = (пункт.get("status") or "").strip()
		if статус not in СТАТУСЫ_ЦЕЛЕЙ:
			raise Отказ(
				ЦЕЛИ_НЕ_СОВПАЛИ,
				"Статус цели должен быть covered, touched или skipped",
				objective=цель,
				status=статус,
			)
		сданные[цель] = статус

	if set(сданные) != set(цели):
		raise Отказ(
			ЦЕЛИ_НЕ_СОВПАЛИ,
			"Отчёт должен покрывать ровно цели урока",
			missing=sorted(set(цели) - set(сданные)),
			unexpected=sorted(set(сданные) - set(цели)),
		)

	# Порядок целей — из директивы, а не из отчёта: строки таблицы читаются в
	# том же порядке, в каком автор задумывал урок.
	занятие.outcomes = []
	for цель in цели:
		занятие.append("outcomes", {"objective": цель, "status": сданные[цель]})
	занятие.save(ignore_permissions=True)
	занятие.записать_событие("Checkpoint Reported", "отчёт по целям урока")

	return {"session": session, "reported": len(цели)}


@frappe.whitelist(methods=["POST"])
@контракт
def report_checkpoint(session: str, note: str) -> dict:
	"""Отметка о пройденном по ходу занятия. Телеметрия, не зачёт."""
	занятие = _своё_занятие(session)
	занятие.записать_событие("Checkpoint Reported", note)
	return {"recorded_at": now_datetime().isoformat()}


@frappe.whitelist(methods=["POST"])
@контракт
def complete_lesson(session: str) -> dict:
	"""Отмечает урок пройденным, когда проверять нечего.

	Для урока с обязательным квизом отказывает: иначе этот метод стал бы
	обходом проверки. Зачёт по квизу ставит только сервер, и обойти его
	вызовом нельзя.
	"""
	занятие = _своё_занятие(session)
	_требовать_отчёт(занятие)
	if quiz.требуется_квиз(занятие.lesson, занятие.student, занятие.course):
		raise Отказ(
			НУЖЕН_КВИЗ,
			"Этот урок закрывается только сдачей квиза",
			session=session,
		)

	quiz.отметить_урок_пройденным(занятие)
	if занятие.status in ("In Progress", "Awaiting Quiz"):
		занятие.status = "Completed"
		занятие.save(ignore_permissions=True)
	занятие.записать_событие("Verdict Returned", "урок закрыт без квиза")

	return {
		"lesson": занятие.lesson,
		"session_status": занятие.status,
		"next_lesson": _следующий_урок(занятие.student, занятие.course),
	}


@frappe.whitelist(methods=["POST"])
@контракт
def request_quiz(session: str) -> dict:
	"""Создаёт попытку и отдаёт первый вопрос."""
	_требовать_отчёт(_своё_занятие(session))
	return quiz.начать_попытку(session)


@frappe.whitelist(methods=["POST"])
@контракт
def submit_answer(attempt: str, question: str, answer: str) -> dict:
	"""Принимает ответ, возвращает вердикт и следующий вопрос."""
	попытка = frappe.get_doc("Agent Quiz Attempt", attempt)
	if попытка.student != текущий_пользователь():
		# Права на чтение мало: занятия и попытки своих людей читает ещё и
		# руководитель, а отвечать за ученика он не должен — иначе сожжёт
		# ему попытку или провалит квиз за него.
		raise Отказ(ЧУЖОЕ_ЗАНЯТИЕ, "Это чужая попытка", attempt=attempt)
	return quiz.принять_ответ(attempt, question, answer)


@frappe.whitelist()
@контракт
def get_my_progress() -> dict:
	"""Сводка по себе."""
	ученик = текущий_пользователь()
	курсы = курсы_ученика(ученик)
	занятия = frappe.get_all(
		"Agent Learning Session",
		filters={"student": ученик},
		fields=["lesson", "status", "started_at"],
		order_by="started_at desc",
		limit=10,
	)
	return {
		"courses_total": len(курсы),
		"courses_overdue": sum(1 for к in курсы if к["overdue"]),
		"courses": [
			{
				"id": курс["course"],
				"title": frappe.db.get_value("LMS Course", курс["course"], "title"),
				"deadline": курс["deadline"],
				"overdue": курс["overdue"],
				"completion": _доля_пройденного(ученик, курс["course"]),
			}
			for курс in курсы
		],
		"recent_sessions": [
			{
				"lesson": з.lesson,
				"status": з.status,
				"started_at": з.started_at.isoformat() if з.started_at else None,
			}
			for з in занятия
		],
	}


# --- вспомогательное ---


def _текущее_занятие(ученик: str, lesson: str):
	"""Незакрытое занятие ученика по этому уроку, если оно есть."""
	открытые = frappe.get_all(
		"Agent Learning Session",
		filters={
			"student": ученик,
			"lesson": lesson,
			"status": ("in", ("In Progress", "Awaiting Quiz")),
		},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return frappe.get_doc("Agent Learning Session", открытые[0]) if открытые else None


def _своё_занятие(session: str):
	"""Занятие текущего ученика. Чужое отклоняется до всякого действия."""
	занятие = frappe.get_doc("Agent Learning Session", session)
	if занятие.student != текущий_пользователь():
		raise Отказ(ЧУЖОЕ_ЗАНЯТИЕ, "Это чужое занятие", session=session)
	return занятие


def _заметки(ученик: str, course: str | None) -> dict:
	"""Факты и наблюдения курса — с датами.

	Даты наружу не для красоты: наблюдение трёхмесячной давности и вчерашнее
	— разные утверждения, и без даты агент примет старое за текущее и станет
	объяснять человеку давно освоенное.

	`ignore_permissions` здесь безопасен: фильтр по ученику уже сузил выборку
	до своего, а права повторили бы то же условие вторым способом.
	"""
	записи = frappe.get_all(
		"Agent Student Note",
		filters={"student": ученик},
		or_filters=[["course", "=", ""], ["course", "=", course or ""]],
		fields=["note_key", "text", "kind", "creation", "modified"],
		order_by="modified desc",
		ignore_permissions=True,
	)
	факты, наблюдения = [], []
	for з in записи:
		если_факт = з.kind == "Fact"
		(факты if если_факт else наблюдения).append(
			{
				"key": з.note_key,
				"text": з.text,
				"since": з.creation.isoformat() if если_факт else None,
				"updated": з.modified.isoformat(),
			}
		)
	return {"facts": факты, "observations": наблюдения}


#: Сколько последних уроков курса приносят с собой незакрытые цели. `Why:`
#: без границы к концу курса это список всего, что когда-либо не дошло, —
#: агент прочитает его целиком и целиком же проигнорирует.
ГЛУБИНА_ПЕРЕНОСА = 3


def _незакрытые_цели(ученик: str, курс: str, кроме: str) -> list[dict]:
	"""Цели прошлых уроков курса, до которых не дошли или дошли вскользь."""
	занятия = frappe.get_all(
		"Agent Learning Session",
		filters={"student": ученик, "course": курс, "status": "Completed"},
		fields=["name", "lesson", "finished_at"],
		order_by="finished_at desc",
		ignore_permissions=True,
	)
	перенос = []
	увиденные = set()
	for занятие in занятия:
		# Урок мог проходиться дважды: значим последний отчёт по нему.
		if занятие.lesson == кроме or занятие.lesson in увиденные:
			continue
		увиденные.add(занятие.lesson)
		if len(увиденные) > ГЛУБИНА_ПЕРЕНОСА:
			break
		for строка in frappe.get_all(
			"Agent Objective Outcome",
			filters={
				"parent": занятие.name,
				"parenttype": "Agent Learning Session",
				"status": ("in", ("touched", "skipped")),
			},
			fields=["objective", "status"],
			order_by="idx asc",
			ignore_permissions=True,
		):
			перенос.append(
				{
					"objective": строка.objective,
					"status": строка.status,
					"lesson": занятие.lesson,
					"when": занятие.finished_at.isoformat() if занятие.finished_at else None,
				}
			)
	return перенос


def _цели_урока(lesson: str) -> list[str]:
	"""Цели действующей директивы урока, в порядке автора."""
	return _директива(lesson).get("objectives", [])


def _требовать_отчёт(занятие) -> None:
	"""Отказывает, пока отчёт по целям не сдан.

	Урок без целей отчёта не требует: требовать нечего, и отказ загнал бы
	агента в тупик без способа из него выйти.
	"""
	if not _цели_урока(занятие.lesson) or занятие.outcomes:
		return
	raise Отказ(
		НЕТ_ОТЧЁТА,
		"Сначала сдайте отчёт по целям урока: report_outcomes",
		session=занятие.name,
	)


def _курс_урока(lesson: str) -> str:
	глава = frappe.db.get_value("Course Lesson", lesson, "chapter")
	курс = frappe.db.get_value("Course Chapter", глава, "course") if глава else None
	if not курс:
		raise Отказ(УРОК_НЕ_НАЙДЕН, "Такого урока нет", lesson=lesson)
	return курс


def _выбрать_урок(ученик: str) -> str:
	"""Следующий незакрытый урок с ближайшим дедлайном.

	Порядок важен: сначала просроченные и срочные курсы, потом остальные —
	ученик, попросивший «давай заниматься», должен получить то, что горит.
	"""
	курсы = sorted(
		курсы_ученика(ученик),
		key=lambda к: (к["deadline"] is None, к["deadline"] or "", not к["mandatory"]),
	)
	for курс in курсы:
		следующий = _следующий_урок(ученик, курс["course"])
		if следующий:
			return следующий["id"]
	raise Отказ(НЕЧЕГО_УЧИТЬ, "Незакрытых уроков не осталось")


def _пройденные(ученик: str, курс: str) -> set[str]:
	return set(
		frappe.get_all(
			"LMS Course Progress",
			filters={"member": ученик, "course": курс, "status": "Complete"},
			pluck="lesson",
		)
	)


def _доля_пройденного(ученик: str, курс: str) -> float:
	"""Доля пройденных уроков курса — её обещает контракт в сводке."""
	уроки = уроки_курса(курс)
	if not уроки:
		return 0.0
	пройдены = _пройденные(ученик, курс)
	return round(len([урок for урок in уроки if урок in пройдены]) / len(уроки), 2)


def _первый_непройденный(уроки: list[str], пройдены: set[str]) -> dict | None:
	for урок in уроки:
		if урок not in пройдены:
			return {"id": урок, "title": frappe.db.get_value("Course Lesson", урок, "title")}
	return None


def _следующий_урок(ученик: str, курс: str) -> dict | None:
	return _первый_непройденный(уроки_курса(курс), _пройденные(ученик, курс))


def _директива(lesson: str) -> dict:
	"""Действующая директива урока — отдельным полем и с пометкой адресата.

	Материал и директива приходят разными полями, а сама директива помечена
	`audience: teacher_only`. Это одна из трёх митигаций против пересказа
	директивы ученику; гарантий она не даёт — гарантию даёт серверный квиз.
	"""
	запись = frappe.get_all(
		"Agent Lesson Directive",
		filters={"lesson": lesson, "is_active": 1},
		fields=[
			"objectives",
			"teaching_directive",
			"probing_questions",
			"common_misconceptions",
			"success_criteria",
		],
		limit=1,
		ignore_permissions=True,
	)
	if not запись:
		return {}
	д = запись[0]
	return {
		"objectives": _строки(д.objectives),
		"directive": {
			"audience": "teacher_only",
			"teaching_directive": д.teaching_directive,
			"probing_questions": _строки(д.probing_questions),
			"common_misconceptions": _строки(д.common_misconceptions),
			"success_criteria": _строки(д.success_criteria),
		},
	}


def _директива_курса(course: str) -> dict:
	"""Сквозная директива курса — тем же способом, что и урочная.

	Цели курса идут наружу, а не внутрь директивы: их агент вправе озвучить
	ученику, как и цели урока.
	"""
	запись = frappe.get_all(
		"Agent Course Directive",
		filters={"course": course, "is_active": 1},
		fields=[
			"objectives",
			"teaching_directive",
			"student_profile",
			"glossary",
			"remember_about_student",
		],
		limit=1,
		ignore_permissions=True,
	)
	if not запись:
		return {}
	д = запись[0]
	return {
		"objectives": _строки(д.objectives),
		"directive": {
			"audience": "teacher_only",
			"teaching_directive": д.teaching_directive,
			"student_profile": д.student_profile,
			"glossary": _строки(д.glossary),
			# Внутрь директивы, а не рядом: по каким признакам его оценивают,
			# ученику знать не нужно — начнёт подстраиваться.
			"remember_about_student": _строки(д.remember_about_student),
		},
	}


def _строки(значение: str | None) -> list[str]:
	return [строка.strip() for строка in (значение or "").splitlines() if строка.strip()]


def _осталось_попыток(ученик: str, lesson: str, политика: dict) -> int | None:
	квиз = quiz._квиз_урока(lesson)
	if not квиз:
		return None
	лимит = политика["max_attempts"]
	if not лимит:
		return None
	return max(0, лимит - quiz._прошлых_попыток(ученик, квиз))
