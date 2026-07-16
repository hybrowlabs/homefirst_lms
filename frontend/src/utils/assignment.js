import { Pencil } from 'lucide-vue-next'
import { createApp, h } from 'vue'
import AssessmentPlugin from '@/components/AssessmentPlugin.vue'
import translationPlugin from '../translation'
import { usersStore } from '@/stores/user'
import { call } from 'frappe-ui'
import router from '@/router'
import { getLmsRoute } from '@/utils/basePath'

export class Assignment {
	constructor({ data, api, readOnly }) {
		this.data = data
		this.readOnly = readOnly
	}

	static get toolbox() {
		const app = createApp({
			render: () =>
				h(Pencil, { size: 18, strokeWidth: 1.5, color: 'black' }),
		})

		const div = document.createElement('div')
		app.mount(div)

		return {
			title: __('Assignment'),
			icon: div.innerHTML,
		}
	}

	static get isReadOnlySupported() {
		return true
	}

	render() {
		this.wrapper = document.createElement('div')
		// Only render a live assignment when a concrete assignment ref exists.
		// Object.keys(this.data).length was true even for {assignment: ""}, which
		// let renderAssignment("") run and query submissions with an undefined
		// assignment filter — Frappe drops that filter and returns the member's
		// first submission (LIMIT 1), leaking Week 1's file into Week 2.
		if (this.data.assignment) {
			this.renderAssignment(this.data.assignment)
		} else {
			this.renderAssignmentModal()
		}
		return this.wrapper
	}

	renderAssignment(assignment) {
		// Guard: never resolve a submission without a concrete assignment.
		// An empty/undefined assignment filter is silently dropped by the
		// backend, returning some other submission (LIMIT 1) for this member
		// and leaking files across weeks.
		if (!assignment) {
			this.wrapper.innerHTML = `<div class="p-3 text-sm text-ink-gray-5">${__('This assignment is no longer available.')}</div>`
			return
		}
		if (this.readOnly) {
			const { userResource } = usersStore()

			// Resolve the current member's identifier. If userResource hasn't
			// loaded yet, fall back to frappe.session.user from the global
			// Frappe context. Never call get_value with an undefined member —
			// the filter would silently drop and the backend would return
			// some other user's submission (LIMIT 1), leaking files across
			// employees.
			const memberName =
				userResource.data?.name ||
				(typeof frappe !== 'undefined' ? frappe.session?.user : null)

			const loadSubmissionFor = (member) => {
				call('frappe.client.get_value', {
					doctype: 'LMS Assignment Submission',
					filters: {
						assignment: assignment,
						member: member,
					},
					fieldname: ['name'],
				}).then((data) => {
					let submission = data.name || 'new'
					const submissionPath = getLmsRoute(
						`assignment-submission/${assignment}/${submission}?fromLesson=1`
					)
					this.wrapper.innerHTML = `<iframe src="${submissionPath}" class="w-full h-[500px]"></iframe>`
				})
			}

			if (memberName) {
				loadSubmissionFor(memberName)
			} else if (userResource.fetch) {
				// User not loaded yet — fetch first, then render
				this.wrapper.innerHTML = `<div class="p-3 text-sm text-ink-gray-5">${__('Loading…')}</div>`
				userResource.fetch().then(() => {
					if (userResource.data?.name) {
						loadSubmissionFor(userResource.data.name)
					} else {
						this.wrapper.innerHTML = `<div class="p-3 text-sm text-ink-gray-5">${__('Please log in to view this assignment.')}</div>`
					}
				})
			} else {
				this.wrapper.innerHTML = `<div class="p-3 text-sm text-ink-gray-5">${__('Please log in to view this assignment.')}</div>`
			}
			return
		}
		call('frappe.client.get_value', {
			doctype: 'LMS Assignment',
			filters: {
				name: assignment,
			},
			fieldname: ['title'],
		}).then((data) => {
			this.wrapper.innerHTML = `<div class='border rounded-md p-4 text-center bg-surface-menu-bar mb-4'>
				<span class="font-medium">
					Assignment: ${data.title}
				</span>
			</div>`
			return
		})
	}

	renderAssignmentModal() {
		if (this.readOnly) {
			return
		}
		const app = createApp(AssessmentPlugin, {
			type: 'assignment',
			onAddition: (assignment) => {
				this.data.assignment = assignment
				this.renderAssignment(assignment)
			},
		})
		app.use(translationPlugin)
		app.use(router)
		app.mount(this.wrapper)
	}

	save() {
		if (Object.keys(this.data).length === 0) return {}
		return {
			assignment: this.data.assignment,
		}
	}
}
