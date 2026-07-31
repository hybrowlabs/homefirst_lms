from frappe.core.doctype.file.file import File


class LMSFile(File):
	"""Keep a re-uploaded file's own name even when its bytes are identical to an
	existing file.

	Frappe de-duplicates uploads by content hash: re-uploading the same bytes
	under a different name silently reuses the old File (and its old name). A
	lesson author who renames a presentation and re-uploads it expects the new
	name to stick. On this site we therefore skip that content-hash reuse and
	always store a fresh file, so the uploaded (renamed) name is preserved.

	Trade-off: identical content uploaded more than once is stored more than once
	on disk. That is acceptable here and needs no frontend build to take effect.
	"""

	def save_file(self, content=None, decode=False, ignore_existing_file_check=False, overwrite=False):
		# Force a fresh write instead of reusing an existing same-content file.
		return super().save_file(
			content=content,
			decode=decode,
			ignore_existing_file_check=True,
			overwrite=overwrite,
		)

	def validate_duplicate_entry(self):
		# The base check would otherwise swap file_url back to a matching-content
		# File right after save_file; suppress it so the new name/URL survives.
		self.flags.ignore_duplicate_entry_error = True
		return super().validate_duplicate_entry()
