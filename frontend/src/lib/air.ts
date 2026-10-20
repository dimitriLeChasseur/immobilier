import type { ClimatAirEnergieData, EnergieResidentielTertiaire, EpisodesPollution } from '../types/audit'
import { capitalize, formatDate, formatDecimal, formatPercent } from './format'

/** Textes des épisodes de pollution et de l'inventaire du territoire, partagés par les cartes et le PDF. */

export interface EpisodesNotice {
  title: string
  /** Une ligne par polluant, du plus fréquent au plus rare. */
  lines: string[]
  detail: string
}

export interface EnergyRow {
  label: string
  local: string
  reference: string
}

type Rows = [string, string][]

const ENERGY_LABELS: Record<keyof EnergieResidentielTertiaire, string> = {
  electricite: 'Électricité',
  gaz: 'Gaz naturel',
  produits_petroliers: 'Fioul et autres produits pétroliers',
  bois: 'Bois',
  reseau_chaleur: 'Réseau de chaleur',
  autres: 'Autres énergies',
}
// Une énergie sous ce seuil des deux côtés n'apprend rien à l'acheteur.
const MIN_ENERGY_SHARE_PCT = 1

function days(count: number): string {
  return count === 1 ? '1 jour' : `${count} jours`
}

function alerts(count: number): string {
  return count ? `, dont ${count} en alerte` : ''
}

/**
 * Bilan des douze derniers mois. La plupart des régions ne publient que les jours d'épisode :
 * zéro n'y veut dire « aucun » que si la zone publie aussi ses jours sans dépassement.
 */
export function episodesNotice(episodes: EpisodesPollution): EpisodesNotice {
  const period = `du ${formatDate(episodes.debut)} au ${formatDate(episodes.fin)}`
  const zone = episodes.zone.nom ? `Zone ${episodes.zone.nom}, ${period}.` : `${capitalize(period)}.`
  const lines = episodes.par_polluant.map(
    (item) => `${capitalize(item.libelle)} : ${days(item.nb_jours)}${alerts(item.nb_jours_alerte)}`,
  )
  if (episodes.suivi_quotidien) {
    return {
      title: episodes.nb_jours
        ? `${days(episodes.nb_jours)} d’épisode de pollution en 12 mois${alerts(episodes.nb_jours_alerte)}`
        : 'Aucun épisode de pollution en 12 mois',
      lines,
      detail: `${zone} Suivi publié chaque jour par l’association régionale de surveillance de l’air.`,
    }
  }
  if (!episodes.nb_jours) {
    return {
      title: 'Aucun épisode de pollution publié en 12 mois',
      lines,
      detail:
        `${zone} L’association régionale de surveillance de l’air ne publie que les jours d’épisode : ` +
        'leur absence ne prouve pas que l’air soit resté sous les seuils.',
    }
  }
  return {
    title: `${days(episodes.nb_jours)} d’épisode de pollution en 12 mois${alerts(episodes.nb_jours_alerte)}`,
    lines,
    detail:
      `${zone} Jours d’épisode publiés par l’association régionale de surveillance de l’air ; ` +
      'son historique peut être incomplet.',
  }
}

function benchmark(reference: number | null, territory: string | undefined): string {
  return reference == null || !territory ? '' : ` (${territory} : ${formatDecimal(reference)} t)`
}

/** Émissions du territoire, chacune rapportée au repère métropolitain de la même année. */
export function climateRows(climate: ClimatAirEnergieData): Rows {
  const territory = climate.repere?.territoire
  const { ges, nox, pm2_5: pm25 } = climate
  const trend = ges.evolution_depuis_2018_pct
  const trendText =
    trend == null
      ? ''
      : `, en ${trend < 0 ? 'baisse' : 'hausse'} de ${formatPercent(Math.abs(trend))} depuis 2018`
  const perArea = (emission: ClimatAirEnergieData['nox']): string =>
    `${formatDecimal(emission.t_par_km2)} t par km²` +
    (emission.secteur_dominant ? `, premier secteur émetteur : ${emission.secteur_dominant.toLowerCase()}` : '') +
    benchmark(emission.repere_t_par_km2, territory)
  const rows: Rows = []
  if (ges.t_par_habitant != null) {
    rows.push([
      'Gaz à effet de serre',
      `${formatDecimal(ges.t_par_habitant)} t éq. CO₂ par habitant${trendText}` +
        benchmark(ges.repere_t_par_habitant, territory),
    ])
  }
  if (nox.t_par_km2 != null) rows.push(['Oxydes d’azote (NOx)', perArea(nox)])
  if (pm25.t_par_km2 != null) rows.push(['Particules fines (PM2.5)', perArea(pm25)])
  return rows
}

/** Énergies consommées par les logements et les bureaux du territoire, de la plus utilisée à la moins utilisée. */
export function energyRows(climate: ClimatAirEnergieData): EnergyRow[] {
  const shares = climate.energie_residentiel_tertiaire
  if (!shares) return []
  const reference = climate.repere?.energie_residentiel_tertiaire
  return (Object.keys(ENERGY_LABELS) as (keyof EnergieResidentielTertiaire)[])
    .filter((key) => Math.max(shares[key], reference?.[key] ?? 0) >= MIN_ENERGY_SHARE_PCT)
    .sort((a, b) => shares[b] - shares[a])
    .map((key) => ({
      label: ENERGY_LABELS[key],
      local: formatPercent(shares[key]),
      reference: formatPercent(reference?.[key]),
    }))
}
