"""
API endpoints for LMS submission data.

Primary consumer: external LLM-evaluation pipeline.
Flow:
  1. UI lets a reviewer pick a Batch + a Quiz.
  2. UI calls `get_submissions_for_evaluation(batch, quiz)`.
  3. This API returns one entry per submission with:
       - the employee context (employee, branch, manager, region, etc.)
       - the submission metadata (score, percentage, dates)
       - the per-question answers (question text + student's answer)
  4. The UI ships that JSON to an LLM, which scores the open-ended answers.

Access is restricted to roles authorised to view answer content (see
ALLOWED_ROLES below).
"""

import frappe
from frappe import _

# Roles that may invoke the LLM-evaluation endpoints. Adjust this list to
# match the org's actual reviewer/LLM-Evaluator role naming. Administrator
# always passes.
ALLOWED_ROLES = {
	"System Manager",
	"Moderator",
	"Course Creator",
	"Batch Evaluator",
	"LMS Manager",
}


def _check_permission():
	"""Raise PermissionError unless the caller holds an evaluator role."""
	if frappe.session.user == "Administrator":
		return
	user_roles = set(frappe.get_roles(frappe.session.user))
	if not (user_roles & ALLOWED_ROLES):
		frappe.throw(
			_("You are not permitted to access submission evaluation data."),
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_submissions_for_evaluation(batch=None, quiz=None):
	"""
	Return all LMS Quiz Submissions for a (batch, quiz) pair, with employee
	context and per-question answers — ready for LLM scoring.

	Args:
		batch:  LMS Batch name (required)
		quiz:   LMS Quiz name (required)

	Returns:
		{
		  "batch": "<batch>",
		  "quiz": "<quiz>",
		  "quiz_title": "<title>",
		  "passing_percentage": <int>,
		  "count": <n>,
		  "submissions": [
		    {
		      "submission_id": "...",
		      "creation": "...",
		      "employee": { name, employee_name, user_id, branch,
		                    region, reports_to, manager_email_id,
		                    designation, department },
		      "submission": { score, score_out_of, percentage,
		                      passing_percentage, member_name },
		      "answers": [
		        {
		          "question_id": "...",
		          "question_text": "...",
		          "question_type": "Open Ended|Choices|User Input",
		          "marks_out_of": <int>,
		          "student_answer": "...",
		          "current_marks": <int>,
		          "current_is_correct": 0|1
		        },
		        ...
		      ]
		    },
		    ...
		  ]
		}
	"""
	_check_permission()

	if not batch or not quiz:
		frappe.throw(
			_("Both 'batch' and 'quiz' are required."),
			frappe.ValidationError,
		)

	# Resolve `batch` and `quiz` — accept either the doctype `name`
	# (slug, e.g. "batch-04-doj-04-may-2026-2") or the human `title`
	# (e.g. "Batch 04 | DOJ: 04 May 2026"). If a title is passed and it
	# is ambiguous (multiple batches share the same title), we throw so
	# the caller can pick the exact name.
	batch = _resolve_by_name_or_title("LMS Batch", batch)
	quiz = _resolve_by_name_or_title("LMS Quiz", quiz)

	# Pull quiz metadata once
	quiz_doc = frappe.db.get_value(
		"LMS Quiz",
		quiz,
		["title", "passing_percentage", "total_marks"],
		as_dict=True,
	)

	# Get batch members, then filter submissions on (member, quiz, batch).
	#
	# custom_batch is required in the filter because a member can be enrolled
	# in multiple batches. Without it, a submission a member made while in
	# batch A would also surface when querying batch B if the same member is
	# now enrolled in batch B.
	members = frappe.get_all(
		"LMS Batch Enrollment",
		filters={"batch": batch},
		pluck="member",
	)

	submission_names = []
	if members:
		submission_names = frappe.get_all(
			"LMS Quiz Submission",
			filters={
				"quiz": quiz,
				"member": ["in", members],
				"custom_batch": batch,
			},
			pluck="name",
			order_by="creation desc",
		)

	submissions = [_build_submission_payload(name) for name in submission_names]

	return {
		"batch": batch,
		"quiz": quiz,
		"quiz_title": quiz_doc.title if quiz_doc else None,
		"passing_percentage": (quiz_doc and quiz_doc.passing_percentage) or 0,
		"total_marks": (quiz_doc and quiz_doc.total_marks) or 0,
		"count": len(submissions),
		"submissions": submissions,
	}


def _resolve_by_name_or_title(doctype, value):
	"""
	Accept either the doctype `name` (slug) or the human `title` and
	return the resolved `name`. Throws if missing or if a title resolves
	to more than one record.
	"""
	if not value:
		frappe.throw(
			_("{0} value is empty.").format(doctype),
			frappe.ValidationError,
		)

	# Fast path: exact name match
	if frappe.db.exists(doctype, value):
		return value

	# Fall back to title lookup
	matches = frappe.get_all(doctype, filters={"title": value}, pluck="name")
	if not matches:
		frappe.throw(
			_("{0} '{1}' not found (matched neither name nor title).").format(doctype, value),
			frappe.DoesNotExistError,
		)
	if len(matches) > 1:
		frappe.throw(
			_("{0} title '{1}' is ambiguous — matches {2} records: {3}. "
			  "Please pass the exact name instead.").format(
				doctype, value, len(matches), ", ".join(matches)
			),
			frappe.ValidationError,
		)
	return matches[0]


@frappe.whitelist()
def list_batches_and_quizzes():
	"""
	Return the list of batches and quizzes available for the dropdowns
	on the Django evaluation UI. Each entry returns both `name` (the
	stable slug to pass back to get_submissions_for_evaluation) and
	`title` (the human label to show in the dropdown).

	Returns:
		{
		  "batches": [{ "name": "...", "title": "..." }, ...],
		  "quizzes": [{ "name": "...", "title": "..." }, ...]
		}
	"""
	_check_permission()
	return {
		"batches": frappe.get_all(
			"LMS Batch",
			fields=["name", "title"],
			order_by="creation desc",
			limit_page_length=200,
		),
		"quizzes": frappe.get_all(
			"LMS Quiz",
			fields=["name", "title"],
			order_by="creation desc",
			limit_page_length=200,
		),
	}


def _build_submission_payload(submission_name):
	"""Build the LLM-friendly payload for one submission."""
	doc = frappe.get_doc("LMS Quiz Submission", submission_name)

	# Employee block — pulls from custom_employee if present, falls back to
	# Employee where user_id = doc.member.
	employee_info = None
	emp_name = doc.get("custom_employee") or frappe.db.get_value(
		"Employee", {"user_id": doc.member}, "name"
	)
	if emp_name:
		employee_info = frappe.db.get_value(
			"Employee",
			emp_name,
			[
				"name",
				"employee_name",
				"user_id",
				"branch",
				"designation",
				"department",
				"reports_to",
				"custom_region",
				"custom_manager_email_id",
			],
			as_dict=True,
		)

	# Answers: per-question rows, enriched with the question text so the LLM
	# can score without a second lookup.
	answers = []
	for row in (doc.result or []):
		row_dict = row.as_dict() if hasattr(row, "as_dict") else dict(row)
		qid = row_dict.get("question") or row_dict.get("question_name")

		question_text = row_dict.get("question_detail") or ""
		question_type = row_dict.get("type") or ""

		if qid and not question_text:
			q = frappe.db.get_value(
				"LMS Question",
				qid,
				["question", "type"],
				as_dict=True,
			)
			if q:
				question_text = q.question
				if not question_type:
					question_type = q.type

		answers.append({
			"question_id": qid,
			"question_text": question_text,
			"question_type": question_type,
			"marks_out_of": row_dict.get("marks_out_of") or 0,
			"student_answer": row_dict.get("answer") or "",
			"current_marks": row_dict.get("marks") or 0,
			"current_is_correct": row_dict.get("is_correct") or 0,
		})

	return {
		"submission_id": doc.name,
		"creation": str(doc.creation),
		"employee": employee_info,
		"submission": {
			"member": doc.member,
			"member_name": doc.member_name,
			"score": doc.score,
			"score_out_of": doc.score_out_of,
			"percentage": doc.percentage,
			"passing_percentage": doc.passing_percentage,
			# Surface the org-context custom fields too, in case the UI/LLM
			# wants to filter by region/branch downstream.
			"custom_batch": doc.get("custom_batch"),
			"custom_branch": doc.get("custom_branch"),
			"custom_region": doc.get("custom_region"),
			"custom_reports_to": doc.get("custom_reports_to"),
			"custom_manager_email_id": doc.get("custom_manager_email_id"),
		},
		"answers": answers,
	}
