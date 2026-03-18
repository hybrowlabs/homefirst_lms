# Copyright (c) 2021, Frappe and Contributors
# See license.txt

"""
M6 QA – Grading Notification Tests
====================================
Run with:
    bench --site <site> run-tests \
        --module lms.lms.lms.doctype.lms_assignment_submission.test_lms_assignment_submission

All tests use mocks so no live DB or SMTP is required.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from lms.lms.lms.doctype.lms_assignment_submission.lms_assignment_submission import (
    GRADED_STATUSES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(**overrides):
	"""
	Return a plain LMSAssignmentSubmission document with sensible defaults.
	We call frappe.new_doc so all model machinery (flags, etc.) is intact,
	then override fields as needed.  No DB insert is performed.
	"""
	d = frappe.new_doc("LMS Assignment Submission")
	d.assignment = "ASSIGN-001"
	d.assignment_title = "Python Basics"
	d.member = "student@example.com"
	d.member_name = "Test Student"
	d.evaluator = "evaluator@example.com"
	d.status = "Not Graded"
	d.comments = ""
	d.lesson = "LESSON-001"
	d.type = "Text"
	d.answer = "My answer"
	d.update(overrides)
	return d


def _before_save(status="Not Graded", comments=""):
	"""Lightweight stand-in for doc_before_save."""
	bs = MagicMock()
	bs.status = status
	bs.comments = comments
	return bs


def _run_validate_status(cur_status, cur_comments, bef_status, bef_comments):
	"""
	Helper: configure doc, call validate_status(), return number of times
	trigger_grading_notification was called.
	"""
	doc = _make_doc(status=cur_status, comments=cur_comments)
	doc.get_doc_before_save = MagicMock(return_value=_before_save(bef_status, bef_comments))
	doc.flags.in_insert = False
	doc.trigger_grading_notification = MagicMock()
	doc.validate_status()
	return doc.trigger_grading_notification.call_count


# ===========================================================================
# TC-01  GRADED_STATUSES constant matches production doctype values
# ===========================================================================

class TestGradedStatusesConstant(unittest.TestCase):
	"""
	Status Select options from the JSON:  Pass / Fail / Not Graded / Not Applicable
	GRADED_STATUSES must include the three that represent a finalised grade.
	"""

	def test_pass_included(self):
		self.assertIn("Pass", GRADED_STATUSES)

	def test_fail_included(self):
		self.assertIn("Fail", GRADED_STATUSES)

	def test_not_applicable_included(self):
		self.assertIn("Not Applicable", GRADED_STATUSES)

	def test_not_graded_excluded(self):
		self.assertNotIn("Not Graded", GRADED_STATUSES)

	def test_exactly_three_statuses(self):
		self.assertEqual(len(GRADED_STATUSES), 3)


# ===========================================================================
# TC-02  validate_status() trigger logic
# ===========================================================================

class TestValidateStatusTrigger(unittest.TestCase):

	# ── Must trigger ─────────────────────────────────────────────────────────

	def test_triggers_not_graded_to_pass(self):
		self.assertEqual(_run_validate_status("Pass", "", "Not Graded", ""), 1)

	def test_triggers_not_graded_to_fail(self):
		self.assertEqual(_run_validate_status("Fail", "", "Not Graded", ""), 1)

	def test_triggers_not_graded_to_not_applicable(self):
		self.assertEqual(_run_validate_status("Not Applicable", "", "Not Graded", ""), 1)

	def test_triggers_regrade_pass_to_fail(self):
		self.assertEqual(_run_validate_status("Fail", "Needs more work", "Pass", "Good"), 1)

	def test_triggers_regrade_fail_to_pass(self):
		self.assertEqual(_run_validate_status("Pass", "Revised", "Fail", "Too short"), 1)

	def test_triggers_feedback_update_on_passed_submission(self):
		"""Evaluator updates comments while keeping status=Pass."""
		self.assertEqual(_run_validate_status("Pass", "Updated feedback", "Pass", "Old feedback"), 1)

	def test_triggers_feedback_update_on_failed_submission(self):
		self.assertEqual(_run_validate_status("Fail", "Detailed reasons", "Fail", ""), 1)

	# ── Must NOT trigger ─────────────────────────────────────────────────────

	def test_no_trigger_on_new_doc(self):
		"""is_new() guard must block notification on first insert."""
		doc = _make_doc(status="Pass")
		doc.trigger_grading_notification = MagicMock()
		doc.flags.in_insert = True   # frappe.new_doc sets this
		doc.validate_status()
		doc.trigger_grading_notification.assert_not_called()

	def test_no_trigger_when_nothing_changed(self):
		self.assertEqual(_run_validate_status("Pass", "Feedback", "Pass", "Feedback"), 0)

	def test_no_trigger_on_not_graded_status(self):
		"""Student re-saves their own submission before grading."""
		self.assertEqual(_run_validate_status("Not Graded", "draft", "Not Graded", ""), 0)

	def test_no_trigger_when_grade_reset_to_not_graded(self):
		"""Evaluator resets grade back to Not Graded."""
		self.assertEqual(_run_validate_status("Not Graded", "", "Pass", "Good"), 0)

	def test_no_trigger_on_comment_change_when_not_graded(self):
		"""Evaluator adds a draft comment but has not yet set a grade."""
		self.assertEqual(_run_validate_status("Not Graded", "Draft note", "Not Graded", ""), 0)


# ===========================================================================
# TC-03  _build_subject() produces correct, grade-aware subject lines
# ===========================================================================

class TestBuildSubject(unittest.TestCase):

	def _subject(self, status, title="Python Basics"):
		return _make_doc(status=status, assignment_title=title)._build_subject()

	def test_pass_subject_contains_pass(self):
		subj = self._subject("Pass")
		self.assertIn("Pass", subj)

	def test_pass_subject_contains_title(self):
		subj = self._subject("Pass", "My Assignment")
		self.assertIn("My Assignment", subj)

	def test_fail_subject_contains_fail(self):
		self.assertIn("Fail", self._subject("Fail"))

	def test_not_applicable_subject_contains_not_applicable(self):
		self.assertIn("Not Applicable", self._subject("Not Applicable"))

	def test_pass_and_fail_subjects_are_different(self):
		self.assertNotEqual(self._subject("Pass"), self._subject("Fail"))


# ===========================================================================
# TC-04  _build_email_body() content
# ===========================================================================

class TestBuildEmailBody(unittest.TestCase):

	def test_body_includes_status(self):
		doc = _make_doc(status="Pass", comments="")
		self.assertIn("Pass", doc._build_email_body())

	def test_body_includes_feedback_when_present(self):
		doc = _make_doc(status="Fail", comments="<p>Too short</p>")
		body = doc._build_email_body()
		self.assertIn("Feedback", body)
		self.assertIn("Too short", body)

	def test_body_omits_feedback_section_when_comments_empty(self):
		doc = _make_doc(status="Pass", comments="")
		self.assertNotIn("Feedback", doc._build_email_body())

	def test_body_omits_feedback_section_when_comments_none(self):
		doc = _make_doc(status="Pass")
		doc.comments = None
		self.assertNotIn("Feedback", doc._build_email_body())


# ===========================================================================
# TC-05  _send_grading_email() guards and sendmail call
# ===========================================================================

class TestSendGradingEmail(unittest.TestCase):

	_ROUTE = "lms/assignment-submission/ASSIGN-001/SUB-001"
	_SUBJECT = "Your assignment Python Basics has been graded: Pass"

	def _call(self, doc, exists_return, get_value_map=None):
		"""DRY helper: patch DB and call _send_grading_email."""
		gv_map = get_value_map or {}

		def _gv(dt, name, field, **kw):
			return gv_map.get((dt, name, field))

		with patch("frappe.db.exists", return_value=exists_return), \
		     patch("frappe.db.get_value", side_effect=_gv), \
		     patch("frappe.utils.get_url", return_value="https://lms.example.com"), \
		     patch("frappe.sendmail") as mock_sm:
			doc._send_grading_email(self._SUBJECT, self._ROUTE)
			return mock_sm

	def test_sendmail_called_when_email_account_exists(self):
		doc = _make_doc(status="Pass")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		mock_sm.assert_called_once()

	def test_sendmail_skipped_when_no_email_account(self):
		mock_sm = self._call(_make_doc(status="Pass"), None)
		mock_sm.assert_not_called()

	def test_sendmail_skipped_when_member_email_missing(self):
		doc = _make_doc(status="Pass")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): None,
		})
		mock_sm.assert_not_called()

	def test_recipients_is_student_email(self):
		doc = _make_doc(status="Pass")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		self.assertEqual(mock_sm.call_args.kwargs["recipients"], "student@example.com")

	def test_template_is_assignment_graded(self):
		doc = _make_doc(status="Pass")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		self.assertEqual(mock_sm.call_args.kwargs["template"], "assignment_graded")

	def test_args_contain_status_pass(self):
		doc = _make_doc(status="Pass", comments="Well done!")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		args = mock_sm.call_args.kwargs["args"]
		self.assertEqual(args["status"], "Pass")
		self.assertIn("Well done", args["comments"])
		self.assertEqual(args["member_name"], "Test Student")
		self.assertEqual(args["evaluator_name"], "Jane")

	def test_args_contain_status_fail(self):
		doc = _make_doc(status="Fail", comments="Needs revision")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Bob",
		})
		self.assertEqual(mock_sm.call_args.kwargs["args"]["status"], "Fail")

	def test_header_green_for_pass(self):
		doc = _make_doc(status="Pass")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		self.assertEqual(mock_sm.call_args.kwargs["header"][1], "green")

	def test_header_orange_for_fail(self):
		doc = _make_doc(status="Fail")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		self.assertEqual(mock_sm.call_args.kwargs["header"][1], "orange")

	def test_header_orange_for_not_applicable(self):
		doc = _make_doc(status="Not Applicable")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		self.assertEqual(mock_sm.call_args.kwargs["header"][1], "orange")

	def test_evaluator_name_fallback_when_evaluator_is_none(self):
		doc = _make_doc(status="Pass")
		doc.evaluator = None
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
		})
		args = mock_sm.call_args.kwargs["args"]
		self.assertTrue(args["evaluator_name"])   # non-empty fallback string

	def test_retry_set_to_3(self):
		doc = _make_doc(status="Pass")
		mock_sm = self._call(doc, "Default Outgoing", {
			("User", "student@example.com", "email"): "student@example.com",
			("User", "evaluator@example.com", "full_name"): "Jane",
		})
		self.assertEqual(mock_sm.call_args.kwargs["retry"], 3)


# ===========================================================================
# TC-06  trigger_grading_notification() orchestration
# ===========================================================================

_MNL_PATH = (
	"lms.lms.lms.doctype.lms_assignment_submission"
	".lms_assignment_submission.make_notification_logs"
)
_ROUTE_PATH = (
	"lms.lms.lms.doctype.lms_assignment_submission"
	".lms_assignment_submission.get_lms_route"
)


class TestTriggerGradingNotification(unittest.TestCase):

	@patch(_MNL_PATH)
	def test_make_notification_logs_called_once(self, mock_mnl):
		doc = _make_doc(status="Pass")
		doc._send_grading_email = MagicMock()
		with patch(_ROUTE_PATH, return_value="lms/x"):
			doc.trigger_grading_notification()
		mock_mnl.assert_called_once()

	@patch(_MNL_PATH)
	def test_send_grading_email_called_once(self, _):
		doc = _make_doc(status="Fail")
		doc._send_grading_email = MagicMock()
		with patch(_ROUTE_PATH, return_value="lms/x"):
			doc.trigger_grading_notification()
		doc._send_grading_email.assert_called_once()

	@patch(_MNL_PATH)
	def test_notification_recipient_is_member(self, mock_mnl):
		doc = _make_doc(status="Pass", member="student@example.com")
		doc._send_grading_email = MagicMock()
		with patch(_ROUTE_PATH, return_value="lms/x"):
			doc.trigger_grading_notification()
		_, recipients = mock_mnl.call_args.args
		self.assertIn("student@example.com", recipients)

	@patch(_MNL_PATH)
	def test_notification_type_is_alert(self, mock_mnl):
		doc = _make_doc(status="Pass")
		doc._send_grading_email = MagicMock()
		with patch(_ROUTE_PATH, return_value="lms/x"):
			doc.trigger_grading_notification()
		notification = mock_mnl.call_args.args[0]
		self.assertEqual(notification["type"], "Alert")

	@patch(_MNL_PATH)
	def test_notification_subject_contains_grade(self, mock_mnl):
		doc = _make_doc(status="Pass", assignment_title="Python Basics")
		doc._send_grading_email = MagicMock()
		with patch(_ROUTE_PATH, return_value="lms/x"):
			doc.trigger_grading_notification()
		notification = mock_mnl.call_args.args[0]
		self.assertIn("Pass", notification["subject"])

	@patch(_MNL_PATH)
	def test_notification_email_content_contains_status(self, mock_mnl):
		doc = _make_doc(status="Fail", comments="Needs revision")
		doc._send_grading_email = MagicMock()
		with patch(_ROUTE_PATH, return_value="lms/x"):
			doc.trigger_grading_notification()
		notification = mock_mnl.call_args.args[0]
		self.assertIn("Fail", notification["email_content"])

	@patch(_MNL_PATH)
	def test_notification_from_user_is_evaluator(self, mock_mnl):
		doc = _make_doc(status="Pass", evaluator="evaluator@example.com")
		doc._send_grading_email = MagicMock()
		with patch(_ROUTE_PATH, return_value="lms/x"):
			doc.trigger_grading_notification()
		notification = mock_mnl.call_args.args[0]
		self.assertEqual(notification["from_user"], "evaluator@example.com")


# ===========================================================================
# TC-07  Duplicate notification prevention
# ===========================================================================

class TestDuplicatePrevention(unittest.TestCase):

	def _total_notifications(self, saves):
		"""
		saves = list of (current_status, current_comments, before_status, before_comments)
		Simulates multiple sequential saves; returns total trigger call count.
		"""
		total = 0
		for cur_st, cur_cm, bef_st, bef_cm in saves:
			total += _run_validate_status(cur_st, cur_cm, bef_st, bef_cm)
		return total

	def test_identical_resave_does_not_duplicate(self):
		"""Save once (graded), then save again with no changes → 1 total."""
		total = self._total_notifications([
			("Pass", "Good",  "Not Graded", ""),    # grade event → 1
			("Pass", "Good",  "Pass",       "Good"), # nothing changed → 0
		])
		self.assertEqual(total, 1)

	def test_regrade_produces_second_notification(self):
		"""Evaluator changes from Pass to Fail → 2 total notifications."""
		total = self._total_notifications([
			("Pass", "Good try",      "Not Graded",   ""),         # 1
			("Fail", "Needs revision","Pass",          "Good try"), # 1
		])
		self.assertEqual(total, 2)

	def test_feedback_update_after_grade_is_one_more(self):
		"""
		Grade (1 notification) → update comments (1 more) → save unchanged (0) = 2 total.
		"""
		total = self._total_notifications([
			("Pass", "Good",          "Not Graded", ""),          # 1
			("Pass", "Good. Detail.", "Pass",        "Good"),      # 1
			("Pass", "Good. Detail.", "Pass",        "Good. Detail."),  # 0
		])
		self.assertEqual(total, 2)

	def test_multiple_ungraded_saves_never_notify(self):
		"""Student saves draft multiple times before grading → 0 notifications."""
		total = self._total_notifications([
			("Not Graded", "draft v1", "Not Graded", ""),
			("Not Graded", "draft v2", "Not Graded", "draft v1"),
			("Not Graded", "draft v3", "Not Graded", "draft v2"),
		])
		self.assertEqual(total, 0)


# ===========================================================================
# TC-08  Frappe "Alert" type hard-coded to never send email
# ===========================================================================

class TestAlertTypeEmailSuppression(unittest.TestCase):
	"""
	Frappe's is_email_notifications_enabled_for_type short-circuits at
	  if notification_type == "Alert": return False
	which means our _send_grading_email is the ONLY email path.
	No duplicate emails can come from the Notification Log system.
	"""

	def test_alert_always_returns_false(self):
		from frappe.desk.doctype.notification_settings.notification_settings import (
			is_email_notifications_enabled_for_type,
		)
		with patch(
			"frappe.desk.doctype.notification_settings.notification_settings"
			".is_email_notifications_enabled",
			return_value=True,  # email notifications ON for the user
		):
			result = is_email_notifications_enabled_for_type("any@example.com", "Alert")
		self.assertFalse(result, "Alert type must never trigger Frappe's own email")


# ===========================================================================
# TC-09  Transaction safety — validate() call order
# ===========================================================================

class TestTransactionSafety(unittest.TestCase):
	"""
	validate_status() must run last inside validate() so that if
	validate_duplicates() or validate_url() raises, the notification
	is never fired (and no Notification Log / Email Queue rows are
	written to the DB before a potential rollback).
	"""

	def test_validate_calls_validate_status(self):
		doc = _make_doc()
		doc.validate_duplicates = MagicMock()
		doc.validate_url = MagicMock()
		doc.validate_status = MagicMock()
		doc.validate()
		doc.validate_status.assert_called_once()

	def test_call_order_dups_then_url_then_status(self):
		order = []
		doc = _make_doc()
		doc.validate_duplicates = MagicMock(side_effect=lambda: order.append("dups"))
		doc.validate_url = MagicMock(side_effect=lambda: order.append("url"))
		doc.validate_status = MagicMock(side_effect=lambda: order.append("status"))
		doc.validate()
		self.assertEqual(order, ["dups", "url", "status"])

	def test_no_notification_when_duplicate_raises(self):
		"""validate_duplicates raises → validate_status never runs."""
		doc = _make_doc()
		doc.validate_duplicates = MagicMock(
			side_effect=frappe.ValidationError("Duplicate assignment")
		)
		doc.validate_status = MagicMock()
		with self.assertRaises(frappe.ValidationError):
			doc.validate()
		doc.validate_status.assert_not_called()


# ===========================================================================
# TC-10  Email template file exists and renders correctly
# ===========================================================================

class TestEmailTemplate(unittest.TestCase):

	def _env(self):
		import os
		from jinja2 import Environment, FileSystemLoader
		template_dir = os.path.join(
			frappe.get_app_path("lms"), "templates", "emails"
		)
		return Environment(loader=FileSystemLoader(template_dir))

	def _render(self, **kwargs):
		defaults = dict(
			member_name="Test Student",
			assignment_title="Python Basics",
			status="Pass",
			comments="",
			evaluator_name="Jane Evaluator",
			link="https://lms.example.com/lms/assignment-submission/A/B",
		)
		defaults.update(kwargs)
		return self._env().get_template("assignment_graded.html").render(**defaults)

	def test_template_file_exists(self):
		import os
		path = os.path.join(
			frappe.get_app_path("lms"), "templates", "emails", "assignment_graded.html"
		)
		self.assertTrue(os.path.exists(path))

	def test_render_pass_contains_student_name(self):
		self.assertIn("Test Student", self._render(status="Pass"))

	def test_render_pass_contains_assignment_title(self):
		self.assertIn("Python Basics", self._render(status="Pass"))

	def test_render_pass_contains_pass(self):
		self.assertIn("Pass", self._render(status="Pass"))

	def test_render_fail_contains_fail(self):
		self.assertIn("Fail", self._render(status="Fail"))

	def test_render_with_comments_shows_feedback(self):
		rendered = self._render(status="Pass", comments="<p>Well done!</p>")
		self.assertIn("Feedback", rendered)
		self.assertIn("Well done", rendered)

	def test_render_without_comments_no_feedback_section(self):
		rendered = self._render(status="Pass", comments="")
		self.assertNotIn("Feedback", rendered)

	def test_render_contains_link(self):
		url = "https://lms.example.com/lms/assignment-submission/A/B"
		self.assertIn(url, self._render(link=url))

	def test_render_contains_evaluator_name(self):
		self.assertIn("Jane Evaluator", self._render(evaluator_name="Jane Evaluator"))

	def test_render_does_not_raise_for_none_comments(self):
		"""Template must handle empty string for comments gracefully."""
		rendered = self._render(comments="")
		self.assertIsInstance(rendered, str)
