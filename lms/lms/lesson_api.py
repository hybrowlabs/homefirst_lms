import frappe

from lms.lms.utils import (
	_check_chapter_progression,
	_is_course_privileged,
)


@frappe.whitelist()
def get_lesson_with_guard(lesson_name, course):
	"""
	Returns lesson data only if the chapter progression rules are satisfied.
	Raises PermissionError otherwise.
	Moderators and course instructors bypass the check.
	"""
	user = frappe.session.user

	if _is_course_privileged(user, course):
		return frappe.get_doc("Course Lesson", lesson_name).as_dict()

	is_blocked, prev_title = _check_chapter_progression(lesson_name, course)
	if is_blocked:
		frappe.throw(
			f"You must complete '{prev_title}' before accessing this lesson.",
			frappe.PermissionError,
		)

	return frappe.get_doc("Course Lesson", lesson_name).as_dict()


@frappe.whitelist()
def is_previous_lesson_complete(lesson_name, course):
	"""
	Returns True if all progression requirements for this lesson are met
	(all previous-chapter lessons done, and previous lesson in this chapter done).
	Used by the frontend to decide whether to enable the Next button.
	"""
	user = frappe.session.user

	if _is_course_privileged(user, course):
		return True

	is_blocked, _ = _check_chapter_progression(lesson_name, course)
	return not is_blocked
