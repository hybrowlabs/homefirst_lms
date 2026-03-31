# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _


@frappe.whitelist()
def create_users_for_employees(employee_list):
	"""Create Frappe/ERPNext users for a list of employees who do not yet have one.

	Handles three cases cleanly:
	  1. User created fresh and linked to employee.
	  2. User already existed (e.g. from a partial previous attempt) — linked now.
	  3. Genuine failure (invalid email, permission error, etc.) — friendly message.

	Returns:
	  dict with keys:
	    created  – list of {employee, user, email} for newly created + linked users
	    linked   – list of {employee, user, email} for already-existing users now linked
	    skipped  – list of {employee, reason} for employees correctly skipped
	    failed   – list of {employee, email, error} for unrecoverable failures
	"""
	if isinstance(employee_list, str):
		employee_list = json.loads(employee_list)

	if not employee_list:
		frappe.throw(_("No employees selected."))

	allowed_roles = {"System Manager", "Moderator", "HR Manager"}
	if not allowed_roles & set(frappe.get_roles(frappe.session.user)):
		frappe.throw(_("You do not have permission to create users for employees."))

	# Resolve the ERPNext create_user function from the same Python environment.
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
	linked = []
	skipped = []
	failed = []

	for emp_name in employee_list:
		# Fetch the employee record
		try:
			employee = frappe.get_doc("Employee", emp_name)
		except frappe.DoesNotExistError:
			skipped.append({"employee": emp_name, "reason": "Employee record not found"})
			continue

		# Skip employees who already have a linked user
		if employee.user_id:
			skipped.append(
				{
					"employee": emp_name,
					"reason": f"Already linked to user: {employee.user_id}",
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
					"reason": "No email address on employee record. Set company email or personal email first.",
				}
			)
			continue

		# --- Attempt user creation ---
		try:
			erpnext_create_user(employee=emp_name, email=email)

			# Re-fetch to confirm user_id was set by ERPNext's create_user
			updated_user_id = frappe.db.get_value("Employee", emp_name, "user_id") or email

			# Ensure employee.user_id is actually persisted
			if not frappe.db.get_value("Employee", emp_name, "user_id"):
				frappe.db.set_value("Employee", emp_name, "user_id", email)
				frappe.db.commit()

			_send_welcome_email_safe(email)
			created.append({"employee": emp_name, "user": updated_user_id, "email": email})

		except Exception as exc:
			# --- Recovery: check if user was actually created despite the exception ---
			# This handles the common case where user insertion succeeded but a
			# post-insert step (e.g. welcome email to a restricted domain) raised
			# an error, leaving employee.user_id unlinked on the first attempt.
			existing_user = frappe.db.get_value("User", {"email": email}, "name")
			if existing_user:
				# User exists — link the employee now and report as "linked"
				if not frappe.db.get_value("Employee", emp_name, "user_id"):
					frappe.db.set_value("Employee", emp_name, "user_id", existing_user)
					frappe.db.commit()
				_send_welcome_email_safe(email)
				linked.append({"employee": emp_name, "user": existing_user, "email": email})
			else:
				# Genuine failure — surface a friendly message, log technical detail
				raw = str(exc)
				frappe.log_error(
					f"Failed to create user for employee {emp_name} ({email}): {raw}",
					"LMS Create Employee User",
				)
				failed.append(
					{
						"employee": emp_name,
						"email": email,
						"error": _get_friendly_error(raw),
					}
				)

	return {"created": created, "linked": linked, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _send_welcome_email_safe(email):
	"""Send welcome / account-setup email to the given user.

	Uses Frappe's built-in reset_password flow so the user receives a
	secure link to complete their registration. Failures are logged only —
	the user record and employee link are never rolled back because of an
	email problem.
	"""
	try:
		user_doc = frappe.get_doc("User", email)
		# Only send if not already sent during creation
		if not user_doc.flags.email_sent:
			user_doc.send_welcome_mail_to_user()
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"LMS: Failed to send welcome email to {email}",
		)


def _get_friendly_error(raw_error):
	"""Convert a raw exception string to a business-friendly message."""
	low = raw_error.lower()
	if "blocked" in low or "invalid email" in low:
		return (
			"Email is blocked or not allowed for user creation. "
			"Please check the email address or contact your system administrator."
		)
	if "duplicate" in low or "already exists" in low:
		return "A user with this email already exists."
	if "permission" in low:
		return "Insufficient permissions to create this user. Contact your system administrator."
	# Generic fallback — keep technical details out of UI, they're in the log
	return "User could not be created. Please check the server error log for details."
