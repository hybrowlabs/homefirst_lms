# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

EVALUATOR_ROLES = frozenset({"System Manager", "Moderator", "Batch Evaluator", "Course Creator"})


class LMSInternEvaluation(Document):
	def validate(self):
		self.validate_evaluator_permission()
		self.validate_no_duplicate()

	def validate_evaluator_permission(self):
		if not EVALUATOR_ROLES & set(frappe.get_roles(frappe.session.user)):
			frappe.throw(_("You do not have permission to submit intern evaluations."))

	def validate_no_duplicate(self):
		if frappe.db.exists(
			"LMS Intern Evaluation",
			{
				"intern": self.intern,
				"course": self.course,
				"batch": self.batch,
				"name": ["!=", self.name],
			},
		):
			frappe.throw(
				_(
					"An evaluation for intern {0} in course {1} and batch {2} already exists."
				).format(self.intern, self.course, self.batch)
			)
