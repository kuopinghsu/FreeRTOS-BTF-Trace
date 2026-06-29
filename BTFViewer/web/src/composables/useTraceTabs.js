import { ref, computed } from 'vue'

let _nextTabId = 1

function _emptyViewport() {
  return { timeStart: 0, timeEnd: 1, scrollY: 0, scrollX: 0, canvasW: 1, canvasH: 1 }
}

export function createTraceTab(name) {
  return {
    id: _nextTabId++,
    name: name || 'trace.btf',
    trace: null,
    cursors: [null, null, null, null],
    marks: [],
    markNextId: 1,
    pinnedHighlightKey: null,
    highlightSegment: null,
    timelineViewport: _emptyViewport(),
    cpuLoadExpanded: true,
    navCache: null,
    findQuery: '',
    findMode: 'contains',
    findHits: [],
    findHitIdx: -1,
    findMarkerNs: null,
    openPlot: null,
    scopeToCursors: true,
    statsSectionCollapsed: null,
    taskFilterText: '',
    migratedOnlyFilter: false,
    taskFilterKeys: null,
    heatmapFilterLabel: null,
  }
}

export function useTraceTabs() {
  const tabs = ref([])
  const activeTabId = ref(null)

  const activeTab = computed(
    () => tabs.value.find(t => t.id === activeTabId.value) ?? null,
  )

  const trace = computed(() => activeTab.value?.trace ?? null)

  const cursors = computed({
    get: () => activeTab.value?.cursors ?? [null, null, null, null],
    set: (v) => {
      if (activeTab.value) activeTab.value.cursors = v
    },
  })

  const marks = computed({
    get: () => activeTab.value?.marks ?? [],
    set: (v) => {
      if (activeTab.value) activeTab.value.marks = v
    },
  })

  const pinnedHighlightKey = computed({
    get: () => activeTab.value?.pinnedHighlightKey ?? null,
    set: (v) => {
      if (activeTab.value) activeTab.value.pinnedHighlightKey = v
    },
  })

  const highlightSegment = computed({
    get: () => activeTab.value?.highlightSegment ?? null,
    set: (v) => {
      if (activeTab.value) activeTab.value.highlightSegment = v
    },
  })

  const timelineViewport = computed(() => activeTab.value?.timelineViewport ?? _emptyViewport())

  const cpuLoadExpanded = computed({
    get: () => activeTab.value?.cpuLoadExpanded ?? true,
    set: (v) => {
      if (activeTab.value) activeTab.value.cpuLoadExpanded = v
    },
  })

  function findTabByName(name) {
    return tabs.value.find(t => t.name === name) ?? null
  }

  function openTab(name) {
    const existing = findTabByName(name)
    if (existing) {
      activeTabId.value = existing.id
      return existing
    }
    const tab = createTraceTab(name)
    tabs.value.push(tab)
    activeTabId.value = tab.id
    return tab
  }

  function closeTab(id) {
    const idx = tabs.value.findIndex(t => t.id === id)
    if (idx < 0) return
    tabs.value.splice(idx, 1)
    if (activeTabId.value === id) {
      const next = tabs.value[Math.min(idx, tabs.value.length - 1)]
      activeTabId.value = next?.id ?? null
    }
  }

  function cycleTraceTab(forward = true) {
    const list = tabs.value
    if (list.length < 2 || activeTabId.value == null) return
    const idx = list.findIndex(t => t.id === activeTabId.value)
    if (idx < 0) return
    const nxt = forward
      ? (idx + 1) % list.length
      : (idx - 1 + list.length) % list.length
    activeTabId.value = list[nxt].id
  }

  function resetTabForLoad(tab) {
    tab.trace = null
    tab.cursors = [null, null, null, null]
    tab.marks = []
    tab.markNextId = 1
    tab.pinnedHighlightKey = null
    tab.highlightSegment = null
    tab.navCache = null
    tab.cpuLoadExpanded = true
    tab.findHits = []
    tab.findHitIdx = -1
    tab.findMarkerNs = null
    tab.taskFilterText = ''
    tab.migratedOnlyFilter = false
    tab.taskFilterKeys = null
    tab.heatmapFilterLabel = null
    Object.assign(tab.timelineViewport, _emptyViewport())
  }

  function getNavCache(tab) {
    return tab?.navCache ?? null
  }

  function setNavCache(tab, cache) {
    if (tab) tab.navCache = cache
  }

  return {
    tabs,
    activeTabId,
    activeTab,
    trace,
    cursors,
    marks,
    pinnedHighlightKey,
    highlightSegment,
    timelineViewport,
    cpuLoadExpanded,
    openTab,
    closeTab,
    cycleTraceTab,
    resetTabForLoad,
    getNavCache,
    setNavCache,
  }
}
