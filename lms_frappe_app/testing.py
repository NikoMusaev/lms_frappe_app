# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Подготовка процесса к прогону тестов (`before_tests` в hooks)."""


def before_tests() -> None:
	"""Выключает индексацию поиска Frappe Learning на время тестов.

	`Why:` каждая вставка урока или курса переиндексирует SQLite-индекс
	Learning (`update_doc_index`), а открытие и закрытие файла индекса на
	томе Docker Desktop стоит по 25 мс — в профиле модуля из девяти тестов
	на индекс уходило 9 с из 14. В CI индекса нет вовсе: его строит воркер
	очереди, которого там не запускают, и `update_doc_index` выходит сразу.
	Локальный прогон уравнивается с CI в процессе, а не на диске: файл
	индекса и поиск на стенде не трогаются (lms-platform#126).
	"""
	from lms.sqlite import LearningSearch

	LearningSearch.is_search_enabled = lambda self: False
