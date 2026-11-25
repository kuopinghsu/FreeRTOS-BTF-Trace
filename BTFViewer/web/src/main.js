import { createApp } from 'vue'
import { UI_FONT_SIZE } from './config.js'
import { installAbortSignalPolyfills } from './utils/abortPolyfill.js'
import { installDomTooltips } from './utils/domTooltip.js'
import App from './App.vue'

// Eclipse's SWT browser (WebKitGTK 2.36 on Linux) lacks AbortSignal.throwIfAborted.
installAbortSignalPolyfills()

document.documentElement.style.setProperty('--ui-font-size', `${UI_FONT_SIZE}px`)
// In-DOM tips (native title tooltips are outside the page and miss tab capture).
installDomTooltips()

createApp(App).mount('#app')
