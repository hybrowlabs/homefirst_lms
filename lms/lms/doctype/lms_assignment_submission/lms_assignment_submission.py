# Copyright (c) 2021, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import make_notification_logs
from frappe.model.document import Document
from frappe.utils import strip_html, validate_url

from lms.lms.utils import get_lms_route

# Statuses that represent a completed grading action
GRADED_STATUSES = ("Pass", "Fail", "Not Applicable")


class LMSAssignmentSubmission(Document):
	def validate(self):
		self.validate_duplicates()
		self.validate_url()
		self.validate_grade_access()
		self.validate_status()

	def on_update(self):
		self.validate_private_attachments()

	def validate_duplicates(self):
		if frappe.db.exists(
			"LMS Assignment Submission",
			{"assignment": self.assignment, "member": self.member, "name": ["!=", self.name]},
		):
			lesson_title = frappe.db.get_value("Course Lesson", self.lesson, "title")
			frappe.throw(
				_("Assignment for Lesson {0} by {1} already exists.").format(lesson_title, self.member_name)
			)

	def validate_url(self):
		if self.type == "URL" and not validate_url(self.answer, True, ["http", "https"]):
			frappe.throw(_("Please enter a valid URL."))

	def validate_grade_access(self):
		"""Prevent students from self-grading their own submissions."""
		if self.is_new():
			return
		doc_before_save = self.get_doc_before_save()
		if not doc_before_save:
			return
		if doc_before_save.status == self.status:
			return
		grading_roles = {"System Manager", "Moderator", "Batch Evaluator", "Course Creator"}
		if not grading_roles & set(frappe.get_roles(frappe.session.user)):
			frappe.throw(_("You do not have permission to grade this submission."))

	def validate_status(self):
		if self.is_new():
			return

		doc_before_save = self.get_doc_before_save()
		if not doc_before_save:
			return

		status_changed = doc_before_save.status != self.status
		comments_changed = doc_before_save.comments != self.comments

		# Notify when a grade is finalized (status set to a graded value),
		# or when the evaluator updates feedback on an already-graded submission.
		is_graded = self.status in GRADED_STATUSES
		if (status_changed and is_graded) or (comments_changed and is_graded and not status_changed):
			self.trigger_grading_notification()

	def validate_private_attachments(self):
		if self.type == "Text":
			if not self.answer:
				return
			from bs4 import BeautifulSoup

			soup = BeautifulSoup(self.answer, "html.parser")
			images = soup.find_all("img")
			self.attach_images_to_document(images)

	def attach_images_to_document(self, images):
		for img in images:
			src = img.get("src", "")
			if src.startswith("/private/files/"):
				file_name = frappe.db.get_value("File", {"file_url": src}, "name")
				if file_name:
					frappe.db.set_value(
						"File",
						file_name,
						{
							"attached_to_doctype": self.doctype,
							"attached_to_name": self.name,
							"attached_to_field": "answer",
						},
					)

	# ------------------------------------------------------------------
	# M6 – Grading notification
	# ------------------------------------------------------------------

	def trigger_grading_notification(self):
		"""
		Called from validate_status() whenever a grade is finalised or feedback
		is updated on an already-graded submission.

		Two things happen:
		  1. An in-app Notification Log is created → the on_change hook on
		     Notification Log fires publish_realtime so the student sees a
		     real-time bell/toast immediately.
		  2. frappe.sendmail() queues an Email Queue row in the SAME DB
		     transaction as the document save.  The row is committed together
		     with the document; background workers pick it up and deliver it.
		     NOTE: do NOT move this to after_commit — after_commit runs inside
		     a new begin() transaction which is never committed, so any
		     Email Queue row inserted there is silently rolled back.
		"""
		subject = self._build_subject()
		link = get_lms_route(f"assignment-submission/{self.assignment}/{self.name}")

		# ── 1. In-app Notification Log ────────────────────────────────────
		notification = frappe._dict(
			{
				"subject": subject,
				"email_content": self._build_email_body(),
				"document_type": self.doctype,
				"document_name": self.name,
				"from_user": self.evaluator,
				"type": "Alert",
				"link": link,
			}
		)
		make_notification_logs(notification, [self.member])

		# ── 2. Guaranteed email — called directly so the Email Queue row is
		#       part of the current (pre-commit) transaction and committed
		#       together with the document save.
		self._send_grading_email(subject, link)

	def _build_subject(self):
		"""Return a subject line that tells the student the actual grade."""
		if self.status == "Pass":
			return _("Your assignment {0} has been graded: Pass").format(
				frappe.bold(self.assignment_title)
			)
		elif self.status == "Fail":
			return _("Your assignment {0} has been graded: Fail").format(
				frappe.bold(self.assignment_title)
			)
		elif self.status == "Not Applicable":
			return _("Your assignment {0} has been marked as Not Applicable").format(
				frappe.bold(self.assignment_title)
			)
		# Feedback update on an already-graded submission
		return _("Your evaluator has updated feedback on assignment {0}").format(
			frappe.bold(self.assignment_title)
		)

	def _build_email_body(self):
		"""Short HTML body used as email_content in the Notification Log."""
		lines = [f"<b>Result:</b> {self.status}"]
		if self.comments:
			lines.append(f"<b>Feedback:</b><br>{self.comments}")
		return "<br><br>".join(lines)

	def _send_grading_email(self, subject, link):
		"""
		Queue a grading notification email for the student.

		Uses frappe.sendmail() which inserts an Email Queue row in the current
		DB transaction.  Background workers pick it up and deliver it after the
		transaction commits.

		All failure paths are logged to Error Log (Settings → Error Log).
		"""
		try:
			if not frappe.db.exists("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}):
				frappe.log_error(
					title="LMS Grading Email Skipped — No Outgoing Email Account",
					message=(
						f"Submission: {self.name}\n"
						f"Member: {self.member}\n"
						f"Status: {self.status}\n\n"
						"Configure an Email Account with 'Default Outgoing' enabled in "
						"Settings → Email Account."
					),
				)
				return

			# User.name == email for standard Frappe users; fall back to name directly.
			recipient_email = (
				frappe.db.get_value("User", self.member, "email") or self.member
			)
			if not recipient_email:
				frappe.log_error(
					title="LMS Grading Email Skipped — No Recipient Email",
					message=f"Could not resolve email for member '{self.member}'. Submission: {self.name}",
				)
				return

			evaluator_name = (
				frappe.db.get_value("User", self.evaluator, "full_name")
				if self.evaluator
				else _("Your evaluator")
			)

			email_subject = strip_html(subject)
			header_color = "green" if self.status == "Pass" else "orange"

			frappe.sendmail(
				recipients=recipient_email,
				subject=email_subject,
				template="assignment_graded",
				args={
					"member_name": self.member_name or self.member,
					"assignment_title": self.assignment_title,
					"status": self.status,
					"comments": self.comments or "",
					"evaluator_name": evaluator_name,
					"link": frappe.utils.get_url() + link,
				},
				header=[email_subject, header_color],
				retry=3,
			)
		except Exception:
			frappe.log_error(
				title="LMS Grading Email Failed",
				message=frappe.get_traceback(),
			)
