<template>
	<div class="flex flex-col h-full">
		<!-- Header -->
		<header
			class="sticky top-0 z-10 flex items-center justify-between border-b bg-surface-white px-3 py-2.5 sm:px-5"
		>
			<Breadcrumbs
				:items="[
					{ label: __('Courses'), route: { name: 'Courses' } },
					{ label: __('Bulk Upload Lessons') },
				]"
			/>
		</header>

		<div class="mx-auto w-full max-w-2xl px-4 py-8 space-y-6">
			<div class="text-lg font-semibold text-ink-gray-9">
				{{ __('Bulk Upload Lessons') }}
			</div>
			<div class="text-sm text-ink-gray-6">
				{{
					__(
						'Upload multiple files at once. Supported: MP4, MOV, PDF, PPT, PPTX, MP3, WAV, OGG, images.'
					)
				}}
			</div>

			<!-- Course selector -->
			<div class="space-y-1">
				<label class="block text-sm font-medium text-ink-gray-7">
					{{ __('Course') }}
					<span class="text-red-500">*</span>
				</label>
				<FormControl
					type="autocomplete"
					:options="courseOptions"
					:modelValue="selectedCourse"
					@update:modelValue="selectedCourse = $event ?? undefined"
					:placeholder="__('Select a course…')"
				/>
			</div>

			<!-- Chapter selector -->
			<div class="space-y-1">
				<label class="block text-sm font-medium text-ink-gray-7">
					{{ __('Chapter') }}
					<span class="text-red-500">*</span>
				</label>
				<FormControl
					type="autocomplete"
					:options="chapterOptions"
					:modelValue="selectedChapter"
					@update:modelValue="selectedChapter = $event ?? undefined"
					:placeholder="
						selectedCourse
							? __('Select a chapter…')
							: __('Select a course first')
					"
					:disabled="!selectedCourse || loadingChapters"
				/>
			</div>

			<!-- Upload mode toggle -->
			<div
				v-if="selectedChapterName"
				class="flex items-center space-x-3 rounded-md border bg-surface-gray-1 px-4 py-3"
			>
				<span class="text-sm font-medium text-ink-gray-7">
					{{ __('Upload mode:') }}
				</span>
				<label class="flex items-center space-x-2 cursor-pointer">
					<input
						type="radio"
						v-model="uploadMode"
						value="new_lesson"
						class="accent-blue-600"
					/>
					<span class="text-sm text-ink-gray-8">
						{{ __('Create new lesson per file') }}
					</span>
				</label>
				<label class="flex items-center space-x-2 cursor-pointer">
					<input
						type="radio"
						v-model="uploadMode"
						value="append_lesson"
						class="accent-blue-600"
					/>
					<span class="text-sm text-ink-gray-8">
						{{ __('Add to existing lesson') }}
					</span>
				</label>
			</div>

			<!-- Lesson selector (only in append mode) -->
			<div v-if="uploadMode === 'append_lesson' && selectedChapterName" class="space-y-1">
				<label class="block text-sm font-medium text-ink-gray-7">
					{{ __('Target Lesson') }}
					<span class="text-red-500">*</span>
				</label>
				<FormControl
					type="autocomplete"
					:options="lessonOptions"
					:modelValue="selectedLesson"
					@update:modelValue="selectedLesson = $event ?? undefined"
					:placeholder="
						loadingLessons ? __('Loading lessons…') : __('Select a lesson…')
					"
					:disabled="loadingLessons || lessonOptions.length === 0"
				/>
				<div v-if="!loadingLessons && lessonOptions.length === 0" class="text-xs text-ink-gray-4">
					{{ __('No lessons found in this chapter.') }}
				</div>
			</div>

			<!-- Drop zone -->
			<div
				class="border-2 border-dashed rounded-lg p-8 text-center transition-colors"
				:class="
					isDragging
						? 'border-blue-500 bg-blue-50'
						: 'border-outline-gray-3 hover:border-outline-gray-4'
				"
				@dragover.prevent="isDragging = true"
				@dragleave.prevent="isDragging = false"
				@drop.prevent="onDrop"
				@click="openFilePicker"
			>
				<input
					ref="fileInput"
					type="file"
					multiple
					accept="video/*,audio/*,.pdf,.ppt,.pptx,image/*"
					class="hidden"
					@change="onFilePicked"
				/>
				<div class="flex flex-col items-center space-y-2 text-ink-gray-5">
					<Upload class="size-8 stroke-1" />
					<div class="text-sm font-medium">
						{{ __('Drag & drop files here, or click to browse') }}
					</div>
					<div class="text-xs">
						{{ __('MP4, MOV, PDF, PPT, PPTX, MP3, WAV, OGG, JPG, PNG, GIF, WebP') }}
					</div>
				</div>
			</div>

			<!-- File list -->
			<div v-if="fileQueue.length" class="space-y-2">
				<div class="text-sm font-medium text-ink-gray-7">
					{{ __('Files') }} ({{ fileQueue.length }})
				</div>
				<div
					v-for="item in fileQueue"
					:key="item.id"
					class="flex items-center justify-between px-3 py-2 rounded-md border bg-surface-gray-1 text-sm"
				>
					<div class="flex items-center space-x-2 min-w-0">
						<component
							:is="fileIcon(item.ext)"
							class="size-4 shrink-0 stroke-1.5 text-ink-gray-5"
						/>
						<span class="truncate text-ink-gray-8">{{ item.name }}</span>
					</div>
					<div class="flex items-center space-x-2 shrink-0 ml-3">
						<!-- Status badge -->
						<span
							class="text-xs px-2 py-0.5 rounded-full font-medium"
							:class="statusClass(item.status)"
						>
							{{ __(item.status) }}
						</span>
						<!-- Remove button (only when pending) -->
						<button
							v-if="item.status === 'Pending'"
							@click.stop="removeFile(item.id)"
							class="text-ink-gray-4 hover:text-ink-red-3"
						>
							<X class="size-4 stroke-1.5" />
						</button>
						<!-- Error detail tooltip -->
						<Tooltip v-if="item.error" :text="item.error">
							<AlertCircle class="size-4 stroke-1.5 text-red-500 cursor-help" />
						</Tooltip>
					</div>
				</div>

				<!-- Inline error messages for failed files -->
				<div
					v-for="item in fileQueue.filter((f) => f.status === 'Error')"
					:key="'err-' + item.id"
					class="flex items-start space-x-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
				>
					<AlertCircle class="size-3.5 mt-0.5 shrink-0 stroke-1.5" />
					<span>
						<span class="font-medium">{{ item.name }}:</span>
						{{ item.error }}
					</span>
				</div>
			</div>

			<!-- Actions -->
			<div class="flex items-center justify-between">
				<Button
					v-if="fileQueue.length && !isRunning"
					variant="subtle"
					@click="clearAll"
				>
					{{ __('Clear All') }}
				</Button>
				<div class="ml-auto">
					<Button
						variant="solid"
						:disabled="!canStart"
						@click="startUpload"
					>
						<template #prefix>
							<Upload class="size-4 stroke-1.5" />
						</template>
						{{ isRunning ? __('Uploading…') : __('Start Upload') }}
					</Button>
				</div>
			</div>

			<!-- Summary -->
			<div
				v-if="isDone"
				class="rounded-md border p-4 space-y-1 text-sm"
				:class="summaryHasErrors ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'"
			>
				<div class="font-medium text-ink-gray-8">{{ __('Upload complete') }}</div>
				<div class="text-ink-gray-6">
					{{ doneCount }}
					{{
						uploadMode === 'append_lesson'
							? __('files added to lesson')
							: __('lessons created')
					}}
					<template v-if="errorCount > 0">
						· {{ errorCount }} {{ __('errors') }}
					</template>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import {
	Breadcrumbs,
	Button,
	FormControl,
	Tooltip,
	call,
	createListResource,
} from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import {
	AlertCircle,
	File,
	FileText,
	Image,
	Music,
	Upload,
	Video,
	X,
} from 'lucide-vue-next'

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const selectedCourse = ref(undefined)
const selectedChapter = ref(undefined)
const selectedLesson = ref(undefined)
const loadingChapters = ref(false)
const loadingLessons = ref(false)
const chapterOptions = ref([])
const lessonOptions = ref([])
const isDragging = ref(false)
const fileInput = ref(null)
const fileQueue = ref([]) // { id, name, ext, file: File, status, error }
const isRunning = ref(false)
const uploadMode = ref('new_lesson') // 'new_lesson' | 'append_lesson'

