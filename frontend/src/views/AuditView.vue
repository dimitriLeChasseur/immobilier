<script setup lang="ts">
import { computed, defineAsyncComponent, h, onMounted, provide, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { AuditTarget } from '../api/audit'
import { unlockWithCredit } from '../api/billing'
import AddressSearch from '../components/AddressSearch.vue'
import AuditStepper from '../components/AuditStepper.vue'
import AuthModal from '../components/AuthModal.vue'
import DashboardPlaceholder from '../components/DashboardPlaceholder.vue'
import HeroPreview from '../components/HeroPreview.vue'
import HomeIntro from '../components/HomeIntro.vue'
import ReportNav from '../components/ReportNav.vue'
import StickyUnlockBar from '../components/StickyUnlockBar.vue'
import SynthesisPanel from '../components/SynthesisPanel.vue'
import SynthesisSkeleton from '../components/SynthesisSkeleton.vue'
import VisitChecklist from '../components/VisitChecklist.vue'
import { useAccount } from '../composables/useAccount'
import { useAudit } from '../composables/useAudit'
import { useAuth } from '../composables/useAuth'
import { usePaymentReturn } from '../composables/usePaymentReturn'
import { usePdfExport } from '../composables/usePdfExport'
import { communeSlug } from '../lib/commune'
import { DEMO_LABEL, DEMO_TARGET } from '../lib/demo'
import { mapMarkers } from '../lib/markers'
import { savePendingAudit } from '../lib/pending'
import { UNIT_PRICE } from '../lib/pricing'
import { findingsCount, LOCKED } from '../lib/teaser'
import { DEFAULT_DESCRIPTION, setPageMeta, SITE_NAME } from '../lib/seo'
import { SOURCE_INFO } from '../lib/sources'
import { UNLOCK_KEY } from '../lib/unlock'
import { readTarget, writeTarget } from '../lib/url'
import type { AddressSuggestion, SourceName } from '../types/audit'

// Leaflet, les cartes du rapport et leurs graphiques ne sont chargés qu'au premier rapport :
// l'accueil n'en a pas besoin. Leur place est tenue pendant le téléchargement, sans délai,
// pour que rien ne saute à leur arrivée.
const AuditDashboard = defineAsyncComponent({
  loader: () => import('../components/AuditDashboard.vue'),
  loadingComponent: DashboardPlaceholder,
  delay: 0,
})
const AuditMap = defineAsyncComponent({
  loader: () => import('../components/AuditMap.vue'),
  loadingComponent: {
    render: () => h('output', { class: 'skeleton block h-72 w-full rounded-2xl lg:h-80', 'aria-label': 'Chargement de la carte' }),
  },
  delay: 0,
})

const { phase, location, sources, meta, access, arrivalRank, errorMessage, sourceNames, start, reset } = useAudit()
const { user, accessToken, ready: authReady } = useAuth()
const { account, refresh: refreshAccount } = useAccount()
const router = useRouter()

const unlockError = ref<string | null>(null)

const initial = readTarget(window.location.search)
const searchKey = ref(0)
const lastTarget = ref<AuditTarget | null>(null)
const checkedItems = ref<string[]>([])
const authOpen = ref(false)
const lastLabel = ref('')
// Un audit, une instance du stepper : son minuteur repart de zéro à chaque lancement.
const auditRun = ref(0)

const active = computed(() => phase.value !== 'idle')
// La synthèse, calculée en fin de flux, a sa place réservée pendant le chargement.
const synthesisPending = computed(() => phase.value === 'loading')
// Sommaire : la synthèse n'y figure que si le rapport en a une, le cadastre n'a pas de section.
const reportSections = computed(() => [
  ...(meta.value?.synthese || synthesisPending.value ? [{ id: 'section-synthesis', label: 'Synthèse' }] : []),
  { id: 'section-market', label: 'Marché immobilier' },
  { id: 'section-risks', label: 'Risques et urbanisme' },
  { id: 'section-environment', label: 'Énergie et environnement' },
  { id: 'section-neighbourhood', label: 'Vie de quartier' },
  { id: 'section-checklist', label: 'Seconde visite' },
])
const settled = computed(() => phase.value === 'done' || phase.value === 'error')
// Version restreinte : le serveur n'a pas envoyé les valeurs réservées aux audits achetés.
// Annoncée dès la localisation : bandeau et bouton de déblocage sont en place avant les cartes.
const teaser = computed(() => access.value === 'teaser')
// Rapport d'exemple : complet, ouvert à tous, sans rapport avec un achat.
const demo = computed(() => access.value === 'demo')
const { paid, late: paymentLate } = usePaymentReturn(phase, teaser, () => retry())
const { exporting, exportFailed, exportPdf } = usePdfExport({ location, meta, sources, checkedItems }, teaser)
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
  auditRun.value += 1
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
  if (!lastTarget.value) return
  auditRun.value += 1
  start(lastTarget.value, accessToken.value)
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

// Barre collante de l'aperçu : elle reprend ce que l'audit a trouvé dès que la synthèse arrive.
const unlockButton = ref<HTMLElement | null>(null)
const stickySummary = computed(() => {
  const synthesis = meta.value?.synthese
  const findings = synthesis ? [...synthesis.alertes, ...synthesis.points_forts] : []
  if (!synthesis || !findings.some((item) => item.titre === LOCKED)) {
    return 'Prix des ventes voisines, bruit, bâtiment et synthèse de cette adresse'
  }
  return `Sur cette adresse : ${findingsCount(synthesis.alertes.length, synthesis.points_forts.length)}`
})
const stickyLabel = computed(() => (user.value && credits.value > 0 ? 'Débloquer (1 crédit)' : `Tout voir · ${UNIT_PRICE}`))

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

onMounted(() => {
  started = started || !initial
  // Pack ou abonnement acheté sans adresse : le compte affiché doit refléter l'achat.
  if (paid.value) void refreshAccount()
})
</script>

<template>
  <!-- En aperçu, la barre collante ne doit pas recouvrir la fin du rapport. -->
  <div :class="{ 'pb-24': teaser }">
      <!-- Accueil : texte et recherche à gauche, maquette du rapport à droite. Le champ de recherche
           garde le même parent une fois le rapport ouvert : il n'est pas recréé, sa saisie reste. -->
      <section
        :class="
          active
            ? 'py-6'
            : 'grid grid-cols-1 items-center gap-12 py-12 sm:py-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:py-20'
        "
      >
        <div>
          <div v-if="!active" class="mx-auto mb-8 max-w-2xl text-center lg:mx-0 lg:text-left">
            <h1 class="text-3xl font-semibold tracking-tight text-balance text-slate-900 sm:text-4xl lg:text-5xl">
              Ne signez pas avant d’avoir vu ce que l’annonce ne dit pas.
            </h1>
            <p class="mt-3 text-base text-slate-600">
              Audit immobilier d’une adresse en une dizaine de secondes : ventes réelles autour du bien,
              risques au point exact, bruit, diagnostics énergie du voisinage, permis en cours. Vingt bases
              publiques croisées.
            </p>
          </div>
          <output
            v-if="paid && !active"
            class="mx-auto mb-6 block max-w-2xl rounded-xl bg-emerald-50 px-4 py-3 text-center text-sm text-emerald-900 lg:mx-0"
          >
            Merci, votre paiement est enregistré. Recherchez une adresse pour lancer un audit complet.
          </output>
          <div class="mx-auto" :class="active ? 'max-w-none' : 'max-w-2xl lg:mx-0'">
            <AddressSearch :key="searchKey" :initial-label="initial?.label" @select="onSelect" />
          </div>
          <p v-if="!active" class="mx-auto mt-5 max-w-2xl text-center text-sm text-slate-600 lg:mx-0 lg:text-left">
            Aperçu gratuit, sans compte. Rapport complet : <strong class="font-semibold text-slate-900">{{ UNIT_PRICE }}</strong>,
            le prix d’un café en terrasse avant un engagement à 200 000 €.
            <button type="button" class="font-medium text-brand-700 underline hover:text-brand-900" @click="run(DEMO_TARGET, DEMO_LABEL)">
              Voir un rapport d’exemple
            </button>
          </p>
        </div>
        <HeroPreview v-if="!active" @demo="run(DEMO_TARGET, DEMO_LABEL)" />
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
                <!-- Titre et ligne d'identification : même hauteur que l'adresse qui les remplace. -->
                <output v-else class="mt-2 block" aria-label="Recherche de l’adresse">
                  <span class="skeleton block h-8 w-4/5"></span>
                  <span class="skeleton mt-1 block h-5 w-2/5"></span>
                </output>
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

                <!-- Gardé une fois l'audit terminé : sa disparition faisait remonter la page. Retiré sur
                     une coupure : il cocherait comme faites des étapes jamais reçues. -->
                <AuditStepper
                  v-if="phase !== 'error'"
                  :key="auditRun"
                  class="mt-5"
                  :located="location !== null"
                  :sources="sources"
                  :source-names="sourceNames"
                  :settled="phase === 'done'"
                />
                <p class="mt-5 min-h-5 text-sm text-slate-600" aria-live="polite">{{ statusText }}</p>
                <p v-if="phase === 'error'" class="mt-2 text-sm text-rose-700" role="alert">
                  La connexion a été interrompue : {{ errorMessage }}
                </p>
              </div>

              <div class="mt-6 flex flex-wrap gap-3">
                <button
                  v-if="teaser"
                  ref="unlockButton"
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
              !paymentLate
                ? 'Déblocage de l’audit en cours…'
                : 'La confirmation tarde : rechargez la page dans une minute. Vous ne serez pas débité deux fois.'
            }}
          </output>
          <p
            v-else-if="teaser"
            class="mb-6 rounded-2xl border border-brand-100 bg-brand-50 px-5 py-4 text-sm text-brand-900"
          >
            <strong class="font-semibold">Votre aperçu est prêt. L’essentiel est sous le voile.</strong>
            Les chiffres de la commune sont en clair ; ce qui est propre à cette adresse (prix réels des
            ventes voisines, rendement, bruit, bâtiment, synthèse) est dans l’audit complet :
            {{ UNIT_PRICE }}, PDF inclus.
          </p>
          <p
            v-else-if="demo"
            class="mb-6 rounded-2xl border border-brand-100 bg-brand-50 px-5 py-4 text-sm text-brand-900"
          >
            <strong class="font-semibold">Rapport d’exemple.</strong>
            Voici ce que contient un audit complet, ici sur une adresse de démonstration à Angers.
            Recherchez votre adresse pour obtenir le même rapport : {{ UNIT_PRICE }}.
          </p>
          <!-- Niveau d'accès pas encore annoncé : la place du bandeau d'aperçu, cas le plus courant, est tenue. -->
          <div v-else-if="access === null && phase === 'loading'" class="skeleton mb-6 h-18.5 rounded-2xl" aria-hidden="true"></div>

          <!-- La clé recrée le sommaire en fin de flux : il observe alors les sections définitives. -->
          <ReportNav :key="`${reportSections.length}-${settled}`" :sections="reportSections" />
          <SynthesisPanel v-if="meta?.synthese" id="section-synthesis" class="mb-10 scroll-mt-16" :synthesis="meta.synthese" />
          <SynthesisSkeleton v-else-if="synthesisPending" id="section-synthesis" class="mb-10 scroll-mt-16" :teaser="teaser" />
          <AuditDashboard :sources="sources" :settled="settled" :street="Boolean(location?.rue)" :arrival-rank="arrivalRank" />
          <VisitChecklist v-model="checkedItems" class="mt-10 scroll-mt-16" />
        </template>
      </template>

    <StickyUnlockBar v-if="teaser && !authOpen" :anchor="unlockButton" :summary="stickySummary" :label="stickyLabel" />
    <AuthModal v-model:open="authOpen" unlocking @authenticated="onAuthenticated" />
  </div>
</template>
