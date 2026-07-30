"""Custom file-upload endpoint for LMS lesson content (presentations, etc.).

Frappe's default `upload_file` de-duplicates by content hash: if you re-upload a
file whose bytes are identical to an existing one, it silently reuses the old
File and returns the OLD file_url — so a merely *renamed* file keeps showing its
previous name. Lesson authors expect the renamed file's name to win.

This endpoint uploads the file as a fresh File record even when identical content
already exists, so the new (renamed) file name is preserved. It is wired from the
lesson content uploader via FileUploader's `uploadArgs.method`.

Trade-off: identical content uploaded under different names is stored more than
once on disk. That is the intended behaviour here.
"""

import frappe
from frappe.utils import cint


@frappe.whitelist()
def upload_lesson_file():
	"""Invoked by `/api/method/upload_file` when `method` points here.

	`frappe.handler.upload_file` has already read the uploaded bytes into
	`frappe.local.*` and checked write permission before delegating to us.
	"""
	content = frappe.local.uploaded_file
	filename = frappe.local.uploaded_filename
	file_url = frappe.local.uploaded_file_url

	file_doc = frappe.new_doc("File")
	file_doc.update(
		{
			"attached_to_doctype": frappe.form_dict.doctype,
			"attached_to_name": frappe.form_dict.docname,
			"attached_to_field": frappe.form_dict.fieldname,
			"folder": frappe.form_dict.folder or "Home",
			"file_name": filename,
			"file_url": file_url,
			"is_private": cint(frappe.form_dict.is_private),
			# Populate `content` on the doc (as the default upload_file endpoint
			# does) so File.get_content() returns the uploaded bytes instead of
			# trying to read a not-yet-existent file path.
			"content": content,
		}
	)

	# When actual bytes were uploaded, write them as a brand-new file regardless
	# of whether identical content already exists on the site.
	if content is not None:
		# 1) Write the blob now, skipping the content-hash reuse check. This sets
		#    file_doc.file_name / file_url to the new (renamed) name.
		file_doc.save_file(content=content, ignore_existing_file_check=True)
		# 2) file_url is set, so tell before_insert to skip re-processing the blob
		#    (which would re-run the reuse check and revert to the old name).
		file_doc.flags.copy_from_existing_file = True
		# 3) Skip validate_duplicate_entry, which otherwise resets file_url back to
		#    a matching-content File and undoes everything above.
		file_doc.flags.ignore_duplicate_entry_error = True

	file_doc.insert()
	return file_doc
