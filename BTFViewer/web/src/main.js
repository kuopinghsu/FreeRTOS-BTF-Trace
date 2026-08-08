import { createApp } from 'vue'
import { UI_FONT_SIZE } from './config.js'
import App from './App.vue'

document.documentElement.style.setProperty('--ui-font-size', `${UI_FONT_SIZE}px`)

createApp(App).mount('#app')