let _nextId = 1

// ---------------------------------------------------------------------------
// Course list
// ---------------------------------------------------------------------------

const courseList = createListResource({
	doctype: 'LMS Course',
	fields: ['name', 'title'],
	filters: { published: 1 },
	auto: true,
})

const courseOptions = computed(() =>
	(courseList.data || []).map((c) => ({ label: c.title, value: c.name }))
)

// frappe-ui autocomplete may set v-model to the full option object {label, value}
// or to the plain value string depending on version. Resolve defensively.
const selectedCourseName = computed(() =>
	typeof selectedCourse.value === 'object'
		? selectedCourse.value?.value ?? null
		: selectedCourse.value || null
)

const selectedChapterName = computed(() =>
	typeof selectedChapter.value === 'object'
		? selectedChapter.value?.value ?? null
		: selectedChapter.value || null
)

const selectedLessonName = computed(() =>
	typeof selectedLesson.value === 'object'
		? selectedLesson.value?.value ?? null
		: selectedLesson.value || null
)

// ---------------------------------------------------------------------------
// Chapter list (loaded on course change)
// ---------------------------------------------------------------------------

const onCourseChange = async () => {
	selectedChapter.value = undefined
	selectedLesson.value = undefined
	chapterOptions.value = []
	lessonOptions.value = []
	if (!selectedCourseName.value) return
	loadingChapters.value = true
	try {
		const chapters = await call(
			'lms.lms.bulk_upload.get_course_chapters',
			{ course: selectedCourseName.value }
		)
		chapterOptions.value = (chapters || []).map((ch) => ({
			label: ch.title,
			value: ch.name,
		}))
	} finally {
		loadingChapters.value = false
	}
}

