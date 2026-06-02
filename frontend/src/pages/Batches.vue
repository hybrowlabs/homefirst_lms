<template>
	<header
		class="sticky flex items-center justify-between top-0 z-10 border-b bg-surface-white px-3 py-2.5 sm:px-5"
	>
		<Breadcrumbs :items="breadcrumbs" />
		<Dropdown
			v-if="canCreateBatch()"
			:options="[
				{
					label: __('New Batch'),
					icon: 'users',
					onClick() {
						router.push({
							name: 'BatchForm',
							params: { batchName: 'new' },
						})
					},
				},
				{
					label: __('Import Batch'),
					icon: 'upload',
					onClick() {
						router.push({
							name: 'NewDataImport',
							params: { doctype: 'LMS Batch' },
						})
					},
				},
				{
					label: __('Import & Assign Users'),
					icon: 'user-plus',
					onClick() {
						router.push({ name: 'BatchImport' })
					},
				},
			]"
		>
			<template v-slot="{ open }">
				<Button variant="solid">
					<template #prefix>
						<Plus class="h-4 w-4 stroke-1.5" />
					</template>
					{{ __('Create') }}
					<template #suffix>
						<ChevronDown
							:class="[
								'w-4 h-4 stroke-1.5 ml-1 transform transition-transform',
								open ? 'rotate-180' : '',
							]"
						/>
					</template>
				</Button>
			</template>
		</Dropdown>
		<!-- <router-link
			v-if="canCreateBatch()"
			:to="{
				name: 'BatchForm',
				params: { batchName: 'new' },
			}"
		>
			<Button variant="solid">
				<template #prefix>
					<Plus class="h-4 w-4 stroke-1.5" />
				</template>
				{{ __('Create') }}
			</Button>
		</router-link> -->
	</header>
	<div class="p-5 pb-10">
		<div
			class="flex flex-col lg:flex-row space-y-4 lg:space-y-0 lg:items-center justify-between mb-5"
		>
			<div class="text-lg text-ink-gray-9 font-semibold">
				{{ __('All Batches') }}
			</div>
			<div
				class="flex flex-col space-y-3 lg:space-y-0 lg:flex-row lg:items-center lg:space-x-4"
			>
				<TabButtons
					v-if="user.data"
					:buttons="batchTabs"
					v-model="currentTab"
					class="w-fit"
				/>
				<div class="grid grid-cols-2 gap-2">
					<FormControl
						v-model="title"
						:placeholder="__('Search by Title')"
						type="text"
						class="min-w-40 lg:min-w-0 lg:w-32 xl:w-40"
						@input="updateBatches()"
					/>
					<div class="min-w-40 lg:min-w-0 lg:w-32 xl:w-40">
						<Select
							v-if="categories.length"
							v-model="currentCategory"
							:options="categories"
							:placeholder="__('Category')"
							@update:modelValue="updateBatches()"
						/>
					</div>
				</div>

				<FormControl
					v-model="certification"
					:label="__('Certification')"
					type="checkbox"
					@change="updateBatches()"
				/>
			</div>
		</div>
		<div
			v-if="(canShowBulkActions || canShowBulkUnarchive) && selectedBatches.size > 0"
			class="flex items-center justify-between mb-4 px-3 py-2 bg-surface-gray-2 rounded-md"
		>
			<div class="text-sm text-ink-gray-7">
				{{ selectedBatches.size }} {{ __('selected') }}
			</div>
			<div class="flex items-center space-x-2">
				<Button @click="clearSelection" :disabled="isArchiving">
					{{ __('Clear') }}
				</Button>
				<Button
					v-if="canShowBulkActions"
					variant="solid"
					@click="archiveSelected"
					:loading="isArchiving"
				>
					{{ __('Archive Selected') }}
				</Button>
				<Button
					v-if="canShowBulkUnarchive"
					variant="solid"
					@click="unarchiveSelected"
					:loading="isArchiving"
				>
					{{ __('Unarchive Selected') }}
				</Button>
			</div>
		</div>
		<div
			v-if="batches.data?.length"
			class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5"
		>
			<div
				v-for="batch in batches.data"
				:key="batch.name"
				class="relative"
			>
				<div
					v-if="canShowBulkActions || canShowBulkUnarchive"
					class="absolute top-2 left-2 z-10"
					@click.stop.prevent
				>
					<input
						type="checkbox"
						:checked="selectedBatches.has(batch.name)"
						@change="toggleBatchSelection(batch.name)"
						class="h-4 w-4 cursor-pointer accent-ink-gray-9"
						:aria-label="__('Select') + ' ' + batch.title"
					/>
				</div>
				<router-link
					:to="{ name: 'BatchDetail', params: { batchName: batch.name } }"
				>
					<BatchCard :batch="batch" />
				</router-link>
			</div>
		</div>
		<EmptyState v-else-if="!batches.list.loading" type="Batches" />

		<div
			v-if="!batches.list.loading && batches.hasNextPage"
			class="flex justify-center mt-5"
		>
			<Button @click="batches.next()">
				{{ __('Load More') }}
			</Button>
		</div>
	</div>
