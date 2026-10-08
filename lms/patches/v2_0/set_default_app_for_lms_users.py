import frappe


def execute():
	"""LMS-only (non-System) users should open the LMS on every login, not the /apps launcher."""
	users = frappe.get_all(
		"User",
		filters={
			"user_type": ["!=", "System User"],
			"name": ["not in", ["Guest", "Administrator"]],
			"enabled": 1,
			"default_app": ["in", ["", None]],
		},
		pluck="name",
	)
	lms_users = set(
		frappe.get_all(
			"Has Role",
			filters={
				"parenttype": "User",
				"role": ["in", ["Moderator", "Course Creator", "Batch Evaluator", "LMS Student"]],
			},
			pluck="parent",
		)
	)
	for user in users:
		if user in lms_users:
			frappe.db.set_value("User", user, "default_app", "lms", update_modified=False)
