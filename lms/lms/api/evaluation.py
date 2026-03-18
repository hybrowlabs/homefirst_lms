# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import today

EVALUATOR_ROLES = frozenset({"System Manager", "Moderator", "Batch Evaluator", "Course Creator"})


def _assert_can_evaluate():
	"""Raise PermissionError if the caller is not an evaluator/admin."""
	if not EVALUATOR_ROLES & set(frappe.get_roles(frappe.session.user)):
		frappe.throw(_("You do not have permission to submit evaluations."), frappe.PermissionError)


def _flt(val):
	try:
		return float(val or 0)
	except (TypeError, ValueError):
		return 0.0


@frappe.whitelist()
def get_template_for_course(course):
	"""Return the evaluation template for a course, including all parameter rows.

	Returns None cleanly if no template is configured for the course.
	Accessible to any evaluator/admin role.
	"""
	_assert_can_evaluate()

	template_name = frappe.db.get_value(
		"LMS Evaluation Template", {"course": course}, "name"
	)
	if not template_name:
		return None

	template = frappe.get_doc("LMS Evaluation Template", template_name)
	return {
		"name": template.name,
		"template_name": template.template_name,
		"parameters": [
			{
				"parameter_name": p.parameter_name,
				"max_score": p.max_score,
				"weightage": p.weightage,
				"description": p.description or "",
			}
			for p in template.parameters
		],
	}


@frappe.whitelist()
def get_batch_courses_for_evaluation(batch):
	"""Return courses linked to a batch, for the course selector in the evaluation dialog."""
	_assert_can_evaluate()

	course_names = frappe.get_all("Batch Course", {"parent": batch}, pluck="course")
	result = []
	for name in course_names:
		title = frappe.db.get_value("LMS Course", name, "title")
		result.append({"name": name, "title": title or name})
	return result


@frappe.whitelist()
def submit_evaluation(intern, course, batch, scores, comments=""):
	"""Create a submitted LMS Intern Evaluation.

	Args:
		intern    – User name (email) of the intern being evaluated.
		course    – LMS Course name.
		batch     – LMS Batch name.
		scores    – JSON list of dicts: [{parameter_name, score, max_score, weightage, description}].
		comments  – Free-text evaluator feedback (optional).

	Returns the new document name on success.

	Raises:
		PermissionError  if the caller is not an evaluator/admin.
		ValidationError  for missing template, invalid scores, duplicate evaluation.
	"""
	_assert_can_evaluate()

	# ------------------------------------------------------------------
	# Parse + basic presence checks
	# ------------------------------------------------------------------
	if isinstance(scores, str):
		scores = json.loads(scores)

	if not scores:
		frappe.throw(_("No scores provided."))

	if not intern:
		frappe.throw(_("Intern is required."))
	if not course:
		frappe.throw(_("Course is required."))
	if not batch:
		frappe.throw(_("Batch is required."))

	# ------------------------------------------------------------------
	# Verify a template exists for this course
	# ------------------------------------------------------------------
	if not frappe.db.exists("LMS Evaluation Template", {"course": course}):
		frappe.throw(
			_("No evaluation template is configured for this course. Please set one up first.")
		)

	# ------------------------------------------------------------------
	# Validate weightages sum to 100
	# ------------------------------------------------------------------
	total_weightage = sum(_flt(s.get("weightage", 0)) for s in scores)
	if abs(total_weightage - 100) > 0.01:
		frappe.throw(
			_("Parameter weightages must sum to 100. Current total: {0}").format(
				round(total_weightage, 2)
			)
		)

	# ------------------------------------------------------------------
	# Validate individual scores
	# ------------------------------------------------------------------
	for s in scores:
		param = s.get("parameter_name") or s.get("parameter") or "?"
		score = _flt(s.get("score", 0))
		max_score = _flt(s.get("max_score", 0))

		if max_score <= 0:
			frappe.throw(_("Max score for '{0}' must be greater than 0.").format(param))
		if score < 0:
			frappe.throw(_("Score for '{0}' cannot be negative.").format(param))
		if score > max_score:
			frappe.throw(
				_("Score for '{0}' ({1}) exceeds the allowed max score of {2}.").format(
					param, score, max_score
				)
			)

	# ------------------------------------------------------------------
	# Prevent duplicate evaluation
	# ------------------------------------------------------------------
	if frappe.db.exists(
		"LMS Intern Evaluation",
		{"intern": intern, "course": course, "batch": batch},
	):
		frappe.throw(
			_(
				"An evaluation for this intern in course '{0}' and batch '{1}' already exists."
			).format(course, batch)
		)

	# ------------------------------------------------------------------
	# Compute total weighted score  (sum of score/max_score * weightage)
	# ------------------------------------------------------------------
	total_weighted_score = sum(
		(_flt(s["score"]) / _flt(s["max_score"])) * _flt(s["weightage"]) for s in scores
	)

	# ------------------------------------------------------------------
	# Create document
	# ------------------------------------------------------------------
	doc = frappe.get_doc(
		{
			"doctype": "LMS Intern Evaluation",
			"intern": intern,
			"course": course,
			"batch": batch,
			"evaluation_date": today(),
			"evaluator": frappe.session.user,
			"evaluator_comments": comments or "",
			"total_weighted_score": round(total_weighted_score, 2),
			"status": "Submitted",
			"scores": [
				{
					"parameter": s.get("parameter_name") or s.get("parameter"),
					"score": _flt(s["score"]),
					"max_score": _flt(s["max_score"]),
					"weightage": _flt(s["weightage"]),
					"description": s.get("description") or "",
				}
				for s in scores
			],
		}
	)
	doc.insert()
	return doc.name


@frappe.whitelist()
def get_intern_evaluations(intern, batch=None):
	"""Return submitted evaluations for an intern (read by evaluators/admins).

	Optionally filter by batch.
	"""
	_assert_can_evaluate()

	filters = {"intern": intern, "status": "Submitted"}
	if batch:
		filters["batch"] = batch

	return frappe.get_all(
		"LMS Intern Evaluation",
		filters,
		[
			"name",
			"course",
			"batch",
			"evaluation_date",
			"evaluator_name",
			"total_weighted_score",
			"status",
		],
		order_by="evaluation_date desc",
	)
