# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _


@frappe.whitelist()
def create_users_for_employees(employee_list):
	"""Create LMS Website Users for a list of employees who do not yet have one.

	Creates the User directly (not via ERPNext's create_user) so we can:
	  - guarantee send_welcome_email = 0 (no duplicate welcome mail)
	  - set user_type = "Website User" from the start (LMS-only access)
	  - avoid Employee.save() which would add the Employee role back

	Handles three cases cleanly:
	  1. User created fresh and linked to employee.
	  2. User already existed — linked now, roles corrected.
	  3. Genuine failure (invalid email, permission error, etc.) — friendly message.

	Returns:
	  dict with keys:
	    created  – list of {employee, user, email, email_note}
	    linked   – list of {employee, user, email, email_note}
	    skipped  – list of {employee, reason}
	    failed   – list of {employee, email, error}
	"""
	if isinstance(employee_list, str):
		employee_list = json.loads(employee_list)

	if not employee_list:
		frappe.throw(_("No employees selected."))

	allowed_roles = {"System Manager", "Moderator", "HR Manager"}
	if not allowed_roles & set(frappe.get_roles(frappe.session.user)):
		frappe.throw(_("You do not have permission to create users for employees."))

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
			_create_lms_user_doc(employee, email)

			# Link employee → user directly (no emp.save() which would add Employee role)
			frappe.db.set_value("Employee", emp_name, "user_id", email)
			frappe.db.commit()

			# Send exactly one welcome email
			email_note = _send_welcome_email_safe(email)
			created.append(
				{"employee": emp_name, "user": email, "email": email, "email_note": email_note}
			)

		except Exception as exc:
			# --- Recovery: check if user was actually created despite the exception ---
			# This handles the case where user insertion succeeded but a post-insert
			# step (e.g. email to a restricted domain) raised an error.
			existing_user = frappe.db.get_value("User", {"email": email}, "name")
			if existing_user:
				# User exists — fix their roles/type, link the employee, report as "linked"
				if not frappe.db.get_value("Employee", emp_name, "user_id"):
					frappe.db.set_value("Employee", emp_name, "user_id", existing_user)
					frappe.db.commit()
				_make_lms_website_user(existing_user)
				email_note = _send_welcome_email_safe(existing_user)
				linked.append(
					{
						"employee": emp_name,
						"user": existing_user,
						"email": email,
						"email_note": email_note,
					}
				)
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


def _create_lms_user_doc(employee, email):
	"""Create a Frappe User for LMS access from an Employee record.

	- user_type is set to "Website User" (no Desk access)
	- send_welcome_email = 0 + flags.no_welcome_mail = True prevents any
	  automatic welcome email from Frappe/ERPNext; caller sends one explicitly
	- The LMS after_insert hook (lms.lms.user.after_insert) adds the
	  "LMS Student" role automatically
	- Employee is linked via frappe.db.set_value (not emp.save()) so that
	  ERPNext's update_user() is never triggered (which would add the Employee
	  role back and change user_type to "System User")
	"""
	name_parts = (employee.employee_name or "").split()
	first_name = name_parts[0] if name_parts else email.split("@")[0]
	last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

	user = frappe.new_doc("User")
	user.email = email
	user.first_name = first_name
	user.last_name = last_name
	user.enabled = 1
	user.user_type = "Website User"  # set before insert so check_roles_added() in
	# validate() sees user_type != "System User" and skips the "No Roles Specified" popup
	user.send_welcome_email = 0  # never auto-send — caller decides
	user.flags.no_welcome_mail = True  # belt-and-suspenders for Frappe's own check
	user.flags.ignore_permissions = True
	user.insert()
	# NOTE: LMS after_insert hook fires here → adds "LMS Student" role → user.save()
	# That save has in_insert=True but send_welcome_email=0, so no email is sent.


def _make_lms_website_user(user_name):
	"""Correct an existing user's type and roles for LMS-only access.

	Called for the recovery path (user already existed before this run).
	Removes Desk-access roles (Employee, Employee Self Service) that ERPNext
	may have added, keeps/adds LMS Student, and lets Frappe recalculate
	user_type as "Website User" automatically.
	"""
	DESK_ROLES_TO_REMOVE = {"Employee", "Employee Self Service"}

	try:
		user = frappe.get_doc("User", user_name)
		user.flags.ignore_permissions = True
		user.flags.no_welcome_mail = True

		# Remove Desk-access roles that do not belong on an LMS intern
		user.roles = [r for r in user.roles if r.role not in DESK_ROLES_TO_REMOVE]

		# Ensure LMS Student role is present
		existing_roles = {r.role for r in user.roles}
		if "LMS Student" not in existing_roles:
			user.append("roles", {"role": "LMS Student"})

		# Frappe's validate → set_system_user() will see no desk_access=1 roles
		# and automatically set user_type = "Website User"
		user.save()
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"LMS: Could not convert {user_name} to Website User",
		)


def _send_welcome_email_safe(email):
	"""Send welcome / account-setup email to the given user.

	Uses Frappe's built-in send_welcome_mail_to_user so the user receives a
	secure link to set their password. Failures are logged only — the user
	record and employee link are never rolled back because of an email problem.

	Returns an empty string on success, or a short warning string when the
	email could not be sent (to surface inline in the UI result dialog).
	Calls frappe.clear_last_message() so that a blocked-email frappe.throw()
	does not pollute _server_messages with a raw red popup.
	"""
	try:
		user_doc = frappe.get_doc("User", email)
		user_doc.send_welcome_mail_to_user()
		return ""
	except Exception:
		frappe.clear_last_message()
		frappe.log_error(
			frappe.get_traceback(),
			f"LMS: Welcome email blocked for {email}",
		)
		return "Welcome email could not be sent."


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
	return "User could not be created. Please check the server error log for details."
