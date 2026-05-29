"""
Backfill custom_employee, custom_branch, custom_region, custom_reports_to,
custom_manager_email_id, and custom_batch on existing LMS Quiz Submission
and LMS Assignment Submission records.

These fields are auto-populated on insert (via before_insert) for new
submissions, but pre-existing submissions created before this feature was
added have these fields empty. This patch fills them in.

Idempotent: skips records where custom_employee is already set, so it can
be re-run safely without duplicating work.
"""

import frappe

from lms.lms.utils import autofill_member_context

CUSTOM_FIELDS = [
	"custom_employee",
	"custom_branch",
	"custom_region",
	"custom_reports_to",
	"custom_manager_email_id",
	"custom_batch",
]


def execute():
	for doctype in ("LMS Quiz Submission", "LMS Assignment Submission"):
		if not frappe.db.exists("DocType", doctype):
			continue

		meta = frappe.get_meta(doctype)
		if not meta.has_field("custom_employee"):
			# Doctype doesn't have the custom fields yet — nothing to do.
			continue

		_backfill_doctype(doctype)

	frappe.db.commit()


def _backfill_doctype(doctype):
	# Process only rows where custom_employee is empty — already-filled rows
	# (e.g. from new submissions after the feature went live) are skipped.
	names = frappe.get_all(
		doctype,
		filters={"custom_employee": ["in", ["", None]]},
		pluck="name",
	)

	if not names:
		print(f"  {doctype}: nothing to backfill")
		return

	print(f"  {doctype}: backfilling {len(names)} records...")

	updated = 0
	for name in names:
		try:
			doc = frappe.get_doc(doctype, name)
			autofill_member_context(doc)

			# Collect only the fields we actually populated
			updates = {}
			for f in CUSTOM_FIELDS:
				value = doc.get(f)
				if value:
					updates[f] = value

			if updates:
				# Direct DB write — avoid triggering validate/notify hooks on
				# already-committed historical submissions.
				frappe.db.set_value(
					doctype, name, updates, update_modified=False
				)
				updated += 1
		except Exception:
			frappe.log_error(
				title=f"backfill_submission_member_context: {doctype} {name}",
				message=frappe.get_traceback(),
			)

	print(f"  {doctype}: {updated} records updated")
