import frappe

from lms.lms.utils import get_lms_route


def execute():
	"""
	Client sites: make pending (never logged in) non-System users land on the LMS
	after they set their password from the welcome mail, and make sure the LMS
	welcome template is the one Frappe sends.
	"""
	if frappe.db.exists("Email Template", "LMS Welcome Email"):
		frappe.db.set_single_value(
			"System Settings", "welcome_email_template", "LMS Welcome Email"
		)

	users = frappe.get_all(
		"User",
		filters={
			"user_type": ["!=", "System User"],
			"name": ["not in", ["Guest", "Administrator"]],
			"enabled": 1,
			"last_login": ["is", "not set"],
			"redirect_url": ["in", ["", None]],
		},
		pluck="name",
	)

	lms_route = get_lms_route()
	for user in users:
		frappe.db.set_value("User", user, "redirect_url", lms_route, update_modified=False)
