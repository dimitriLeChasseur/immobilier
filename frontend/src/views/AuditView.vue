<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { AuditTarget } from '../api/audit'
import { unlockWithCredit } from '../api/billing'
import AddressSearch from '../components/AddressSearch.vue'
import AuditDashboard from '../components/AuditDashboard.vue'
import AuditStepper from '../components/AuditStepper.vue'
import AuthModal from '../components/AuthModal.vue'
import VisitChecklist from '../components/VisitChecklist.vue'
import { useAccount } from '../composables/useAccount'
import { useAudit } from '../composables/useAudit'
import { useAuth } from '../composables/useAuth'
import { clearPendingAudit, savePendingAudit } from '../lib/pending'
import { buildReportSections, unavailableSources } from '../lib/report'
import { SOURCE_INFO } from '../lib/sources'
import { UNLOCK_KEY } from '../lib/unlock'
import { readTarget, writeTarget } from '../lib/url'
import type { AddressSuggestion, SourceName } from '../types/audit'

// Leaflet n'est chargé qu'à l'affichage du premier rapport.
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
const settled = computed(() => phase.value === 'done' || phase.value === 'error')
// Version restreinte : le serveur n'a pas envoyé les valeurs réservées aux audits achetés.
const teaser = computed(() => meta.value?.access === 'teaser')
const credits = computed(() => account.value?.credits ?? 0)
const unlockLabel = computed(() => {
  if (!user.value) return 'Créer un compte pour débloquer l’audit complet de cette adresse'
  if (credits.value > 0) return `Débloquer avec 1 crédit (${credits.value} restants)`
  return 'Débloquer l’audit complet de cette adresse'
})
const statusText = computed(() => {
  // Pendant le chargement, les étapes affichées tiennent lieu de message d'état.
  if (!meta.value) return ''
  const origin = meta.value.cached ? 'Rapport récent repris du cache' : 'Rapport généré à l’instant'
  if (!meta.value.is_partial) return origin
  const failed = (meta.value.failed_sources ?? []).map((name) => SOURCE_INFO[name as SourceName]?.title ?? name)
  const detail = failed.length ? `sans réponse : ${failed.join(', ')}` : 'certaines sources n’ont pas répondu'
  return `${origin} · rapport partiel, ${detail}`
})

function run(target: AuditTarget, label: string): void {
  checkedItems.value = []
  lastTarget.value = target
  lastLabel.value = label
  window.history.replaceState(null, '', writeTarget(target, label))
  start(target, accessToken.value)
}

function onSelect(suggestion: AddressSuggestion): void {
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
  searchKey.value += 1
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
      sections: buildReportSections(sources.value),
      charts: collectCharts(),
      unavailable,
      checkedItems: checkedItems.value,
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
      <section :class="active ? 'py-6' : 'py-16 sm:py-24'">
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
      </section>

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
            L’analyse de cette adresse est terminée. Les résultats détaillés (prix, rendement, risques
            précis, antennes, bruit) sont réservés à l’audit complet, export PDF inclus.
          </p>

          <AuditDashboard :sources="sources" :settled="settled" :street="Boolean(location?.rue)" />
          <VisitChecklist v-model="checkedItems" class="mt-10" />
        </template>
      </template>

    <AuthModal v-model:open="authOpen" @authenticated="onAuthenticated" />
  </div>
</template>
