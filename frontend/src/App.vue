<template>
	<FrappeUIProvider>
		<Layout class="isolate text-base">
			<!-- Routes flagged with meta.remountOnParamChange (e.g. LessonForm) are
			     keyed by fullPath so switching between two lessons on the same route
			     remounts the component — a fresh editor + fresh fetch per lesson.
			     Without this, EditorJS state from the previous lesson bled into (and
			     autosaved onto) the next one. All other routes keep the default
			     no-key behaviour. -->
			<router-view v-slot="{ Component, route }">
				<component
					:is="Component"
					:key="route.meta.remountOnParamChange ? route.fullPath : undefined"
				/>
			</router-view>
		</Layout>
		<InstallPrompt v-if="isMobile && !settings.data?.disable_pwa" />
		<Dialogs />
	</FrappeUIProvider>
</template>
<script setup>
import { FrappeUIProvider } from 'frappe-ui'
import { Dialogs } from '@/utils/dialogs'
import { computed, onUnmounted, ref } from 'vue'
import { useScreenSize } from './utils/composables'
import { useSettings } from '@/stores/settings'
import { useRouter } from 'vue-router'
import DesktopLayout from './components/DesktopLayout.vue'
import MobileLayout from './components/MobileLayout.vue'
import NoSidebarLayout from './components/NoSidebarLayout.vue'
import InstallPrompt from './components/InstallPrompt.vue'

const { isMobile } = useScreenSize()
const router = useRouter()
const noSidebar = ref(false)
const { settings } = useSettings()

router.beforeEach((to, from, next) => {
	if (to.query.fromLesson || to.path === '/persona') {
		noSidebar.value = true
	} else {
		noSidebar.value = false
	}
	next()
})

const Layout = computed(() => {
	if (noSidebar.value) {
		return NoSidebarLayout
	}
	if (isMobile.value) {
		return MobileLayout
	}
	return DesktopLayout
})

onUnmounted(() => {
	noSidebar.value = false
})
</script>
