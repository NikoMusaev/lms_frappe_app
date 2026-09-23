# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentAuthorVisit(Document):
	"""Визит автора в урок кабинета: снимок мест урока, каким автор его видел.

	По нему кабинет отмечает «изменено с вашего прошлого визита» (lms-high-time/
	learning-services#271). Одна запись на пару «автор + урок»; пишет её только
	`mark_lesson_seen` страницы кабинета. Не содержание курса: удалению урока
	не мешает (`ignore_links_on_delete` в hooks).
	"""
