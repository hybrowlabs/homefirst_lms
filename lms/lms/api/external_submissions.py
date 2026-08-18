# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""APIs for pushing quiz and assignment results into LMS from outside.

LMS already has `quiz_summary`, but it is built for the LMS player: it takes
every answer, grades them itself, and always files the attempt under
`frappe.session.user`. Neither fits an external system that has *already*
graded and needs to file the result for somebody else.

These two calls do that:

    submit_quiz_score        — a quiz score for one member
    submit_assignment_result — a Pass/Fail (or feedback) for one member

Both name the member explicitly, so the caller is an integration user rather
than the student.

On scores: LMS Quiz Submission recomputes `score` inside its own validate(),
by summing the `marks` of its result rows — a score assigned directly is
overwritten. So the score is carried in the rows. Pass per-question `results`
and they are used as-is; pass only a total and one summary row holds it.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

# Roles LMSAssignmentSubmission.validate_grade_access() accepts as graders.
# Anything else is refused a status change, so the caller is checked up front
# with a message that says so, rather than failing deeper in.
GRADING_ROLES = {"System Manager", "Moderator", "Batch Evaluator", "Course Creator"}

GRADED_STATUSES = ("Pass", "Fail", "Not Applicable")
ASSIGNMENT_STATUSES = GRADED_STATUSES + ("Not Graded",)


def _loads(value):
	"""Accept JSON strings as well as real lists/dicts — REST callers send strings."""
	if isinstance(value, str):
		return json.loads(value)
	return value


def _require_member(member):
	if not member:
		frappe.throw(_("member is required."), frappe.MandatoryError)
	if not frappe.db.exists("User", member):
		frappe.throw(_("User {0} does not exist.").format(member), frappe.DoesNotExistError)
	return member


def _result_rows(results, score, score_out_of):
	"""The rows whose marks add up to the score LMS will store.

	Per-question results are kept whole — the submission then reads like one
	made in the LMS itself, answer by answer. With only a total to go on there
	is nothing to break down, so a single row carries it.
	"""
	rows = []

	for row in _loads(results) or []:
		rows.append(
			{
				"question": row.get("question"),
				"question_name": row.get("question_name"),
				"answer": row.get("answer"),
				"is_correct": cint(row.get("is_correct")),
				"marks": cint(row.get("marks")),
				"marks_out_of": cint(row.get("marks_out_of")),
			}
		)

	if rows:
		return rows

	return [
		{
			"question": _("Score submitted externally"),
			"answer": "",
			"is_correct": 0,
			"marks": cint(score),
			"marks_out_of": cint(score_out_of),
		}
	]


