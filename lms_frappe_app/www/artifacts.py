# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Страница «Мои документы»: то, что ученик собрал по ходу курса.

Показывает документ целиком, отмечает незаполненные блоки подсказками автора
и даёт скачать markdown — собранную папку проекта на выходе из курса. Правка
поблочная и идёт тем же методом, что у агента: `update_artifact`.

Здесь только раскладка и отрисовка; какие документы и из чего состоят,
решает схема автора, а помогает заполнять агент. Страница ни того, ни
другого не знает.
"""

import frappe
from frappe.utils import md_to_html, sanitize_html

from lms_frappe_app.agent_learning.access import доступен_курс, курсы_ученика
from lms_frappe_app.agent_learning.errors import Отказ
from lms_frappe_app.api import student, текущий_пользователь
from lms_frappe_app.site_navigation import шапка_платформы

no_cache = 1

СТРАНИЦА = "/artifacts"
МЕТОД_ЗАПИСИ = "lms_frappe_app.api.student.update_artifact"
МЕТОД_ЗАГРУЗКИ = "lms_frappe_app.api.student.upload_artifact_file"
ПУСТОЙ_БЛОК = "_Не заполнено._"


def сведения(пользователь: str, course: str | None = None, artifact: str | None = None) -> dict:
	"""Что показать на странице этому пользователю.

	Без `course` и `artifact` — курсы с их документами и долей заполненности;
	с ними — один документ целиком. Чужой курс и неизвестный документ дают
	пустую страницу с пометкой, а не ошибку: ссылку могли прислать по старой
	схеме.

	Только `course` — документы этого курса: так на них ведёт веб-чат из
	урока (learning-services#303). У курса документов нет или он чужой —
	весь список, чтобы ссылка не приводила на пустую страницу.
	"""
	гость = пользователь == "Guest"
	основа = {
		"is_guest": гость,
		"login_url": f"/login?redirect-to={СТРАНИЦА}",
		"page_url": СТРАНИЦА,
		"update_method": МЕТОД_ЗАПИСИ,
		"upload_method": МЕТОД_ЗАГРУЗКИ,
		"courses": [],
		"document": None,
		"missing": False,
	}
	if гость:
		return основа
	if course and artifact:
		документ = _документ(пользователь, course, artifact)
		основа["document"] = документ
		основа["missing"] = документ is None
		return основа
	курсы = _курсы(пользователь)
	if course:
		курсы = [курс for курс in курсы if курс["id"] == course] or курсы
	основа["courses"] = курсы
	return основа


def _курсы(пользователь: str) -> list[dict]:
	"""Курсы ученика, у которых есть документы. Без документов курсу здесь
	делать нечего: страница про них, а не про программу."""
	курсы = []
	for запись in курсы_ученика(пользователь):
		перечень = student._перечень_артефактов(пользователь, запись["course"])
		if not перечень:
			continue
		курсы.append(
			{
				"id": запись["course"],
				"title": frappe.db.get_value("LMS Course", запись["course"], "title"),
				"artifacts": перечень,
			}
		)
	return курсы


def _документ(пользователь: str, course: str, artifact: str) -> dict | None:
	можно, _ = доступен_курс(пользователь, course)
	if not можно:
		return None
	try:
		документ = student._артефакт_целиком(пользователь, course, artifact)
	except Отказ:
		return None
	документ["course_title"] = frappe.db.get_value("LMS Course", course, "title")
	for блок in документ["blocks"]:
		# Содержимое — markdown ученика; на страницу оно идёт разметкой и
		# только после чистки: свой же скрипт человеку не страшен, а чужого
		# здесь не бывает, но правило «HTML из базы не доверять» одно на всех.
		блок["html"] = sanitize_html(md_to_html(блок["content"])) if блок["content"] else ""
		# Срез — таблица markdown; ученику он показывает, что увидит агент.
		блок["preview_html"] = sanitize_html(md_to_html(блок["preview"])) if блок["preview"] else ""
		блок["accept_attr"] = ",".join("." + тип for тип in блок["accept"])
		if блок["file"]:
			блок["file"]["size_display"] = _размер(блок["file"]["size"])
	документ["download_url"] = (
		f"/api/method/lms_frappe_app.www.artifacts.download?course={course}&artifact={документ['artifact']}"
	)
	return документ


def _размер(байт: int) -> str:
	if байт < 1024:
		return f"{байт} Б"
	if байт < 1024 * 1024:
		return f"{байт / 1024:.0f} КБ"
	return f"{байт / (1024 * 1024):.1f} МБ"


def собрать_markdown(документ: dict) -> str:
	"""Документ одним файлом: заголовок и блоки в порядке схемы.

	Файл блока сюда не вкладывается — только его имя и срез: markdown остаётся
	текстом, а сам файл скачивается со страницы.
	"""
	части = [f"# {документ['title']}"]
	for блок in документ["blocks"]:
		части.append(f"## {блок['title']}")
		текст = (блок["content"] or "").strip()
		if блок.get("url"):
			текст = "\n\n".join(ч for ч in (f"Ссылка: {блок['url']}", текст) if ч)
		if блок.get("file"):
			текст = "\n\n".join(
				ч for ч in (f"Файл: {блок['file']['name']}", блок.get("preview") or "", текст) if ч
			)
		части.append(текст or ПУСТОЙ_БЛОК)
	return "\n\n".join(части) + "\n"


@frappe.whitelist()
def download(course: str, artifact: str):
	"""Отдаёт документ файлом markdown. Права те же, что у чтения методом."""
	пользователь = текущий_пользователь()
	student._требовать_доступ_к_курсу(пользователь, course)
	документ = student._артефакт_целиком(пользователь, course, artifact)
	frappe.response["filename"] = f"{документ['artifact']}.md"
	frappe.response["filecontent"] = собрать_markdown(документ)
	frappe.response["type"] = "download"


def get_context(context):
	context.no_breadcrumbs = True
	шапка_платформы(context)
	context.title = "Мои документы"
	context.update(
		сведения(frappe.session.user, frappe.form_dict.get("course"), frappe.form_dict.get("artifact"))
	)
	if not context.is_guest:
		# Запись блока идёт с этой же страницы вызовом whitelisted-метода, а
		# POST без токена Frappe отклоняет.
		context.csrf_token = frappe.sessions.get_csrf_token()
	return context
