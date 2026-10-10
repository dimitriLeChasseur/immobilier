import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'
import './style.css'

const app = createApp(App).use(router)
// La page arrive parfois déjà écrite en HTML (accueil, tarifs, communes) : on ne la remplace
// qu'une fois la vue de la route chargée, pour ne pas afficher un écran vide entre les deux.
void router.isReady().then(() => app.mount('#app'))
