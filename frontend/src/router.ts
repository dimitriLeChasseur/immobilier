import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { LEGAL_INCOMPLETE } from './lib/legal'
import { LEGAL_DOCUMENTS, type LegalKey } from './lib/legalContent'
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

// Pages légales : une même vue, trois documents. Elles ne sont proposées à l'indexation
// qu'une fois l'identité de l'éditeur complétée.
const LEGAL_PAGES: [path: string, name: string, key: LegalKey][] = [
  ['/mentions-legales', 'legal-notice', 'mentions'],
  ['/cgv', 'terms', 'cgv'],
  ['/confidentialite', 'privacy', 'confidentialite'],
]
const LEGAL_ROUTES: RouteRecordRaw[] = LEGAL_PAGES.map(([path, name, key]) => ({
  path,
  name,
  component: () => import('./views/LegalView.vue'),
  props: { document: key },
  meta: {
    title: `${LEGAL_DOCUMENTS[key].title} | ${SITE_NAME}`,
    description: LEGAL_DOCUMENTS[key].description,
    private: LEGAL_INCOMPLETE,
  },
}))

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
    {
      path: '/mot-de-passe',
      name: 'password',
      component: () => import('./views/ResetPasswordView.vue'),
      meta: { title: `Nouveau mot de passe | ${SITE_NAME}`, private: true },
    },
    ...LEGAL_ROUTES,
    // La fiche fixe elle-même ses balises, une fois la commune chargée.
    { path: '/commune/:slug', name: 'commune', component: () => import('./views/CommuneView.vue') },
    // L'hébergeur sert ces adresses avec le code 404 (404.html) : la vue le dit à l'écran.
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('./views/NotFoundView.vue'),
      meta: { title: `Page introuvable | ${SITE_NAME}`, private: true },
    },
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
