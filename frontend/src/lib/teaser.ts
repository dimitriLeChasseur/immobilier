import type { SourceName } from '../types/audit'
import { formatInteger } from './format'

/** Valeur renvoyée par le serveur à la place d'une donnée réservée aux audits achetés. */
export const LOCKED = '***LOCKED***'

/** Vrai si les données d'une source contiennent au moins une valeur masquée par le serveur. */
export function isLocked(data: unknown): boolean {
  if (data === LOCKED) return true
  if (Array.isArray(data)) return data.some(isLocked)
  if (typeof data === 'object' && data !== null) return Object.values(data).some(isLocked)
  return false
}

/** Nombre lisible, ou null si la valeur est absente ou masquée. */
function count(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

type Data = Record<string, unknown>
type Hook = (data: Data) => string | null

function sentence(value: unknown, build: (n: number) => string): string | null {
  const n = count(value)
  return n === null ? null : build(n)
}

function poiTotal(data: Data): string | null {
  const categories = data.categories
  if (typeof categories !== 'object' || categories === null) return null
  const total = Object.values(categories as Record<string, { nb?: unknown }>).reduce(
    (sum, category) => sum + (count(category?.nb) ?? 0),
    0,
  )
  return `${formatInteger(total)} équipements repérés à moins de ${formatInteger(count(data.rayon_m))} m`
}

function riskCount(data: Data): string | null {
  const risks = data.risques
  return Array.isArray(risks) ? `${risks.length} risques recensés sur la commune` : null
}

function quarterName(data: Data): string | null {
  const iris = data.iris as { nom?: unknown } | null | undefined
  return typeof iris?.nom === 'string' ? `Revenus et profil du quartier « ${iris.nom} » analysés` : null
}

// Ce que l'on peut dire sans rien révéler : la preuve que l'analyse a eu lieu.
const HOOKS: Partial<Record<SourceName, Hook>> = {
  dvf: (d) =>
    sentence(d.nb_ventes, (n) =>
      d.perimetre === 'rue'
        ? `${formatInteger(n)} ventes analysées dans la rue`
        : `${formatInteger(n)} ventes analysées à moins de ${formatInteger(count(d.rayon_m))} m`,
    ),
  georisques: riskCount,
  reseau_mobile: (d) => sentence(d.nb_sites, (n) => `${formatInteger(n)} sites d’antennes repérés à proximité`),
  permis_construire: (d) => sentence(d.nb_permis, (n) => `${formatInteger(n)} autorisation(s) d’urbanisme en cours à proximité`),
  dpe: (d) => sentence(d.nb_dpe_analyses, (n) => `${formatInteger(n)} diagnostics énergétiques analysés`),
  proximite: poiTotal,
  loyers: (d) => sentence(d.nb_observations, (n) => `Loyer estimé à partir de ${formatInteger(n)} annonces`),
  connectivite: (d) => sentence(d.nb_locaux, (n) => `${formatInteger(n)} locaux analysés dans la commune`),
  delinquance: (d) => sentence(d.annee, (n) => `Statistiques ${n} de la commune analysées`),
  taxe_fonciere: (d) => sentence(d.annee, (n) => `Taux ${n} de la commune relevés`),
  quartier: quarterName,
}

const DEFAULT_HOOK = 'Analyse réalisée pour cette adresse'

/** Phrase d'accroche affichée au-dessus du contenu flouté d'une source verrouillée. */
export function teaserHook(source: SourceName, data: unknown): string {
  if (typeof data !== 'object' || data === null) return DEFAULT_HOOK
  return HOOKS[source]?.(data as Data) ?? DEFAULT_HOOK
}

// Ce que contient chaque carte verrouillée, dit sans rien révéler du résultat : la promesse
// remplace une mention générique répétée sur quinze cartes.
const LOCKED_PROMISES: Partial<Record<SourceName, string>> = {
  georisques: 'Sites Seveso, cavités et plans de prévention autour de l’adresse',
  permis_construire: 'Chantiers autorisés autour de l’adresse, avec leur nature',
  batiment: 'Année de construction, niveaux et étiquette énergie de l’immeuble',
  cadastre: 'Surface et références de la parcelle',
  urbanisme: 'Zonage du plan d’urbanisme et servitudes au point exact',
  dpe: 'Étiquette énergie la plus fréquente du voisinage, numéro par numéro',
  ensoleillement: 'Ensoleillement de l’adresse, été comme hiver',
  bruit: 'Bruit des routes et voies ferrées à l’adresse',
  proximite: 'Distance à pied de l’arrêt, du commerce et du soignant les plus proches',
  ecoles: 'Collège de secteur et niveau social (IPS) des écoles proches',
  marche_locatif: 'Locataires, logements vacants et permis de louer du quartier',
  quartier: 'Revenu médian et taux de pauvreté du quartier',
  reseau_mobile: 'Opérateurs et 5G des antennes proches',
  copropriete: 'Charges de copropriété estimées pour votre surface',
}

export function lockedPromise(source: SourceName): string {
  return LOCKED_PROMISES[source] ?? 'Détail dans l’audit complet'
}

/**
 * Silhouette affichée floutée sous une carte verrouillée : un dessin fixe, jamais tiré des
 * données (le serveur ne les envoie pas), qui laisse deviner la forme du résultat.
 */
export type GhostKind = 'scale' | 'meter' | 'tiles' | 'list'

const GHOSTS: Partial<Record<SourceName, GhostKind>> = {
  dpe: 'scale',
  batiment: 'tiles',
  bruit: 'meter',
  ensoleillement: 'tiles',
  quartier: 'tiles',
  cadastre: 'tiles',
  copropriete: 'tiles',
  marche_locatif: 'tiles',
}

export function lockedGhost(source: SourceName): GhostKind {
  return GHOSTS[source] ?? 'list'
}

function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count > 1 ? pluralForm : singular}`
}

/** « 2 alertes et 1 point fort » : le nombre de constats, seule partie lisible en aperçu. */
export function findingsCount(alerts: number, strengths: number): string {
  const alertText = alerts ? plural(alerts, 'alerte', 'alertes') : 'aucune alerte'
  const strengthText = strengths ? plural(strengths, 'point fort', 'points forts') : 'aucun point fort'
  return `${alertText} et ${strengthText}`
}
