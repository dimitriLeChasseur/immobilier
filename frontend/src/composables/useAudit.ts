import { computed, onScopeDispose, ref, shallowRef } from 'vue'

import { fetchSourceNames, openAuditStream, type AuditAccess, type AuditTarget } from '../api/audit'
import type { AuditLocation, ReportMeta, SourceName, SourceResults } from '../types/audit'

export type AuditPhase = 'idle' | 'loading' | 'done' | 'error'

/** Ordre d'affichage par défaut, utilisé tant que le serveur n'a pas fourni sa liste. */
export const DEFAULT_SOURCES: SourceName[] = [
  'georisques',
  'cadastre',
  'urbanisme',
  'dvf',
  'dpe',
  'batiment',
  'proximite',
  'qualite_air',
  'ensoleillement',
  'loyers',
  'delinquance',
  'taxe_fonciere',
  'ecoles',
  'permis_construire',
  'marche_locatif',
  'quartier',
  'connectivite',
  'copropriete',
  'reseau_mobile',
  'bruit',
]

interface AuditDependencies {
  open: typeof openAuditStream
  listSources: typeof fetchSourceNames
}

// Sources reçues à moins de cet intervalle : une rafale (rapport repris du cache), que
// l'interface fait apparaître en cascade plutôt que d'un bloc.
const BURST_GAP_MS = 50

/** État d'un audit alimenté au fil de l'eau par le flux du serveur. */
export function useAudit(dependencies: Partial<AuditDependencies> = {}) {
  const open = dependencies.open ?? openAuditStream
  const listSources = dependencies.listSources ?? fetchSourceNames

  const phase = ref<AuditPhase>('idle')
  const location = shallowRef<AuditLocation | null>(null)
  const sources = ref<SourceResults>({})
  const meta = shallowRef<ReportMeta | null>(null)
  const errorMessage = ref<string | null>(null)
  const announcedAccess = ref<AuditAccess | null>(null)
  // Rang de chaque source dans sa rafale d'arrivée : 0 pour une source arrivée seule.
  const arrivalRank = ref<Partial<Record<SourceName, number>>>({})
  let lastArrival = Number.NEGATIVE_INFINITY
  let burst = 0
  const sourceNames = ref<SourceName[]>(DEFAULT_SOURCES)

  let cancelStream: (() => void) | undefined

  // Connu dès la localisation ; un serveur antérieur à l'évènement ne le donne qu'à la fin.
  const access = computed<AuditAccess | null>(() => announcedAccess.value ?? meta.value?.access ?? null)

  const receivedCount = computed(() => Object.keys(sources.value).length)
  const progress = computed(() =>
    sourceNames.value.length ? receivedCount.value / sourceNames.value.length : 0,
  )

  // La liste du serveur fait foi (une source peut être ajoutée sans redéployer le frontend).
  listSources()
    .then((names) => {
      if (names.length) sourceNames.value = names
    })
    .catch(() => undefined)

  function cancel(): void {
    cancelStream?.()
    cancelStream = undefined
  }

  function start(target: AuditTarget, accessToken?: string | null): void {
    cancel()
    phase.value = 'loading'
    location.value = null
    sources.value = {}
    meta.value = null
    errorMessage.value = null
    announcedAccess.value = null
    arrivalRank.value = {}
    lastArrival = Number.NEGATIVE_INFINITY

    cancelStream = open(target, {
      onLocation: (value) => {
        location.value = value
      },
      onAccess: (value) => {
        announcedAccess.value = value
      },
      onSource: (name, result) => {
        const now = performance.now()
        burst = now - lastArrival < BURST_GAP_MS ? burst + 1 : 0
        lastArrival = now
        arrivalRank.value = { ...arrivalRank.value, [name]: burst }
        sources.value = { ...sources.value, [name]: result }
      },
      onDone: (value) => {
        meta.value = value
        phase.value = 'done'
      },
      onError: (message) => {
        errorMessage.value = message
        phase.value = 'error'
      },
    }, accessToken)
  }

  function reset(): void {
    cancel()
    phase.value = 'idle'
    location.value = null
    sources.value = {}
    meta.value = null
    errorMessage.value = null
    announcedAccess.value = null
  }

  onScopeDispose(cancel)

  return { phase, location, sources, meta, access, arrivalRank, errorMessage, sourceNames, progress, start, reset }
}
