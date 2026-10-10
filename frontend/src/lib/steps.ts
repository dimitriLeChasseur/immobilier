import type { SourceName, SourceResults } from '../types/audit'

export type StepState = 'pending' | 'active' | 'done'

export interface AuditStep {
  key: string
  /** Libellé pendant le traitement, puis une fois terminé. */
  activeLabel: string
  doneLabel: string
  state: StepState
  /** Sources reçues / attendues pour cette étape. */
  received: number
  expected: number
}

interface StepDefinition {
  key: string
  activeLabel: string
  doneLabel: string
  sources: SourceName[]
}

// Regroupement des sources en étapes parlantes ; une source inconnue rejoint la dernière.
const DEFINITIONS: StepDefinition[] = [
  {
    key: 'market',
    activeLabel: 'Calcul du marché immobilier…',
    doneLabel: 'Marché immobilier calculé',
    sources: ['dvf', 'loyers', 'taxe_fonciere', 'copropriete', 'marche_locatif'],
  },
  {
    key: 'risks',
    activeLabel: 'Analyse des risques environnementaux…',
    doneLabel: 'Risques environnementaux analysés',
    sources: ['georisques', 'qualite_air', 'bruit', 'ensoleillement', 'dpe', 'batiment'],
  },
  {
    key: 'planning',
    activeLabel: 'Lecture du cadastre et de l’urbanisme…',
    doneLabel: 'Cadastre et urbanisme consultés',
    sources: ['cadastre', 'urbanisme', 'permis_construire'],
  },
  {
    key: 'neighbourhood',
    activeLabel: 'Exploration du quartier et des réseaux…',
    doneLabel: 'Quartier et réseaux explorés',
    sources: ['proximite', 'ecoles', 'delinquance', 'quartier', 'connectivite', 'reseau_mobile'],
  },
]

function stateOf(received: number, expected: number, started: boolean): StepState {
  if (received >= expected) return 'done'
  return started ? 'active' : 'pending'
}

/**
 * Étapes affichées pendant l'audit. Le géocodage vient d'abord ; les autres avancent en
 * parallèle, au rythme réel des réponses du serveur.
 */
export function buildSteps(
  located: boolean,
  sources: SourceResults,
  expectedSources: readonly SourceName[],
): AuditStep[] {
  const known = new Set(DEFINITIONS.flatMap((definition) => definition.sources))
  const orphans = expectedSources.filter((name) => !known.has(name))
  const steps: AuditStep[] = [
    {
      key: 'geocoding',
      activeLabel: 'Géocodage de l’adresse…',
      doneLabel: 'Adresse localisée',
      state: located ? 'done' : 'active',
      received: located ? 1 : 0,
      expected: 1,
    },
  ]
  DEFINITIONS.forEach((definition, index) => {
    const isLast = index === DEFINITIONS.length - 1
    const names = [...definition.sources, ...(isLast ? orphans : [])].filter((name) =>
      expectedSources.includes(name),
    )
    if (!names.length) return
    const received = names.filter((name) => sources[name] !== undefined).length
    steps.push({
      key: definition.key,
      activeLabel: definition.activeLabel,
      doneLabel: definition.doneLabel,
      state: stateOf(received, names.length, located),
      received,
      expected: names.length,
    })
  })
  return steps
}
