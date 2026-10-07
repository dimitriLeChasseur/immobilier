import { createRouter, createWebHistory } from 'vue-router'

import { DEFAULT_DESCRIPTION, setPageMeta, SITE_NAME } from './lib/seo'
import AuditView from './views/AuditView.vue'

declare module 'vue-router' {
  interface RouteMeta {
    /** Titre et description de la page ; absents quand la vue les fixe elle-même. */
    title?: string
    description?: string
    /** Page personnelle : jamais indexée. */
    private?: boolean
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'audit',
      component: AuditView,
      meta: { title: `${SITE_NAME} : tout savoir sur une adresse avant d’acheter`, description: DEFAULT_DESCRIPTION },
    },
    // Chargée à la demande : la grille tarifaire n'alourdit pas la page d'audit.
    {
      path: '/tarifs',
      name: 'pricing',
      component: () => import('./views/PricingView.vue'),
      meta: {
        title: `Tarifs de l’audit immobilier | ${SITE_NAME}`,
        description:
          'Audit complet d’une adresse à 4,99 €, pack de 10 audits pour comparer plusieurs biens, ou abonnement ' +
          'professionnel illimité avec export PDF.',
      },
    },
    {
      path: '/communes',
      name: 'communes',
      component: () => import('./views/CommunesView.vue'),
      meta: {
        title: `Chiffres clés immobiliers par commune | ${SITE_NAME}`,
        description:
          'Taxe foncière, sécurité, écoles et logement des principales communes de France, à partir des données publiques.',
      },
    },
    {
      path: '/compte',
      name: 'account',
      component: () => import('./views/AccountView.vue'),
      meta: { title: `Mon compte | ${SITE_NAME}`, private: true },
    },
    // La fiche fixe elle-même ses balises, une fois la commune chargée.
    { path: '/commune/:slug', name: 'commune', component: () => import('./views/CommuneView.vue') },
    { path: '/:pathMatch(.*)*', redirect: { name: 'audit' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  if (!to.meta.title) return
  setPageMeta({
    title: to.meta.title,
    description: to.meta.description ?? DEFAULT_DESCRIPTION,
    path: to.path,
    // Le rapport d'une adresse (paramètres lat/lon) n'a pas vocation à être indexé : il contient
    // des ventes DVF, dont les conditions de réutilisation excluent l'indexation.
    noindex: 'lat' in to.query || to.meta.private === true,
  })
})
