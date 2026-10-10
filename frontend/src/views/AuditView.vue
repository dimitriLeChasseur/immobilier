<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { AuditTarget } from '../api/audit'
import { fetchBranding, type Branding } from '../api/account'
import { unlockWithCredit } from '../api/billing'
import AddressSearch from '../components/AddressSearch.vue'
import AuditStepper from '../components/AuditStepper.vue'
import AuthModal from '../components/AuthModal.vue'
import HomeIntro from '../components/HomeIntro.vue'
import ReportNav from '../components/ReportNav.vue'
import SynthesisPanel from '../components/SynthesisPanel.vue'
import VisitChecklist from '../components/VisitChecklist.vue'
import { useAccount } from '../composables/useAccount'
import { useAudit } from '../composables/useAudit'
import { useAuth } from '../composables/useAuth'
import { communeSlug } from '../lib/commune'
import { DEMO_LABEL, DEMO_TARGET } from '../lib/demo'
import { mapMarkers } from '../lib/markers'
import { clearPendingAudit, savePendingAudit } from '../lib/pending'
import { UNIT_PRICE } from '../lib/pricing'
import { buildReportSections, synthesisSections, unavailableSources } from '../lib/report'
import { DEFAULT_DESCRIPTION, setPageMeta, SITE_NAME } from '../lib/seo'
import { SOURCE_INFO } from '../lib/sources'
import { UNLOCK_KEY } from '../lib/unlock'
import { readTarget, writeTarget } from '../lib/url'
import type { AddressSuggestion, SourceName } from '../types/audit'

// Leaflet, les cartes du rapport et leurs graphiques ne sont chargés qu'au premier rapport :
// l'accueil n'en a pas besoin.
const AuditDashboard = defineAsyncComponent(() => import('../components/AuditDashboard.vue'))
const AuditMap = defineAsyncComponent(() => import('../components/AuditMap.vue'))

const { phase, location, sources, meta, errorMessage, sourceNames, start, reset } = useAudit()
const { user, accessToken, ready: authReady } = useAuth()
const { account, refresh: refreshAccount } = useAccount()
const router = useRouter()

// Retour de la page de paiement : Stripe confirme l'achat au serveur en quelques secondes.
const PAYMENT_CHECKS = 6
const PAYMENT_CHECK_DELAY_MS = 2500
const paid = ref(new URLSearchParams(window.location.search).get('paiement') === 'ok')
let paymentChecks = 0
let paymentTimer: ReturnType<typeof setTimeout> | undefined
const unlockError = ref<string | null>(null)

const initial = readTarget(window.location.search)
const searchKey = ref(0)
const lastTarget = ref<AuditTarget | null>(null)
const checkedItems = ref<string[]>([])
const exporting = ref(false)
const exportFailed = ref(false)
const authOpen = ref(false)
const lastLabel = ref('')

const active = computed(() => phase.value !== 'idle')
// Sommaire : la synthèse n'y figure que si le rapport en a une, le cadastre n'a pas de section.
const reportSections = computed(() => [
  ...(meta.value?.synthese ? [{ id: 'section-synthesis', label: 'Synthèse' }] : []),
  { id: 'section-market', label: 'Marché immobilier' },
  { id: 'section-risks', label: 'Risques et urbanisme' },
  { id: 'section-environment', label: 'Énergie et environnement' },
  { id: 'section-neighbourhood', label: 'Vie de quartier' },
  { id: 'section-checklist', label: 'Contre-visite' },
])
const settled = computed(() => phase.value === 'done' || phase.value === 'error')
// Version restreinte : le serveur n'a pas envoyé les valeurs réservées aux audits achetés.
const teaser = computed(() => meta.value?.access === 'teaser')
// Rapport d'exemple : complet, ouvert à tous, sans rapport avec un achat.
const demo = computed(() => meta.value?.access === 'demo')
const credits = computed(() => account.value?.credits ?? 0)
const unlockLabel = computed(() => {
  // Le prix est annoncé avant la création de compte : personne ne s'inscrit pour le découvrir.
  if (!user.value) return `Débloquer l’audit complet pour ${UNIT_PRICE}`
  if (credits.value > 0) return `Débloquer avec 1 crédit (${credits.value} restants)`
  return `Débloquer l’audit complet pour ${UNIT_PRICE}`
})
// Ventes, écoles et permis placés sur la carte ; vide en aperçu gratuit (positions non transmises).
const markers = computed(() => mapMarkers(sources.value))
const statusText = computed(() => {
  // Pendant le chargement, les étapes affichées tiennent lieu de message d'état.
  if (!meta.value) return ''
  const origin = meta.value.cached ? 'Rapport récent repris du cache' : 'Rapport généré à l’instant'
  if (!meta.value.is_partial) return origin
  const failed = (meta.value.failed_sources ?? []).map((name) => SOURCE_INFO[name as SourceName]?.title ?? name)
  const detail = failed.length ? `sans réponse : ${failed.join(', ')}` : 'certaines sources n’ont pas répondu'
  return `${origin} · rapport partiel, ${detail}`
})