</template>
<script setup>
import {
	Breadcrumbs,
	Button,
	call,
	createListResource,
	Dropdown,
	FormControl,
	Select,
	TabButtons,
	usePageMeta,
} from 'frappe-ui'
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronDown, Plus } from 'lucide-vue-next'
import { sessionStore } from '@/stores/session'
import BatchCard from '@/components/BatchCard.vue'
import EmptyState from '@/components/EmptyState.vue'

const user = inject('$user')
const dayjs = inject('$dayjs')
const { brand } = sessionStore()
const start = ref(0)
const pageLength = ref(20)
const categories = ref([])
const currentCategory = ref(null)
const title = ref('')
const certification = ref(false)
const filters = ref({})
const orFilters = ref({})
const is_student = computed(() => user.data?.is_student)
const currentTab = ref(is_student.value ? 'all' : 'upcoming')
const orderBy = ref('start_date')
const readOnlyMode = window.read_only_mode
const router = useRouter()

const selectedBatches = ref(new Set())
const isArchiving = ref(false)

const isModerator = computed(
	() =>
		user.data?.is_moderator ||
		user.data?.is_instructor ||
		user.data?.is_evaluator
)

const canShowBulkActions = computed(
	() => isModerator.value && currentTab.value !== 'archived'
)

const canShowBulkUnarchive = computed(
	() => isModerator.value && currentTab.value === 'archived'
)

const toggleBatchSelection = (name) => {
	const next = new Set(selectedBatches.value)
	if (next.has(name)) {
		next.delete(name)
	} else {
		next.add(name)
	}
	selectedBatches.value = next
}

const clearSelection = () => {
	selectedBatches.value = new Set()
}

const archiveSelected = async () => {
	if (selectedBatches.value.size === 0 || isArchiving.value) return
	isArchiving.value = true
	try {
		await call('lms.lms.api.batch_actions.archive_batches', {
			batch_names: Array.from(selectedBatches.value),
		})
		clearSelection()
		updateBatches()
	} catch (e) {
		console.error('Archive failed:', e)
	} finally {
		isArchiving.value = false
	}
}

const unarchiveSelected = async () => {
	if (selectedBatches.value.size === 0 || isArchiving.value) return
	isArchiving.value = true
	try {
		await call('lms.lms.api.batch_actions.unarchive_batches', {
			batch_names: Array.from(selectedBatches.value),
		})
		clearSelection()
		updateBatches()
	} catch (e) {
		console.error('Unarchive failed:', e)
	} finally {
		isArchiving.value = false
	}
}

onMounted(() => {
	setFiltersFromQuery()
	updateBatches()
	categories.value = [
		{
			label: '',
			value: null,
		},
	]
})

const setFiltersFromQuery = () => {
	let queries = new URLSearchParams(location.search)
	title.value = queries.get('title') || ''
	currentCategory.value = queries.get('category') || null
	certification.value = queries.get('certification') || false
}

const batches = createListResource({
	doctype: 'LMS Batch',
	url: 'lms.lms.utils.get_batches',
	cache: ['batches', user.data?.name],
	pageLength: pageLength.value,
	start: start.value,
})

const setCategories = (data) => {
	let allCategories = data.map((batch) => batch.category)
	allCategories = allCategories.filter(
		(category, index) => allCategories.indexOf(category) === index && category
	)
	if (categories.value.length <= allCategories.length) {
		updateCategories(data)
	}
}

const updateBatches = () => {
	updateFilters()
	batches.update({
		filters: filters.value,
		or_filters: orFilters.value,
		orderBy: orderBy.value,
	})
	batches.reload().then((data) => {
		setCategories(data)
	})
}

