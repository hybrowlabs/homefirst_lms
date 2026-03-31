frappe.listview_settings["Employee"] = {
	onload(listview) {
		// ── Action 1: Assign to LMS Batch ────────────────────────────────
		listview.page.add_action_item("Assign to LMS Batch", function () {
			const selected = listview.get_checked_items().map((d) => d.name);

			if (!selected.length) {
				frappe.msgprint("Please select at least one Employee.");
				return;
			}

			let dialog = new frappe.ui.Dialog({
				title: "Select LMS Batch",
				fields: [
					{
						label: "LMS Batch",
						fieldname: "batch",
						fieldtype: "Link",
						options: "LMS Batch",
						reqd: 1,
					},
				],
				primary_action_label: "Assign",
				primary_action(values) {
					frappe.call({
						method: "lms.lms.api.employee_batch_assignment.bulk_assign_existing_employees",
						args: {
							employee_list: selected,
							batch_name: values.batch,
						},
						callback(r) {
							const m = r.message;
							let html = "";

							if (m.assigned > 0) {
								html += `<p style="color:green">✔ <b>${m.assigned}</b> employee(s) assigned to batch.</p>`;
							}
							if (m.skipped_no_user > 0) {
								html += `<p style="color:orange">⚠ <b>${m.skipped_no_user}</b> employee(s) skipped — no LMS user linked yet. Use "Create LMS User" first.</p>`;
							}
							if (m.skipped_existing > 0) {
								html += `<p style="color:gray">ℹ <b>${m.skipped_existing}</b> employee(s) already in this batch.</p>`;
							}
							if (!html) {
								html = "<p>No employees were processed.</p>";
							}

							frappe.msgprint({ title: "Batch Assignment Result", message: html });
							dialog.hide();
							listview.refresh();
						},
					});
				},
			});

			dialog.show();
		});

		// ── Action 2: Create LMS User ─────────────────────────────────────
		listview.page.add_action_item("Create LMS User", function () {
			const selected = listview.get_checked_items().map((d) => d.name);

			if (!selected.length) {
				frappe.msgprint("Please select at least one Employee.");
				return;
			}

			frappe.confirm(
				`Create LMS users for <b>${selected.length}</b> selected employee(s)?<br><br>
				<span class="text-muted" style="font-size:0.85em">
					Employees who already have a user account or have no email address will be skipped.
				</span>`,
				function () {
					frappe.call({
						method: "lms.lms.api.create_employee_user.create_users_for_employees",
						args: { employee_list: selected },
						freeze: true,
						freeze_message: "Creating users, please wait...",
						callback(r) {
							if (!r.message) return;
							const { created, linked, skipped, failed } = r.message;
							_show_create_user_result(created, linked || [], skipped, failed);
							listview.refresh();
						},
					});
				}
			);
		});
	},
};

function _show_create_user_result(created, linked, skipped, failed) {
	let html = "";

	if (created.length) {
		html += `<div class="mb-3">
			<b style="color:green">✔ Created and linked (${created.length})</b>
			<ul class="mt-1">
				${created.map((r) => `<li>${r.employee} — ${r.email}</li>`).join("")}
			</ul>
		</div>`;
	}

	if (linked.length) {
		html += `<div class="mb-3">
			<b style="color:#2d8a4e">✔ Already existed — now linked (${linked.length})</b>
			<ul class="mt-1">
				${linked.map((r) => `<li>${r.employee} — ${r.email}</li>`).join("")}
			</ul>
		</div>`;
	}

	if (skipped.length) {
		html += `<div class="mb-3">
			<b style="color:orange">⚠ Skipped (${skipped.length})</b>
			<ul class="mt-1">
				${skipped.map((r) => `<li>${r.employee}: ${r.reason}</li>`).join("")}
			</ul>
		</div>`;
	}

	if (failed.length) {
		html += `<div class="mb-3">
			<b style="color:red">✖ Could not create (${failed.length})</b>
			<ul class="mt-1">
				${failed.map((r) => `<li>${r.employee} (${r.email}): ${r.error}</li>`).join("")}
			</ul>
		</div>`;
	}

	if (!html) {
		html = "<p>No employees were processed.</p>";
	}

	let d = new frappe.ui.Dialog({
		title: "Create LMS User — Results",
		fields: [{ fieldtype: "HTML", options: html }],
		primary_action_label: "Close",
		primary_action() { d.hide(); },
	});
	d.show();
}
