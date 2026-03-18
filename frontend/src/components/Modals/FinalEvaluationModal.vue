<template>
	<Dialog
		v-model="show"
		:options="{
			title: __('Submit Final Evaluation'),
			size: 'xl',
			actions: [
				{
					label: __('Submit Evaluation'),
					variant: 'solid',
					loading: submitResource.loading,
					onClick: () => handleSubmit(),
				},
			],
		}"
	>
		<template #body-content>
			<div class="space-y-5 text-base">
				<!-- Intern header -->
				<div class="flex items-center space-x-3 pb-3 border-b">
					<Avatar :image="internImage" :label="internName" size="lg" />
					<div>
						<div class="font-semibold text-ink-gray-9">{{ internName }}</div>
						<div class="text-sm text-ink-gray-5">{{ intern }}</div>
					</div>
				</div>

				<!-- Course selector -->
				<FormControl
					v-model="selectedCourse"
					type="select"
					:label="__('Course')"
					:options="courseOptions"
				/>

				<!-- Loading template -->
				<div
					v-if="templateResource.loading"
					class="text-sm text-ink-gray-5 py-6 text-center"
				>
					{{ __('Loading evaluation template...') }}
				</div>

				<!-- No template configured -->
				<div
					v-else-if="selectedCourse && templateLoaded && !template"
					class="bg-surface-orange-1 text-ink-orange-3 text-sm p-3 rounded-md"
				>
					{{
						__(
							'No evaluation template is configured for this course. Ask an administrator to create one first.'
						)
					}}
				</div>

				<!-- Score table -->
				<div v-else-if="template && scores.length">
					<div class="text-sm font-medium text-ink-gray-7 mb-3">
						{{ __('Parameter Scores') }}
					</div>

					<div class="border rounded-lg overflow-hidden">
						<table class="w-full text-sm">
							<thead class="bg-surface-gray-2">
								<tr>
									<th
										class="text-left p-3 text-ink-gray-6 font-medium"
									>
										{{ __('Parameter') }}
									</th>
									<th
										class="text-center p-3 text-ink-gray-6 font-medium w-20"
									>
										{{ __('Weight') }}
									</th>
									<th
										class="text-center p-3 text-ink-gray-6 font-medium w-20"
									>
										{{ __('Max') }}
									</th>
									<th
										class="text-center p-3 text-ink-gray-6 font-medium w-32"
									>
										{{ __('Score') }}
									</th>
									<th
										class="text-center p-3 text-ink-gray-6 font-medium w-24"
									>
										{{ __('Weighted') }}
									</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="(row, idx) in scores"
									:key="idx"
									class="border-t"
								>
									<td class="p-3">
										<div class="font-medium text-ink-gray-9">
											{{ row.parameter_name }}
										</div>
										<div
											v-if="row.description"
											class="text-xs text-ink-gray-5 mt-0.5 leading-4"
										>
											{{ row.description }}
										</div>
									</td>
									<td class="p-3 text-center text-ink-gray-6">
										{{ row.weightage }}%
									</td>
									<td class="p-3 text-center text-ink-gray-6">
										{{ row.max_score }}
									</td>
									<td class="p-3 text-center">
										<input
											v-model.number="scores[idx].score"
											type="number"
											:min="0"
											:max="row.max_score"
											step="0.5"
											class="w-24 text-center border rounded-md px-2 py-1.5 text-ink-gray-9 text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-4"
											:class="{
												'border-red-400 bg-red-50': isScoreInvalid(row),
											}"
										/>
										<div
											v-if="isScoreInvalid(row)"
											class="text-xs text-red-500 mt-0.5"
										>
											{{ __('0 – {0}').format(row.max_score) }}
										</div>
									</td>
									<td
										class="p-3 text-center font-semibold"
										:class="
											row.score > 0
												? 'text-ink-gray-9'
												: 'text-ink-gray-4'
										"
									>
										{{ computeWeighted(row).toFixed(1) }}%
									</td>
								</tr>
							</tbody>
							<tfoot class="bg-surface-gray-2 border-t-2 border-outline-gray-2">
								<tr>
									<td
										colspan="4"
										class="p-3 text-right font-semibold text-ink-gray-9"
									>
										{{ __('Total Weighted Score') }}
									</td>
									<td
										class="p-3 text-center text-lg font-bold"
										:class="totalScoreColor"
									>
										{{ totalWeightedScore.toFixed(1) }}%
									</td>
								</tr>
							</tfoot>
						</table>
					</div>

					<!-- Comments -->
					<div class="mt-5">
						<div class="text-sm font-medium text-ink-gray-7 mb-1.5">
							{{ __('Evaluator Comments') }}
						</div>
						<textarea
							v-model="comments"
							rows="3"
							class="w-full border rounded-md px-3 py-2 text-sm text-ink-gray-9 focus:outline-none focus:ring-1 focus:ring-outline-gray-3 resize-none"
							:placeholder="__('Add overall feedback for the intern...')"
						></textarea>
					</div>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { Avatar, Dialog, FormControl, createResource, toast } from 'frappe-ui'
