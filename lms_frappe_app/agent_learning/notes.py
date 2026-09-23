# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Замечания автора: адрес места, переходы статуса и чей ход.

Замечание — не содержание курса: его пишет человек в кабинете или агент
куратора, чтобы петля «увидел → агент поправил → принял» не шла через
пересказ в чате. Модуль к базе не ходит: разбор адреса, правила переходов и
очередь проверяются без курса в базе; существование урока или вопроса
проверяет вызывающий.

Статусы: `open` → `done` (агент, с тем, что поменял) → `accepted` (автор) или
назад в `open` с ответом автора. `via` — кто пишет: `author` или `agent`.
Агент ходит в MCP с токеном куратора, и по пользователю его запись от записи
автора не отличить; признак передаёт вызывающий. Это признак для очереди, а не
защита: писать могут только авторские роли.
"""

from lms_frappe_app.agent_learning.doctype.agent_course_artifact.agent_course_artifact import (
	нормализовать_ключ,
)
from lms_frappe_app.agent_learning.errors import Отказ

НЕВЕРНЫЙ_АДРЕС = "invalid_target"
НЕДОПУСТИМЫЙ_ПЕРЕХОД = "invalid_transition"

СТАТУСЫ = ("open", "done", "accepted")
ИСТОЧНИКИ = ("author", "agent")

#: Виды адресов, которым нужен урок; `block` и `map` урок принимают, но не требуют.
С_УРОКОМ = frozenset({"lesson", "material", "directive", "question"})
БЕЗ_УРОКА = frozenset({"course", "course_directive"})

#: Допустимые переходы: (было, стало) → кто вправе и нужен ли текст.
ПЕРЕХОДЫ = {
	("open", "done"): ("agent", True),
	("done", "accepted"): ("author", False),
	("open", "accepted"): ("author", False),
	("done", "open"): ("author", True),
	("accepted", "open"): ("author", True),
}


def разобрать_адрес(
	target: str, lesson: str | None, поля_урока: tuple[str, ...], поля_курса: tuple[str, ...]
) -> dict:
	"""Адрес места замечания: `{kind, key}` — или `Отказ(invalid_target)`.

	Поля директив передаёт вызывающий: их дом — авторинг, а не этот модуль.
	Существование урока, вопроса и принадлежность урока курсу здесь не
	проверяются — это забота вызывающего, у которого есть база.
	"""
	адрес = (target or "").strip()
	вид, _, ключ = адрес.partition(".")
	ключ = ключ.strip()
	if вид in ("course", "lesson", "material") and not ключ and "." not in адрес:
		разобранный = {"kind": вид, "key": None}
	elif вид == "course_directive" and ключ in поля_курса:
		разобранный = {"kind": вид, "key": ключ}
	elif вид == "directive" and ключ in поля_урока:
		разобранный = {"kind": вид, "key": ключ}
	elif вид in ("question", "map") and ключ:
		разобранный = {"kind": вид, "key": ключ}
	elif вид == "block":
		документ, _, блок = ключ.partition("/")
		документ, блок = нормализовать_ключ(документ), нормализовать_ключ(блок)
		if not документ or not блок:
			_отказ_адреса("target", "Блок пишется как block.<документ>/<ключ>")
		разобранный = {"kind": вид, "key": f"{документ}/{блок}"}
	else:
		_отказ_адреса(
			"target",
			"Адрес не распознан: course, course_directive.<поле>, lesson, material, "
			"directive.<поле>, question.<id>, block.<документ>/<ключ>, map.<узел>",
		)
	if разобранный["kind"] in С_УРОКОМ and not lesson:
		_отказ_адреса("lesson", "Этому месту нужен урок")
	if разобранный["kind"] in БЕЗ_УРОКА and lesson:
		_отказ_адреса("lesson", "Это место относится к курсу, а не к уроку")
	return разобранный


def проверить_переход(было: str, стало: str, via: str, текст: str | None) -> None:
	"""Отказ `invalid_transition`, если переход недопустим.

	Агент отмечает «сделано» и пишет, что поменял; принимает и возвращает
	автор, а возвращая — отвечает, что не так.
	"""
	правило = ПЕРЕХОДЫ.get((было, стало))
	if via not in ИСТОЧНИКИ or not правило:
		raise Отказ(НЕДОПУСТИМЫЙ_ПЕРЕХОД, f"Из «{было}» в «{стало}» перейти нельзя", status=было)
	кто, нужен_текст = правило
	if via != кто:
		raise Отказ(
			НЕДОПУСТИМЫЙ_ПЕРЕХОД,
			"Отметить «сделано» может агент" if стало == "done" else "Принять или вернуть может автор",
			status=было,
		)
	if нужен_текст and not (текст or "").strip():
		raise Отказ(
			НЕДОПУСТИМЫЙ_ПЕРЕХОД,
			"Напишите, что поменяли" if стало == "done" else "Напишите, что не так",
			status=было,
		)


def ждёт(статус: str, via: str, ответы: list[dict]) -> str | None:
	"""Чей ход: `author`, `agent` или `None`, если замечание принято.

	«Сделано» ждёт проверки автора. Открытое ждёт того, кто не сказал
	последнего слова: вопрос агента — автора, замечание автора — агента.
	"""
	if статус == "accepted":
		return None
	if статус == "done":
		return "author"
	последний = ответы[-1]["via"] if ответы else via
	return "author" if последний == "agent" else "agent"


def группа(статус: str, ход: str | None) -> str:
	"""Группа очереди кабинета: `check`, `question`, `agent`, `accepted`."""
	if статус == "accepted":
		return "accepted"
	if статус == "done":
		return "check"
	return "question" if ход == "author" else "agent"


def _отказ_адреса(место: str, сообщение: str):
	raise Отказ(НЕВЕРНЫЙ_АДРЕС, сообщение, where=место)