/** Le rapport d'une adresse n'est pas indexable (ventes DVF) et porte le nom de l'adresse. */
function markAsReport(label: string): void {
  setPageMeta({
    title: label ? `Audit immobilier : ${label} | ${SITE_NAME}` : `Audit immobilier | ${SITE_NAME}`,
    description: DEFAULT_DESCRIPTION,
    path: '/',
    noindex: true,
  })
}

function run(target: AuditTarget, label: string): void {
  markAsReport(label)
  checkedItems.value = []
  lastTarget.value = target
  lastLabel.value = label
  window.history.replaceState(null, '', writeTarget(target, label))
  start(target, accessToken.value)
}

function onSelect(suggestion: AddressSuggestion): void {
  // Une commune entière n'est pas une adresse : sa fiche est plus juste qu'un audit de son centre.
  if (suggestion.commune) {
    void router.push({
      name: 'commune',
      params: { slug: communeSlug(suggestion.commune.nom, suggestion.commune.code) },
    })
    return
  }
  run({ lat: suggestion.lat, lon: suggestion.lon, banId: suggestion.id }, suggestion.label)
}

function retry(): void {
  if (lastTarget.value) start(lastTarget.value, accessToken.value)
}

/** Dépense un crédit du pack pour cette adresse, puis redemande le rapport complet. */
async function spendCredit(token: string, address: AuditTarget & { label: string }): Promise<void> {
  unlockError.value = null
  try {
    account.value = await unlockWithCredit(token, address)
    retry()
  } catch (failure) {
    unlockError.value = failure instanceof Error ? failure.message : 'Le déblocage a échoué.'
  }
}

/** Débloque avec un crédit s'il en reste ; sinon mène au paiement, par la création de compte si nécessaire. */
function unlock(): void {
  if (!lastTarget.value) return
  const address = { ...lastTarget.value, label: location.value?.label ?? lastLabel.value }
  savePendingAudit(address)
  if (!user.value) authOpen.value = true
  else if (credits.value > 0 && accessToken.value) void spendCredit(accessToken.value, address)
  else void router.push({ name: 'pricing' })
}

function onAuthenticated(): void {
  authOpen.value = false
  void router.push({ name: 'pricing' })
}

provide(UNLOCK_KEY, { open: unlock, label: unlockLabel })

function newSearch(): void {
  reset()
  lastTarget.value = null
  window.history.replaceState(null, '', window.location.pathname)
  setPageMeta({
    title: `${SITE_NAME} : tout savoir sur une adresse avant d’acheter`,
    description: DEFAULT_DESCRIPTION,
    path: '/',
  })
  searchKey.value += 1
}

/** Marque blanche de l'abonné ; son absence ou une panne n'empêche jamais l'export. */
async function loadBranding(): Promise<Branding | null> {
  if (!accessToken.value || !account.value?.subscription_active) return null
  try {
    return await fetchBranding(accessToken.value)
  } catch {
    return null
  }
}

async function exportPdf(): Promise<void> {
  if (!location.value || teaser.value) return
  exporting.value = true
  exportFailed.value = false
  try {
    // jsPDF (~400 Ko) n'est téléchargé qu'au premier export.
    const { buildReportPdf, collectCharts, reportFileName } = await import('../lib/pdf')
    const unavailable = unavailableSources(sources.value).map(
      (name) => SOURCE_INFO[name as SourceName]?.title ?? name,
    )
    buildReportPdf({
      location: location.value,
      meta: meta.value,
      sections: [...synthesisSections(meta.value?.synthese), ...buildReportSections(sources.value)],
      charts: collectCharts(),
      unavailable,
      checkedItems: checkedItems.value,
      branding: await loadBranding(),
    }).save(reportFileName(location.value))
  } catch (error) {
    console.error('Export PDF impossible', error)
    exportFailed.value = true
  } finally {
    exporting.value = false
  }
}