import { ref, computed, watch } from 'vue'

const show = defineModel()

const props = defineProps({
	intern: {
		type: String,
		required: true,
	},
	internName: {
		type: String,
		default: '',
	},
	internImage: {
		type: String,
		default: '',
	},
	batch: {
		type: String,
		required: true,
	},
})

const selectedCourse = ref('')
const scores = ref([])
const comments = ref('')
const template = ref(null)
const templateLoaded = ref(false)

// ── Batch courses ──────────────────────────────────────────────────────────
const coursesResource = createResource({
	url: 'lms.lms.api.evaluation.get_batch_courses_for_evaluation',
	makeParams() {
		return { batch: props.batch }
	},
	auto: true,
	onSuccess(data) {
		if (data?.length === 1) {
			selectedCourse.value = data[0].name
		}
	},
})

const courseOptions = computed(() => {
	const base = [{ label: __('Select a course'), value: '' }]
	if (!coursesResource.data) return base
	return [
		...base,
		...coursesResource.data.map((c) => ({ label: c.title, value: c.name })),
	]
})

// ── Template fetch ─────────────────────────────────────────────────────────
const templateResource = createResource({
	url: 'lms.lms.api.evaluation.get_template_for_course',
	makeParams() {
		return { course: selectedCourse.value }
	},
	onSuccess(data) {
		templateLoaded.value = true
		template.value = data || null
		scores.value = data?.parameters
			? data.parameters.map((p) => ({ ...p, score: 0 }))
			: []
	},
	onError() {
		templateLoaded.value = true
		template.value = null
		scores.value = []
	},
})

watch(selectedCourse, (course) => {
	template.value = null
	templateLoaded.value = false
	scores.value = []
	if (course) {
		templateResource.reload()
	}
})

// Reset form when dialog opens
watch(show, (val) => {
	if (val) {
		selectedCourse.value = ''
		template.value = null
		templateLoaded.value = false
		scores.value = []
		comments.value = ''
		coursesResource.reload()
	}
})

// ── Score helpers ──────────────────────────────────────────────────────────
const computeWeighted = (row) => {
	if (!row.score || !row.max_score) return 0
	return (row.score / row.max_score) * row.weightage
}

const totalWeightedScore = computed(() =>
	scores.value.reduce((sum, row) => sum + computeWeighted(row), 0)
)

const totalScoreColor = computed(() => {
	const s = totalWeightedScore.value
	if (s >= 75) return 'text-green-600'
	if (s >= 50) return 'text-orange-500'
	return 'text-red-500'
})

const isScoreInvalid = (row) =>
	row.score !== '' && (row.score < 0 || row.score > row.max_score)

// ── Submit ─────────────────────────────────────────────────────────────────
const submitResource = createResource({
	url: 'lms.lms.api.evaluation.submit_evaluation',
	makeParams() {
		return {
			intern: props.intern,
			course: selectedCourse.value,
			batch: props.batch,
			scores: scores.value,
			comments: comments.value,
		}
	},
})

const handleSubmit = () => {
	if (!selectedCourse.value) {
		toast.warning(__('Please select a course.'))
		return
	}
	if (!template.value) {
		toast.warning(__('No evaluation template found for this course.'))
		return
	}
	if (scores.value.some(isScoreInvalid)) {
		toast.warning(__('Please ensure all scores are within the allowed range.'))
		return
	}

	submitResource.submit(
		{},
		{
			onSuccess() {
				toast.success(__('Final evaluation submitted successfully.'))
				show.value = false
			},
			onError(err) {
				toast.error(
					err.messages?.[0] ||
						err.message ||
						__('Failed to submit evaluation.')
				)
			},
		}
	)
}
</script>
