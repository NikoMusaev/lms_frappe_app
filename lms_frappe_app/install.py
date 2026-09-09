# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Настройка при установке и миграции."""

import frappe

#: Web Page — обязательное поле пункта, а `route` и `title` пункт берёт из неё
#: (`fetch_from`). Заглушка не публикуется: сама страница живёт в коде по
#: адресу /agent, а с /agent-sidebar на неё ведёт `website_redirects` в hooks.
ЗАГЛУШКА = {"title": "Подключить агента", "route": "agent-sidebar"}
ИКОНКА = "bot"


def обеспечить_пункт_сайдбара() -> None:
	"""Пункт «Подключить агента» в сайдбаре Frappe Learning.

	Сайдбар читает дочернюю таблицу `LMS Settings.sidebar_items` и ведёт по
	`route` обычной ссылкой. Идемпотентно: вызывается и при установке, и при
	каждой миграции.
	"""
	заглушка = _заглушка()
	фильтры = {
		"parenttype": "LMS Settings",
		"parentfield": "sidebar_items",
		"parent": "LMS Settings",
		"web_page": заглушка,
	}
	if frappe.db.exists("LMS Sidebar Item", фильтры):
		return
	настройки = frappe.get_single("LMS Settings")
	настройки.append("sidebar_items", {"web_page": заглушка, "icon": ИКОНКА})
	настройки.save(ignore_permissions=True)


def _заглушка() -> str:
	имя = frappe.db.get_value("Web Page", {"route": ЗАГЛУШКА["route"]})
	if имя:
		return имя
	return (
		frappe.get_doc(
			{
				"doctype": "Web Page",
				"published": 0,
				"content_type": "Rich Text",
				"main_section": "<p>Страница живёт в приложении: /agent.</p>",
				**ЗАГЛУШКА,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def обеспечить_индекс_заметок() -> None:
	"""Уникальность ключа заметки на уровне базы.

	`Why:` замещение по ключу — договор всей затеи. Проверка в Python держит
	его, пока запись идёт из одного места; индекс держит всегда, включая
	правку из админки и гонку двух вызовов агента. Пустой курс у фактов
	хранится строкой, а не NULL: NULL-ы MariaDB считает различными, и дубли
	прошли бы мимо индекса.
	"""
	frappe.db.sql_ddl(
		"""
		CREATE UNIQUE INDEX IF NOT EXISTS `agent_student_note_key`
		ON `tabAgent Student Note` (`student`, `course`, `note_key`)
		"""
	)


#: Ключи Google живут в конфигурации сайта, а не в коде: значения секретны, а
#: запись провайдера — данные, которые обязаны пережить пересоздание сайта.
КЛЮЧ_ID = "google_login_client_id"
КЛЮЧ_СЕКРЕТ = "google_login_client_secret"


def обеспечить_вход_через_google() -> None:
	"""Ключ входа через Google из конфигурации сайта.

	`Why:` запись `Social Login Key`, заведённая кликами в админке, живёт до
	пересоздания сайта. Стенд поднимается `create-site`, и такая настройка
	нигде не записана — после переезда или восстановления из бэкапа вход
	исчезает молча, а замечает это первый ученик, который не смог войти.

	Ключей в конфиге нет — не делаем ничего: локальная разработка не обязана
	держать секреты Google, а пустая запись сломала бы кнопку на `/login`.
	"""
	client_id = frappe.conf.get(КЛЮЧ_ID)
	client_secret = frappe.conf.get(КЛЮЧ_СЕКРЕТ)
	if not client_id or not client_secret:
		return

	существует = frappe.db.exists("Social Login Key", "google")
	ключ = (
		frappe.get_doc("Social Login Key", "google")
		if существует
		else frappe.new_doc("Social Login Key")
	)
	if not существует:
		# Адреса, скоупы и иконку задаёт сам Frappe: свои копии разъехались бы
		# с ним при первом же обновлении. Метод объявлен пригодным именно для
		# создания ключа из контроллера.
		ключ.get_social_login_provider("Google", initialize=True)

	if not _расходится(ключ, client_id, client_secret):
		return

	ключ.update(
		{
			"social_login_provider": "Google",
			"client_id": client_id,
			"client_secret": client_secret,
			"enable_social_login": 1,
			# Пускаем всех: платформа открыта, ограничение по доменам
			# организаций сознательно не вводится.
			"sign_ups": "Allow",
		}
	)
	ключ.save(ignore_permissions=True)


def _расходится(ключ, client_id: str, client_secret: str) -> bool:
	"""Отличается ли запись от конфигурации.

	`Why:` `after_migrate` зовётся на каждый старт контейнера, и безусловное
	сохранение писало бы новую версию документа на ровном месте.
	"""
	from frappe.utils.password import get_decrypted_password

	if ключ.is_new():
		return True
	if ключ.client_id != client_id or not ключ.enable_social_login:
		return True
	if ключ.sign_ups != "Allow":
		return True
	прежний = get_decrypted_password(
		"Social Login Key", "google", "client_secret", raise_exception=False
	)
	return прежний != client_secret


#: Язык платформы. Переводы есть и во Frappe, и в `frappe/lms`; запись
#: `Language` для него создаётся `sync_languages` при каждой миграции.
ЯЗЫК = "ru"


def обеспечить_язык_платформы() -> None:
	"""Ставит русский языком сайта, если язык ещё не выбран.

	`Why:` интерфейс LMS — отдельное приложение и своего переключателя языка
	не показывает: он спрашивает язык у сервера один раз (`User.language`, а
	для гостя `System Settings.language`). Настройка живёт в базе и не
	переживает пересоздания сайта — как ключ входа через Google.

	Выбранный язык не трогаем: `after_migrate` зовётся на каждый старт
	контейнера, и настойчивость откатывала бы решение администратора при
	каждой выкатке.
	"""
	if frappe.db.get_single_value("System Settings", "language"):
		return
	настройки = frappe.get_single("System Settings")
	настройки.language = ЯЗЫК
	настройки.save(ignore_permissions=True)


def after_install() -> None:
	обеспечить_пункт_сайдбара()
	обеспечить_индекс_заметок()
	обеспечить_вход_через_google()
	обеспечить_язык_платформы()


def after_migrate() -> None:
	обеспечить_пункт_сайдбара()
	обеспечить_индекс_заметок()
	обеспечить_вход_через_google()
	обеспечить_язык_платформы()
