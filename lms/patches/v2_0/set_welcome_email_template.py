import frappe


def execute():
	frappe.db.set_single_value(
		"System Settings", "welcome_email_template", "LMS Welcome Email"
	)
