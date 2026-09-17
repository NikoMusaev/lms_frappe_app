// Copyright (c) 2026, NikoMusaev and contributors
// For license information, please see license.txt

// Список репортов — очередь разбора, и разбирают её сверху вниз по цвету:
// неразобранное видно, не вчитываясь в строки. Клик по индикатору оставляет
// в списке репорты того же статуса.
frappe.listview_settings["Agent Course Report"] = {
	add_fields: ["status"],
	get_indicator: (док) => {
		const цвета = {
			New: "red",
			"In Progress": "orange",
			Fixed: "green",
			Rejected: "gray",
			Duplicate: "gray",
		};
		return [__(док.status), цвета[док.status] || "gray", "status,=," + док.status];
	},
};
