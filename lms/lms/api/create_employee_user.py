# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _


@frappe.whitelist()
def create_users_for_employees(employee_list):
	"""Create Frappe/ERPNext users for a list of employees who do not yet have one.

	Calls erpnext.setup.doctype.employee.employee.create_user directly as a
	Python function (same bench, no HTTP credentials required).

	Args:
		employee_list: JSON-encoded list of employee names (e.g. ["HR-EMP-00023", ...])

	Returns:
		dict with keys:
		  created  – list of {employee, user, email} for successfully created users
		  skipped  – list of {employee, reason} for employees that were skipped
		  failed   – list of {employee, email, error} for employees where creation failed
	"""
	if isinstance(employee_list, str):
		employee_list = json.loads(employee_list)

	if not employee_list:
		frappe.throw(_("No employees selected."))

	allowed_roles = {"System Manager", "Moderator", "HR Manager"}
	if not allowed_roles & set(frappe.get_roles(frappe.session.user)):
		frappe.throw(_("You do not have permission to create users for employees."))

	# Resolve the ERPNext create_user function from the same Python environment.
	# This works because ERPNext and LMS are installed in the same bench —
	# no HTTP call or API credentials are needed.
	try:
		erpnext_create_user = frappe.get_attr(
			"erpnext.setup.doctype.employee.employee.create_user"
		)
	except (ImportError, AttributeError):
		frappe.throw(
			_(
				"ERPNext is not installed in this bench. "
				"The create_user function could not be found."
			)
		)

	created = []
	skipped = []
	failed = []

	for emp_name in employee_list:
		# Fetch the employee record
		try:
			employee = frappe.get_doc("Employee", emp_name)
		except frappe.DoesNotExistError:
			skipped.append({"employee": emp_name, "reason": "Employee not found"})
			continue

		# Skip employees who already have a linked user
		if employee.user_id:
			skipped.append(
				{
					"employee": emp_name,
					"reason": f"User already exists: {employee.user_id}",
				}
			)
			continue

		# Resolve email: prefer company_email, fall back to personal_email
		email = (
			getattr(employee, "company_email", None)
			or getattr(employee, "personal_email", None)
			or ""
		).strip()

		if not email:
			skipped.append(
				{
					"employee": emp_name,
					"reason": "No email on employee record (set company_email or personal_email first)",
				}
			)
			continue

		# Call ERPNext's create_user directly in the same Python process
		try:
			erpnext_create_user(employee=emp_name, email=email)
			# Re-fetch to confirm user_id was linked
			updated_user_id = frappe.db.get_value("Employee", emp_name, "user_id") or email
			created.append({"employee": emp_name, "user": updated_user_id, "email": email})
		except frappe.exceptions.DuplicateEntryError:
			skipped.append(
				{"employee": emp_name, "reason": f"User with email {email} already exists"}
			)
		except Exception:
			failed.append(
				{
					"employee": emp_name,
					"email": email,
					"error": frappe.get_traceback(with_context=False).strip().splitlines()[-1],
				}
			)

	return {"created": created, "skipped": skipped, "failed": failed}
