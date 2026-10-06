import { createRouter, createWebHistory } from 'vue-router'

import AuditView from './views/AuditView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'audit', component: AuditView },
    // Chargée à la demande : la grille tarifaire n'alourdit pas la page d'audit.
    { path: '/tarifs', name: 'pricing', component: () => import('./views/PricingView.vue') },
    { path: '/:pathMatch(.*)*', redirect: { name: 'audit' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
