<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'

import type { AuditTarget } from './api/audit'
import AddressSearch from './components/AddressSearch.vue'
import AuditDashboard from './components/AuditDashboard.vue'
import AuditStepper from './components/AuditStepper.vue'
import VisitChecklist from './components/VisitChecklist.vue'
import { useAudit } from './composables/useAudit'
import { buildReportSections, unavailableSources } from './lib/report'
import { DATA_SOURCES, SOURCE_INFO } from './lib/sources'
import { readTarget, writeTarget } from './lib/url'
import type { AddressSuggestion, SourceName } from './types/audit'

// Leaflet n'est chargé qu'à l'affichage du premier rapport.
const AuditMap = defineAsyncComponent(() => import('./components/AuditMap.vue'))

const { phase, location, sources, meta, errorMessage, sourceNames, start, reset } = useAudit()

const initial = readTarget(window.location.search)
const searchKey = ref(0)
const lastTarget = ref<AuditTarget | null>(null)
const checkedItems = ref<string[]>([])
const exporting = ref(false)
const exportFailed = ref(false)

const active = computed(() => phase.value !== 'idle')
const settled = computed(() => phase.value === 'done' || phase.value === 'error')
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
  window.history.replaceState(null, '', writeTarget(target, label))
  start(target)
}

function onSelect(suggestion: AddressSuggestion): void {
  run({ lat: suggestion.lat, lon: suggestion.lon, banId: suggestion.id }, suggestion.label)
}

function retry(): void {
  if (lastTarget.value) start(lastTarget.value)
}

function newSearch(): void {
  reset()
  lastTarget.value = null
  window.history.replaceState(null, '', window.location.pathname)
  searchKey.value += 1
}

async function exportPdf(): Promise<void> {
  if (!location.value) return
  exporting.value = true
  exportFailed.value = false
  try {
    // jsPDF (~400 Ko) n'est téléchargé qu'au premier export.
    const { buildReportPdf, collectCharts, reportFileName } = await import('./lib/pdf')
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

onMounted(() => {
  if (initial) run(initial, initial.label)
})
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center gap-3 px-4 py-4 sm:px-6">
        <img src="/favicon.svg" alt="" class="size-8" />
        <p class="text-base font-semibold text-slate-900">Audit Immobilier</p>
      </div>
    </header>

    <main class="mx-auto w-full max-w-6xl flex-1 px-4 pb-16 sm:px-6">
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
                <p class="text-xs font-medium tracking-wide text-brand-700 uppercase">Adresse auditée</p>
                <h1 v-if="location" class="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
                  {{ location.label }}
                </h1>
                <output v-else class="skeleton mt-3 block h-8 w-4/5" aria-label="Recherche de l’adresse"></output>
                <p v-if="location" class="mt-1 text-sm text-slate-500">Code INSEE {{ location.citycode }}</p>

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
              <p v-if="exportFailed" class="mt-3 text-sm text-rose-700" role="alert">
                Le PDF n’a pas pu être généré. Réessayez.
              </p>
            </div>

            <div class="lg:col-span-3">
              <AuditMap v-if="location" :lat="location.lat" :lon="location.lon" :label="location.label" />
              <output v-else class="skeleton block h-72 w-full rounded-2xl lg:h-80" aria-label="Chargement de la carte"></output>
            </div>
          </div>

          <AuditDashboard :sources="sources" :settled="settled" />
          <VisitChecklist v-model="checkedItems" class="mt-10" />
        </template>
      </template>
    </main>

    <footer class="border-t border-slate-200 bg-white">
      <p class="mx-auto max-w-6xl px-4 py-5 text-xs text-slate-500 sm:px-6">
        Données publiques : {{ DATA_SOURCES }}. Informations indicatives, sans valeur contractuelle.
      </p>
    </footer>
  </div>
</template>