const updateFilters = () => {
	updateCategoryFilter()
	updateTitleFilter()
	updateCertificationFilter()
	updateTabFilter()
	updateStudentFilter()
	setQueryParams()
}

const updateCategoryFilter = () => {
	if (currentCategory.value) {
		filters.value['category'] = currentCategory.value
	} else {
		delete filters.value['category']
	}
}

const updateTitleFilter = () => {
	if (title.value) {
		filters.value['title'] = ['like', `%${title.value}%`]
	} else {
		delete filters.value['title']
	}
}

const updateCertificationFilter = () => {
	if (certification.value) {
		filters.value['certification'] = 1
	} else {
		delete filters.value['certification']
	}
}

const updateTabFilter = () => {
	orderBy.value = 'start_date'
	// Reset or_filters on every tab change — archived is the only tab that uses it
	orFilters.value = {}
	if (!user.data) {
		return
	}
	if (currentTab.value == 'enrolled' && is_student.value) {
		filters.value['enrolled'] = 1
		delete filters.value['start_date']
		delete filters.value['published']
		orderBy.value = 'start_date desc'
	} else if (is_student.value) {
		delete filters.value['enrolled']
	} else {
		delete filters.value['start_date']
		delete filters.value['published']
		delete filters.value['end_date']
		orderBy.value = 'start_date desc'
		if (currentTab.value == 'upcoming') {
			filters.value['start_date'] = ['>=', dayjs().format('YYYY-MM-DD')]
			filters.value['published'] = 1
			orderBy.value = 'start_date'
		} else if (currentTab.value == 'archived') {
			// Match either manually archived OR auto-archived (end_date passed).
			// `end_date` is not set as an AND filter here so that batches
			// without an end_date can still show up via custom_is_archived.
			orFilters.value = {
				custom_is_archived: 1,
				end_date: ['<=', dayjs().format('YYYY-MM-DD')],
			}
		} else if (currentTab.value == 'unpublished') {
			filters.value['published'] = 0
		}
	}
}

const updateStudentFilter = () => {
	if (!user.data) {
		filters.value['start_date'] = ['>=', dayjs().format('YYYY-MM-DD')]
		filters.value['published'] = 1
	} else if (is_student.value && currentTab.value != 'enrolled') {
		// Hide completed batches (end_date passed) for students
		filters.value['published'] = 1
		delete filters.value['start_date']
		filters.value['end_date'] = ['>=', dayjs().format('YYYY-MM-DD')]
	}
}

const setQueryParams = () => {
	let queries = new URLSearchParams(location.search)
	let filterKeys = {
		title: title.value,
		category: currentCategory.value,
		certification: certification.value,
	}

	Object.keys(filterKeys).forEach((key) => {
		if (filterKeys[key]) {
			queries.set(key, filterKeys[key])
		} else {
			queries.delete(key)
		}
	})

	history.replaceState(
		{},
		'',
		`${location.pathname}${queries.size > 0 ? `?${queries.toString()}` : ''}`
	)
}

const updateCategories = (data) => {
	data.forEach((batch) => {
		if (
			batch.category &&
			!categories.value.find((category) => category.value === batch.category)
		)
			categories.value.push({
				label: batch.category,
				value: batch.category,
			})
	})
}

watch(currentTab, () => {
	clearSelection()
	updateBatches()
})

const batchTabs = computed(() => {
	let tabs = [
		{
			label: __('All'),
			value: 'all',
		},
	]

	if (
		user.data?.is_moderator ||
		user.data?.is_instructor ||
		user.data?.is_evaluator
	) {
		tabs.push({ label: __('Upcoming'), value: 'upcoming' })
		tabs.push({ label: __('Archived'), value: 'archived' })
		tabs.push({ label: __('Unpublished'), value: 'unpublished' })
	} else if (user.data) {
		tabs.push({ label: __('Enrolled'), value: 'enrolled' })
	}
	return tabs
})

const canCreateBatch = () => {
	if (readOnlyMode) return false
	if (
		user.data?.is_moderator ||
		user.data?.is_instructor ||
		user.data?.is_evaluator
	)
		return true
	return false
}

const breadcrumbs = computed(() => [
	{
		label: __('Batches'),
		route: { name: 'Batches' },
	},
])

usePageMeta(() => {
	return {
		title: __('Batches'),
		icon: brand.favicon,
	}
})
</script>
