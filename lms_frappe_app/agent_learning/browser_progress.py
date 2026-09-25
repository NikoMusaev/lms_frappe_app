# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Урок закрывает занятие с наставником, а не просмотр страницы.

`Why:` Frappe Learning закрывает урок сам: страница урока через
`lesson_dwell_time` секунд зовёт `save_progress`, и появляется
`LMS Course Progress` со статусом `Complete` — та же запись, по которой агент
выбирает следующий урок, а отчёт руководителя считает пройденное. Ученик,
пролиставший урок в браузере, получал его закрытым без занятия и квиза, и
агент этот урок пропускал (lms-platform#305).

Метод Learning подменяется хуком `override_whitelisted_methods`, а не правкой
форка: правило обязано держаться и против прямого вызова метода своим
токеном, минуя страницу. Отказ, а не тихий успех: на успешный ответ страница
урока ставит зелёную отметку, которая пропадает после перезагрузки.

Чего не делает: не трогает браузерный квиз урока — он закрывает урок другим
методом, `mark_lesson_progress`, — и прогресс SCORM-главы, который идёт этим
же методом с `scorm_details`: занятия с наставником по SCORM-пакету нет.
"""

import frappe
from lms.lms.doctype.course_lesson.course_lesson import save_progress as save_progress_learning

ПОДМЕНЯЕМЫЙ = "lms.lms.doctype.course_lesson.course_lesson.save_progress"
ОТКАЗ = "Урок закрывается на занятии с наставником — в веб-чате или у вашего агента"


@frappe.whitelist()
def save_progress(lesson: str, course: str, scorm_details: dict | None = None):
	"""Прогресс SCORM — как у Learning, всё остальное — отказ."""
	if scorm_details:
		return save_progress_learning(lesson, course, scorm_details)
	frappe.throw(ОТКАЗ, frappe.ValidationError)