// L'audit attend de savoir si une session existe : un acheteur reçoit d'emblée le rapport complet.
let started = false
watch(
  authReady,
  (isReady) => {
    if (isReady && !started && initial) {
      started = true
      run(initial, initial.label)
    }
  },
  { immediate: true },
)

// Connexion ou déconnexion en cours de consultation : le rapport est redemandé avec les bons droits.
watch(
  () => user.value?.id,
  (current, previous) => {
    if (current !== previous && lastTarget.value && phase.value !== 'idle') retry()
  },
)

// Après un paiement, le rapport est redemandé tant que la confirmation de Stripe n'est pas arrivée.
watch(phase, (current) => {
  if (current !== 'done') return
  if (!teaser.value) {
    paid.value = false
    clearPendingAudit()
  } else if (paid.value && paymentChecks < PAYMENT_CHECKS) {
    paymentChecks += 1
    paymentTimer = setTimeout(retry, PAYMENT_CHECK_DELAY_MS)
  }
})

onMounted(() => {
  started = started || !initial
  // Pack ou abonnement acheté sans adresse : le compte affiché doit refléter l'achat.
  if (paid.value) void refreshAccount()
})

onBeforeUnmount(() => clearTimeout(paymentTimer))
</script>

<template>
  <div>
      <section :class="active ? 'py-6' : 'py-14 sm:py-20'">
        <div v-if="!active" class="mx-auto mb-8 max-w-2xl text-center">
          <h1 class="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
            Tout savoir sur une adresse avant d’acheter
          </h1>
          <p class="mt-3 text-base text-slate-600">
            Prix des ventes voisines, risques, urbanisme, écoles et environnement, réunis en quelques
            secondes à partir des données publiques.
          </p>
        </div>
        <output
          v-if="paid && !active"
          class="mx-auto mb-6 block max-w-2xl rounded-xl bg-emerald-50 px-4 py-3 text-center text-sm text-emerald-900"
        >
          Merci, votre paiement est enregistré. Recherchez une adresse pour lancer un audit complet.
        </output>
        <div class="mx-auto" :class="active ? 'max-w-none' : 'max-w-2xl'">
          <AddressSearch :key="searchKey" :initial-label="initial?.label" @select="onSelect" />
        </div>
        <p v-if="!active" class="mx-auto mt-5 max-w-2xl text-center text-sm text-slate-600">
          Aperçu gratuit et sans compte. Audit complet avec export PDF : {{ UNIT_PRICE }} par adresse.
          <button type="button" class="font-medium text-brand-700 underline hover:text-brand-900" @click="run(DEMO_TARGET, DEMO_LABEL)">
            Voir un rapport d’exemple
          </button>
        </p>
      </section>

      <HomeIntro v-if="!active" @demo="run(DEMO_TARGET, DEMO_LABEL)" />

      <template v-if="active">
        <div
          v-if="phase === 'error' && !location"
          class="rounded-2xl border border-rose-200 bg-rose-50 p-6"
          role="alert"
        >
          <p class="font-medium text-rose-900">L’audit n’a pas pu démarrer</p>
          <p class="mt-1 text-sm text-rose-800">{{ errorMessage }}</p>
          <div class="mt-4 flex gap-3">
            <button
              type="button"
              class="rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium text-white hover:bg-rose-800"
              @click="retry"
            >
              Réessayer
            </button>
            <button
              type="button"
              class="rounded-lg px-4 py-2 text-sm font-medium text-rose-800 hover:bg-rose-100"
              @click="newSearch"
            >
              Nouvelle recherche
            </button>
          </div>
        </div>

        <template v-else>
          <div class="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-5">
            <div class="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
              <div>
                <p class="text-xs font-medium tracking-wide text-brand-700 uppercase">
                  {{ location?.rue ? 'Rue auditée' : 'Adresse auditée' }}
                </p>
                <h1 v-if="location" class="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
                  {{ location.label }}
                </h1>
                <output v-else class="skeleton mt-3 block h-8 w-4/5" aria-label="Recherche de l’adresse"></output>
                <p v-if="location" class="mt-1 text-sm text-slate-500">
                  Code INSEE {{ location.citycode }}<template v-if="location.rue">
                    · {{ location.rue.nb_numeros }} numéros · environ {{ location.rue.longueur_m }} m</template>
                </p>
                <p v-if="location?.voie_non_verifiee" class="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">
                  La rue n’a pas pu être identifiée (service d’adresses indisponible) : cette analyse porte
                  sur un seul point, pas sur la rue entière. Relancez l’audit dans un instant.
                </p>
                <p v-if="location?.rue" class="mt-3 rounded-xl bg-brand-50 px-3 py-2 text-sm text-brand-900">
                  Analyse de la rue entière : ventes et diagnostics énergie de ses numéros, zonages et
                  bruit le long de la voie. Les autres blocs sont calculés depuis son milieu.
                </p>

                <AuditStepper
                  v-if="phase === 'loading'"
                  class="mt-5"
                  :located="location !== null"
                  :sources="sources"
                  :source-names="sourceNames"
                />
                <p class="mt-5 text-sm text-slate-600" aria-live="polite">{{ statusText }}</p>
                <p v-if="phase === 'error'" class="mt-2 text-sm text-rose-700" role="alert">
                  La connexion a été interrompue : {{ errorMessage }}
                </p>
              </div>

              <div class="mt-6 flex flex-wrap gap-3">
                <button
                  v-if="teaser"
                  type="button"
                  class="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900"
                  @click="unlock"
                >
                  {{ unlockLabel }}
                </button>
                <button
                  v-else
                  type="button"
                  class="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="phase !== 'done' || exporting"
                  @click="exportPdf"
                >
                  {{ exporting ? 'Préparation…' : 'Exporter en PDF' }}
                </button>
                <button
                  v-if="phase === 'error'"
                  type="button"
                  class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  @click="retry"
                >
                  Relancer l’audit
                </button>
                <button
                  type="button"
                  class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  @click="newSearch"
                >
                  Nouvelle recherche
                </button>
              </div>
              <p v-if="unlockError" class="mt-3 text-sm text-rose-700" role="alert">{{ unlockError }}</p>
              <p v-if="exportFailed" class="mt-3 text-sm text-rose-700" role="alert">
                Le PDF n’a pas pu être généré. Réessayez.
              </p>
            </div>

            <div class="lg:col-span-3">
              <AuditMap
                v-if="location"
                :lat="location.lat"
                :lon="location.lon"
                :label="location.label"
                :street="location.rue?.points"
                :markers="markers"
              />
              <output v-else class="skeleton block h-72 w-full rounded-2xl lg:h-80" aria-label="Chargement de la carte"></output>
            </div>
          </div>

          <output
            v-if="teaser && paid"
            class="mb-6 block rounded-2xl border border-emerald-100 bg-emerald-50 px-5 py-4 text-sm text-emerald-900"
          >
            <strong class="font-semibold">Paiement reçu.</strong>
            {{
              paymentChecks < PAYMENT_CHECKS
                ? 'Déblocage de l’audit en cours…'
                : 'La confirmation tarde : rechargez la page dans une minute. Vous ne serez pas débité deux fois.'
            }}
          </output>
          <p
            v-else-if="teaser"
            class="mb-6 rounded-2xl border border-brand-100 bg-brand-50 px-5 py-4 text-sm text-brand-900"
          >
            <strong class="font-semibold">Aperçu gratuit.</strong>
            Les chiffres de la commune (loyers, taxe foncière, délinquance, fibre) et la qualité de l’air
            sont affichés en clair. Ce qui est propre à cette adresse (prix des ventes voisines, rendement,
            bâtiment, bruit, permis, synthèse) est réservé à l’audit complet, export PDF inclus :
            {{ UNIT_PRICE }}.
          </p>
          <p
            v-else-if="demo"
            class="mb-6 rounded-2xl border border-brand-100 bg-brand-50 px-5 py-4 text-sm text-brand-900"
          >
            <strong class="font-semibold">Rapport d’exemple.</strong>
            Voici ce que contient un audit complet, ici sur une adresse de démonstration à Angers.
            Recherchez votre adresse pour obtenir le même rapport : {{ UNIT_PRICE }}.
          </p>

          <!-- La clé recrée le sommaire quand la synthèse arrive : ses sections sont alors toutes dans la page. -->
          <ReportNav :key="reportSections.length" :sections="reportSections" />
          <SynthesisPanel v-if="meta?.synthese" id="section-synthesis" class="mb-10 scroll-mt-16" :synthesis="meta.synthese" />
          <AuditDashboard :sources="sources" :settled="settled" :street="Boolean(location?.rue)" />
          <VisitChecklist v-model="checkedItems" class="mt-10 scroll-mt-16" />
        </template>
      </template>

    <AuthModal v-model:open="authOpen" @authenticated="onAuthenticated" />
  </div>
</template>
