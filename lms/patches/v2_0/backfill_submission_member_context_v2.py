"""
Re-run of backfill_submission_member_context.

The original patch in this folder ran successfully for LMS Quiz Submission
on production, but silently skipped LMS Assignment Submission because the
custom_employee field did not exist on that doctype at patch time — the
field arrived later in the same migrate via the Custom Field fixtures.

This patch reuses the same logic. By the time it runs (on the next deploy
after the fixtures have been installed), the field exists on Assignment
Submission too, so historical submissions there get backfilled.

Idempotent: skips rows where custom_employee is already populated, so
re-running on Quiz Submission is a no-op.
"""

from lms.patches.v2_0.backfill_submission_member_context import execute as _execute


def execute():
	_execute()
