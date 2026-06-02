"""
Bulk actions on LMS Batches.

Used by the Batches frontend page to archive / un-archive multiple batches
in a single click.
"""

import json

import frappe
from frappe import _


ALLOWED_ROLES = {
	"System Manager",
	"Moderator",
	"Course Creator",
	"Batch Evaluator",
	"LMS Manager",
}


def _check_permission():
	if frappe.session.user == "Administrator":
		return
	if not (set(frappe.get_roles()) & ALLOWED_ROLES):
		frappe.throw(
			_("You are not permitted to perform this action."),
			frappe.PermissionError,
		)


def _coerce_names(batch_names):
	if isinstance(batch_names, str):
		try:
			parsed = json.loads(batch_names)
		except (ValueError, TypeError):
			parsed = [batch_names]
		return parsed if isinstance(parsed, list) else [parsed]
	if isinstance(batch_names, list):
		return batch_names
	return []


@frappe.whitelist()
def archive_batches(batch_names):
	"""Mark the given LMS Batches as archived (custom_is_archived = 1).

	Args:
		batch_names: list of LMS Batch `name`s (or JSON-encoded string of the same)

	Returns:
		{"archived_count": <n>, "skipped_count": <n>}
	"""
	_check_permission()

	names = _coerce_names(batch_names)
	if not names:
		frappe.throw(_("No batches selected."), frappe.ValidationError)

	archived = 0
	skipped = 0
	for name in names:
		if not frappe.db.exists("LMS Batch", name):
			skipped += 1
			continue
		if frappe.db.get_value("LMS Batch", name, "custom_is_archived"):
			skipped += 1
			continue
		frappe.db.set_value("LMS Batch", name, "custom_is_archived", 1)
		archived += 1

	frappe.db.commit()
	return {"archived_count": archived, "skipped_count": skipped}


@frappe.whitelist()
def unarchive_batches(batch_names):
	"""Mark the given LMS Batches as un-archived (custom_is_archived = 0)."""
	_check_permission()

	names = _coerce_names(batch_names)
	if not names:
		frappe.throw(_("No batches selected."), frappe.ValidationError)

	unarchived = 0
	skipped = 0
	for name in names:
		if not frappe.db.exists("LMS Batch", name):
			skipped += 1
			continue
		if not frappe.db.get_value("LMS Batch", name, "custom_is_archived"):
			skipped += 1
			continue
		frappe.db.set_value("LMS Batch", name, "custom_is_archived", 0)
		unarchived += 1

	frappe.db.commit()
	return {"unarchived_count": unarchived, "skipped_count": skipped}
