import { computed, onScopeDispose, ref, shallowRef } from 'vue'

import { fetchSourceNames, openAuditStream, type AuditTarget } from '../api/audit'
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

/** État d'un audit alimenté au fil de l'eau par le flux du serveur. */
export function useAudit(dependencies: Partial<AuditDependencies> = {}) {
  const open = dependencies.open ?? openAuditStream
  const listSources = dependencies.listSources ?? fetchSourceNames

  const phase = ref<AuditPhase>('idle')
  const location = shallowRef<AuditLocation | null>(null)
  const sources = ref<SourceResults>({})
  const meta = shallowRef<ReportMeta | null>(null)
  const errorMessage = ref<string | null>(null)
  const sourceNames = ref<SourceName[]>(DEFAULT_SOURCES)

  let cancelStream: (() => void) | undefined

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

    cancelStream = open(target, {
      onLocation: (value) => {
        location.value = value
      },
      onSource: (name, result) => {
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
  }

  onScopeDispose(cancel)

  return { phase, location, sources, meta, errorMessage, sourceNames, progress, start, reset }
}
