# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class LMSEvaluationTemplate(Document):
	def validate(self):
		self.validate_parameters_exist()
		self.validate_weightages()
		self.validate_max_scores()

	def validate_parameters_exist(self):
		if not self.parameters:
			frappe.throw(_("At least one evaluation parameter is required."))

	def validate_weightages(self):
		total = sum(flt(p.weightage) for p in self.parameters)
		if abs(total - 100) > 0.01:
			frappe.throw(
				_("Parameter weightages must sum to 100. Current total: {0}").format(
					round(total, 2)
				)
			)

	def validate_max_scores(self):
		for p in self.parameters:
			if not p.max_score or p.max_score <= 0:
				frappe.throw(
					_("Max score for '{0}' must be greater than 0.").format(p.parameter_name)
				)


def flt(val):
	try:
		return float(val or 0)
	except (TypeError, ValueError):
		return 0.0
