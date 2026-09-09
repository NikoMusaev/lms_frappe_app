# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

from lms_frappe_app.agent_learning.directives import ВерсионированнаяДиректива


class AgentLessonDirective(ВерсионированнаяДиректива):
	"""Инструкция преподавателю по конкретному уроку.

	Не контент для ученика: тексты отсюда адресованы агенту, который ведёт
	занятие. Ученику директива не показывается, и роль `LMS Student` не имеет
	к этому DocType никаких прав.

	Директивы переписываются чаще самих уроков, поэтому у урока может быть
	несколько версий — действующей считается ровно одна.
	"""

	ПОЛЯ_ВЛАДЕЛЬЦА = ("lesson",)