watch(selectedCourse, onCourseChange)

// ---------------------------------------------------------------------------
// Lesson list (loaded on chapter change, only needed for append mode)
// ---------------------------------------------------------------------------

const onChapterChange = async () => {
	selectedLesson.value = undefined
	lessonOptions.value = []
	if (!selectedChapterName.value) return
	loadingLessons.value = true
	try {
		const lessons = await call(
			'lms.lms.bulk_upload.get_chapter_lessons',
			{ chapter: selectedChapterName.value }
		)
		lessonOptions.value = (lessons || []).map((l) => ({
			label: l.title,
			value: l.name,
		}))
	} finally {
		loadingLessons.value = false
	}
}

watch(selectedChapter, onChapterChange)

// Reset lesson selection when mode changes
watch(uploadMode, () => {
	selectedLesson.value = undefined
})

// ---------------------------------------------------------------------------
// File helpers
// ---------------------------------------------------------------------------

const ALLOWED = new Set([
	'mp4', 'mov', 'avi', 'mkv', 'webm',
	'mp3', 'wav', 'ogg',
	'pdf',
	'ppt', 'pptx',
	'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg',
])

const getExt = (name) => (name.includes('.') ? name.split('.').pop() : '').toLowerCase()

const fileIcon = (ext) => {
	if (['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) return Video
	if (['mp3', 'wav', 'ogg'].includes(ext)) return Music
	if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) return Image
	if (['ppt', 'pptx', 'pdf'].includes(ext)) return FileText
	return File
}

const statusClass = (status) => {
	const map = {
		Pending: 'bg-surface-gray-2 text-ink-gray-5',
		Uploading: 'bg-blue-100 text-blue-700',
		Converting: 'bg-yellow-100 text-yellow-700',
		Processing: 'bg-blue-100 text-blue-700',
		Done: 'bg-green-100 text-green-700',
		Error: 'bg-red-100 text-red-600',
	}
	return map[status] || 'bg-surface-gray-2 text-ink-gray-5'
}

const addFiles = (rawFiles) => {
	for (const f of Array.from(rawFiles)) {
		const ext = getExt(f.name)
		if (!ALLOWED.has(ext)) continue
		fileQueue.value.push({
			id: _nextId++,
			name: f.name,
			ext,
			file: f,
			status: 'Pending',
			error: null,
		})
	}
}

// ---------------------------------------------------------------------------
// Drop / pick
// ---------------------------------------------------------------------------

const openFilePicker = () => fileInput.value?.click()

const onFilePicked = (e) => {
	addFiles(e.target.files)
	e.target.value = ''
}

const onDrop = (e) => {
	isDragging.value = false
	if (e.dataTransfer?.files) addFiles(e.dataTransfer.files)
}

const removeFile = (id) => {
	fileQueue.value = fileQueue.value.filter((f) => f.id !== id)
}

const clearAll = () => {
	fileQueue.value = []
}

// ---------------------------------------------------------------------------
// Computed helpers
// ---------------------------------------------------------------------------

const canStart = computed(() => {
	if (!selectedCourseName.value) return false
	if (!selectedChapterName.value) return false
	if (fileQueue.value.length === 0) return false
	if (isRunning.value) return false
	if (uploadMode.value === 'append_lesson' && !selectedLessonName.value) return false
	return true
})

const isDone = computed(
	() =>
		fileQueue.value.length > 0 &&
		!isRunning.value &&
		fileQueue.value.every((f) => f.status === 'Done' || f.status === 'Error')
)

const doneCount = computed(() => fileQueue.value.filter((f) => f.status === 'Done').length)
const errorCount = computed(() => fileQueue.value.filter((f) => f.status === 'Error').length)
const summaryHasErrors = computed(() => errorCount.value > 0)

// ---------------------------------------------------------------------------
// Upload flow
// ---------------------------------------------------------------------------

const startUpload = async () => {
	if (!canStart.value) return
	isRunning.value = true

	// Process files sequentially so chapter idx ordering is predictable
	for (const item of fileQueue.value) {
		if (item.status !== 'Pending') continue

		// Step 1 — upload file to Frappe filesystem
		item.status = 'Uploading'
		let fileUrl, uploadedName
		try {
			const result = await uploadToFrappe(item.file)
			fileUrl = result.file_url
			uploadedName = result.file_name
		} catch (e) {
			item.status = 'Error'
			item.error = e.message || __('File upload failed')
			continue
		}

		// Step 2 — convert PPT / create or append lesson via backend
		const isPpt = ['ppt', 'pptx'].includes(item.ext)
		item.status = isPpt ? 'Converting' : 'Processing'
		try {
			let response
			if (uploadMode.value === 'append_lesson') {
				response = await call(
					'lms.lms.bulk_upload.append_file_to_lesson',
					{
						course: selectedCourseName.value,
						lesson_name: selectedLessonName.value,
						file_url: fileUrl,
						file_name: uploadedName || item.name,
					}
				)
			} else {
				response = await call(
					'lms.lms.bulk_upload.create_lesson_from_file',
					{
						course: selectedCourseName.value,
						chapter: selectedChapterName.value,
						file_url: fileUrl,
						file_name: uploadedName || item.name,
					}
				)
			}
			if (response?.status === 'Done') {
				item.status = 'Done'
			} else {
				item.status = 'Error'
				item.error = response?.message || __('Unknown error')
			}
		} catch (e) {
			item.status = 'Error'
			item.error = e.message || __('Lesson creation failed')
		}
	}

	isRunning.value = false
}

// ---------------------------------------------------------------------------
// Frappe file upload helper — with improved error surfacing
// ---------------------------------------------------------------------------

const uploadToFrappe = (file) => {
	// Check file size client-side before sending (max_file_size must be set to 2 GB in site config)
	const maxBytes = 2 * 1024 * 1024 * 1024
	if (file.size > maxBytes) {
		return Promise.reject(
			new Error(
				__('File is too large ({0} MB). Maximum allowed size is 2 GB.').format(
					(file.size / 1024 / 1024).toFixed(1)
				)
			)
		)
	}

	return new Promise((resolve, reject) => {
		const formData = new FormData()
		formData.append('file', file)
		formData.append('is_private', '0')

		fetch('/api/method/upload_file', {
			method: 'POST',
			headers: {
				'X-Frappe-CSRF-Token': window.csrf_token || '',
			},
			body: formData,
		})
			.then((res) => {
				if (res.status === 413)
					throw new Error(
						__('File is too large. The server rejected it. Check max_file_size in site config.')
					)
				if (!res.ok)
					throw new Error(__('Upload failed (HTTP {0})').format(res.status))
				return res.json()
			})
			.then((data) => {
				if (data.message?.file_url) {
					resolve(data.message)
				} else {
					// Extract the most meaningful error message from Frappe's response
					let msg = null
					try {
						if (data._server_messages) {
							const parsed = JSON.parse(data._server_messages)
							msg = parsed?.[0]?.message || parsed?.[0] || null
						}
					} catch (_) {}
					if (!msg && data.exception) msg = data.exception
					if (!msg && data.exc_type) msg = data.exc_type
					reject(new Error(msg || __('Upload failed')))
				}
			})
			.catch(reject)
	})
}
</script>
