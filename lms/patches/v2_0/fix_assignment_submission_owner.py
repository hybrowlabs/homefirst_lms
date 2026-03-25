"""
Fix legacy LMS Assignment Submission records whose ``owner`` field does not
match the ``member`` field.

Root cause
----------
The ``LMS Student`` role has ``if_owner = 1`` in the
``LMS Assignment Submission`` DocType permissions.  Frappe grants read/write
to a student only when ``owner == frappe.session.user``.

Old submissions created before the M6 fix were inserted under an
Administrator session (either during manual testing or via a server-side code
path that ran as Administrator), so they carry ``owner = "Administrator"``
while ``member = <student_email>``.  When the student later tries to open the
submission via ``frappe.client.get`` the ``if_owner`` check fails and raises
``frappe.PermissionError``.

New submissions created via ``frappe.client.insert`` from the student's
browser session correctly get ``owner = session.user``, so no migration is
needed for them.

What this patch does
--------------------
For every ``LMS Assignment Submission`` where ``owner != member``, set
``owner = member``.  This is safe because:

* The correct semantic is that the submitting student owns their submission.
* Evaluators/moderators already have explicit (non-if_owner) read + write
  access, so their access is not affected by the ``owner`` field.
* The read-only-after-grading logic lives in ``validate_grade_access()`` on
  the Python controller and is unchanged by this patch.
"""

import frappe


def execute():
	# frappe.db.get_all doesn't support cross-field comparisons, so use SQL.
	bad_records = frappe.db.sql(
		"""
		SELECT name, member, owner
		FROM `tabLMS Assignment Submission`
		WHERE owner != member
		  AND member IS NOT NULL
		  AND member != ''
		""",
		as_dict=True,
	)

	if not bad_records:
		return

	updated = 0
	for row in bad_records:
		frappe.db.set_value(
			"LMS Assignment Submission",
			row["name"],
			"owner",
			row["member"],
			update_modified=False,  # preserve original modified timestamp
		)
		updated += 1

	frappe.db.commit()
	frappe.logger().info(
		f"fix_assignment_submission_owner: updated owner on {updated} record(s)"
	)
