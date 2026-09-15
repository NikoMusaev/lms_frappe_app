# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentChatState(Document):
	"""Состояние разговора веб-чата — одна запись на занятие.

	Чистое хранение: формат пишет и разбирает MCP-сервис. Истории изменений
	нет намеренно — каждое сохранение замещает блоб целиком, и версии копили
	бы копии всей переписки.
	"""