@frappe.whitelist()
def submit_quiz_score(quiz, member, score, results=None):
	"""File a quiz attempt for `member` with a score worked out elsewhere.

	Args:
		quiz: LMS Quiz name.
		member: User the attempt belongs to.
		score: Marks scored, out of the quiz's own total_marks.
		results: Optional per-question rows — question, question_name, answer,
			is_correct, marks, marks_out_of. Their marks must add up to `score`.

	Returns the submission name, the score, the percentage, and whether it
	passed the quiz's passing percentage.

	The marks available are not a parameter: `score_out_of` is read-only on the
	submission and fetched from the quiz, so anything passed in is discarded.
	A quiz with no total_marks is therefore rejected — every score against it
	would silently come out at 0%.
	"""
	_require_member(member)

	quiz_details = frappe.db.get_value(
		"LMS Quiz",
		quiz,
		["name", "title", "total_marks", "passing_percentage", "lesson", "course", "max_attempts"],
		as_dict=True,
	)
	if not quiz_details:
		frappe.throw(_("Quiz {0} does not exist.").format(quiz), frappe.DoesNotExistError)

	score = cint(score)
	score_out_of = cint(quiz_details.total_marks)
	if not score_out_of:
		frappe.throw(
			_("Quiz {0} has no total marks set, so no percentage can be worked out.").format(quiz),
			frappe.ValidationError,
		)
	if score > score_out_of:
		frappe.throw(_("Score {0} is more than the {1} marks available.").format(score, score_out_of))

	# The doctype counts attempts against frappe.session.user, which is the
	# integration user here — it would never see the member's own attempts. So
	# the limit is applied to the member, which is what it is meant to mean.
	max_attempts = cint(quiz_details.max_attempts)
	if max_attempts:
		attempts = frappe.db.count("LMS Quiz Submission", {"quiz": quiz, "member": member})
		if attempts >= max_attempts:
			frappe.throw(
				_("{0} has already used all {1} attempts for this quiz.").format(member, max_attempts),
				frappe.ValidationError,
			)

	submission = frappe.new_doc("LMS Quiz Submission")
	submission.update(
		{
			"quiz": quiz,
			"member": member,
			"course": quiz_details.course,
			"quiz_title": quiz_details.title,
			"score_out_of": score_out_of,
			"passing_percentage": cint(quiz_details.passing_percentage),
			# Both are mandatory and the mandatory check runs before validate(),
			# which is where the controller fills them in from the rows. Seeding
			# them with zero lets it get that far — the same thing LMS's own
			# create_submission() does.
			"score": 0,
			"percentage": 0,
			"result": _result_rows(results, score, score_out_of),
		}
	)
	submission.save(ignore_permissions=True)

	# Clearing the quiz counts towards the lesson, exactly as it does in the
	# LMS player.
	from lms.lms.doctype.lms_quiz.lms_quiz import save_progress_after_quiz

	save_progress_after_quiz(quiz_details, flt(submission.percentage))

	return {
		"submission": submission.name,
		"member": member,
		"score": cint(submission.score),
		"score_out_of": score_out_of,
		"percentage": flt(submission.percentage),
		"passing_percentage": cint(quiz_details.passing_percentage),
		"passed": flt(submission.percentage) >= cint(quiz_details.passing_percentage),
	}


@frappe.whitelist()
def submit_assignment_result(
	assignment, member, status=None, comments=None, answer=None, assignment_attachment=None
):
	"""Record — or re-record — one member's result for an assignment.

	One submission exists per assignment and member, so a second call updates
	the first rather than being refused as a duplicate.

	Args:
		assignment: LMS Assignment name.
		member: User the submission belongs to.
		status: Pass, Fail, Not Graded or Not Applicable.
		comments: Evaluator feedback. Shown to the member with the grade.
		answer: The member's answer, for the assignment's own type.
		assignment_attachment: File URL, when the answer is a file.

	Setting a status counts as grading: the member is notified and emailed by
	the doctype itself.
	"""
	_require_member(member)

	assignment_details = frappe.db.get_value(
		"LMS Assignment", assignment, ["name", "title", "type", "course"], as_dict=True
	)
	if not assignment_details:
		frappe.throw(
			_("Assignment {0} does not exist.").format(assignment), frappe.DoesNotExistError
		)

	if status and status not in ASSIGNMENT_STATUSES:
		frappe.throw(
			_("status must be one of: {0}").format(", ".join(ASSIGNMENT_STATUSES)),
			frappe.ValidationError,
		)

	# Grading is refused deeper in for anyone without one of these roles; saying
	# so here names the missing role instead of a generic permission error.
	if status and not (GRADING_ROLES & set(frappe.get_roles(frappe.session.user))):
		frappe.throw(
			_("Grading needs one of these roles: {0}.").format(", ".join(sorted(GRADING_ROLES))),
			frappe.PermissionError,
		)

	name = frappe.db.get_value(
		"LMS Assignment Submission", {"assignment": assignment, "member": member}, "name"
	)
	created = not name

	if name:
		submission = frappe.get_doc("LMS Assignment Submission", name)
	else:
		submission = frappe.new_doc("LMS Assignment Submission")
		submission.update(
			{
				"assignment": assignment,
				"member": member,
				"course": assignment_details.course,
				"assignment_title": assignment_details.title,
				"type": assignment_details.type,
			}
		)

	if answer is not None:
		submission.answer = answer
	if assignment_attachment is not None:
		submission.assignment_attachment = assignment_attachment
	if comments is not None:
		submission.comments = comments
	if status:
		submission.status = status
		submission.evaluator = frappe.session.user

	submission.save(ignore_permissions=True)

	return {
		"submission": submission.name,
		"member": member,
		"status": submission.status,
		"created": created,
		"graded": submission.status in GRADED_STATUSES,
	}
