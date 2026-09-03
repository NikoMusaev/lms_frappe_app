app_name = "lms_frappe_app"
app_title = "Agent Learning"
app_publisher = "NikoMusaev"
app_description = "Директивы, сессии и серверный квиз для обучения через MCP-агента"
app_email = "hightimeconsult@gmail.com"
app_license = "agpl-3.0"

# Apps
# ------------------

# Приложение опирается на доменную модель Frappe Learning: директива ссылается
# на Course Lesson, сверка ответа — на LMS Question, итоги пишутся в
# LMS Course Progress и LMS Quiz Submission.
required_apps = ["frappe/lms"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "lms_frappe_app",
# 		"logo": "/assets/lms_frappe_app/logo.png",
# 		"title": "Agent Learning",
# 		"route": "/lms_frappe_app",
# 		"has_permission": "lms_frappe_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/lms_frappe_app/css/lms_frappe_app.css"
# app_include_js = "/assets/lms_frappe_app/js/lms_frappe_app.js"

# include js, css files in header of web template
# web_include_css = "/assets/lms_frappe_app/css/lms_frappe_app.css"
# web_include_js = "/assets/lms_frappe_app/js/lms_frappe_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "lms_frappe_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "lms_frappe_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "lms_frappe_app.utils.jinja_methods",
# 	"filters": "lms_frappe_app.utils.jinja_filters"
# }

# Права
# ------------------
# Изоляция занятий держится на правах Frappe, а не на проверках в вызывающем
# коде: и браузер, и MCP-сервис ходят от имени ученика, поэтому чужое занятие
# отклоняется одинаково в обоих каналах, без дублирования логики.

_сессия = "lms_frappe_app.agent_learning.doctype.agent_learning_session.agent_learning_session"
_права = "lms_frappe_app.agent_learning.permissions"

permission_query_conditions = {
	"Agent Learning Session": f"{_права}.условие_занятия",
	"Agent Session Event": f"{_права}.условие_события",
	"Agent Quiz Attempt": f"{_права}.условие_попытки",
	"Agent Quiz Answer": f"{_права}.условие_ответа",
	"Organization Membership": f"{_права}.условие_членства",
	"Course Allocation": f"{_права}.условие_назначения",
}

has_permission = {
	"Agent Learning Session": f"{_права}.доступно_занятие",
	"Agent Session Event": f"{_права}.доступно_событие",
	"Agent Quiz Attempt": f"{_права}.доступна_попытка",
	"Agent Quiz Answer": f"{_права}.доступен_ответ",
	"Organization Membership": f"{_права}.доступно_членство",
	"Course Allocation": f"{_права}.доступно_назначение",
}

# Роли ставятся вместе с приложением: без них права на DocType ссылались бы
# на несуществующие роли, и Frappe молча отдал бы доступ никому.
fixtures = [
	{
		"dt": "Role",
		"filters": [
			["name", "in", ["Organization Manager", "Organization Admin", "Agent Service"]]
		],
	}
]

# Фоновые задачи
# ------------------
# Раз в час: занятия, брошенные посреди урока, закрываются сами. Иначе ученик,
# закрывший ноутбук, навсегда остаётся «в процессе» и портит отчётность.

_назначение = "lms_frappe_app.agent_learning.doctype.course_allocation.course_allocation"

scheduler_events = {
	"hourly": [f"{_сессия}.закрыть_брошенные_занятия"],
	# Страховка к хуку на вступление: членство может появиться в обход него —
	# импортом, миграцией или правкой в базе.
	"daily": [f"{_назначение}.сверить_зачисления"],
}

# Installation
# ------------

# before_install = "lms_frappe_app.install.before_install"
# after_install = "lms_frappe_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "lms_frappe_app.uninstall.before_uninstall"
# after_uninstall = "lms_frappe_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "lms_frappe_app.utils.before_app_install"
# after_app_install = "lms_frappe_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "lms_frappe_app.utils.before_app_uninstall"
# after_app_uninstall = "lms_frappe_app.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "lms_frappe_app.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "lms_frappe_app.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["lms_frappe_app.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"lms_frappe_app.tasks.all"
# 	],
# 	"daily": [
# 		"lms_frappe_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"lms_frappe_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"lms_frappe_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"lms_frappe_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "lms_frappe_app.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "lms_frappe_app.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "lms_frappe_app.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "lms_frappe_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["lms_frappe_app.utils.before_request"]
# after_request = ["lms_frappe_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["lms_frappe_app.utils.before_job"]
# after_job = ["lms_frappe_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"lms_frappe_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

