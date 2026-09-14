# Copyright (c) 2026, NikoMusaev and contributors
# For license information, please see license.txt

"""Логотип приложения для desk — методом, а не статикой.

`Why:` код приложения на стенде обновляется через том (пуш в ветку deploy),
а ссылка `sites/assets/<app>` заводится только при сборке образа: файлы из
`public/` до стенда не доезжают, и `/assets/lms_frappe_app/...` отвечал 404.
Поле `logo_url` у плитки стартового экрана — `Data`, data-URI в него не
влезает. Метод отдаёт SVG с правильным типом, а файл остаётся источником
правды (проверено 14 сентября 2026).
"""

from pathlib import Path

import frappe
from werkzeug.wrappers import Response

ФАЙЛ = Path(__file__).resolve().parent.parent / "public" / "images" / "agent-learning.svg"
АДРЕС = "/api/method/lms_frappe_app.agent_learning.branding.logo"


@frappe.whitelist(allow_guest=True, methods=["GET"])
def logo() -> Response:
	"""SVG логотипа. Готовый Response Frappe отдаёт как есть, без обёртки JSON."""
	ответ = Response(ФАЙЛ.read_bytes(), mimetype="image/svg+xml")
	ответ.headers["Cache-Control"] = "public, max-age=86400"
	return ответ
