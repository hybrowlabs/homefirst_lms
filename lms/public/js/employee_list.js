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
							frappe.msgprint(
								`Assigned: ${r.message.assigned}<br>
								 Skipped (No User): ${r.message.skipped_no_user}<br>
								 Skipped (Already in Batch): ${r.message.skipped_existing}`
							);
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
							const { created, skipped, failed } = r.message;
							_show_create_user_result(created, skipped, failed);
							listview.refresh();
						},
					});
				}
			);
		});
	},
};

function _show_create_user_result(created, skipped, failed) {
	let html = "";

	if (created.length) {
		html += `<div class="mb-3">
			<b style="color:green">✔ Created (${created.length})</b>
			<ul class="mt-1">
				${created.map((r) => `<li>${r.employee} → ${r.user}</li>`).join("")}
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
			<b style="color:red">✖ Failed (${failed.length})</b>
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
