# Copyright (c) 2026, NikoMusaev and Contributors
# See license.txt
"""Роли платформы OAuth-клиентам, созданным до хука (#26)."""

from lms_frappe_app.agent_learning.oauth_client import добить_роли_существующим


def execute():
	добить_роли_существующим()
