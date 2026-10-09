/** Zone tendue et collège de secteur : libellés communs au tableau de bord et au PDF. */

import type { EcolesData, MarcheLocatifData } from '../types/audit'

type TenseZone = NonNullable<MarcheLocatifData['zone_tendue']>
type Sector = NonNullable<EcolesData['college_secteur']>

export interface Notice {
  title: string
  detail: string
}

const TENSE_ZONES: Record<TenseZone['categorie'], Notice> = {
  tendue: {
    title: 'Zone tendue',
    detail:
      'Préavis du locataire réduit à un mois, hausse de loyer encadrée lors d’une relocation ou d’un ' +
      'renouvellement de bail, taxe sur les logements vacants. La commune peut aussi majorer la taxe ' +
      'd’habitation des résidences secondaires.',
  },
  touristique: {
    title: 'Zone tendue (commune touristique)',
    detail:
      'Taxe sur les logements vacants applicable ; la commune peut majorer la taxe d’habitation des ' +
      'résidences secondaires. Le préavis réduit à un mois et l’encadrement des hausses de loyer visent ' +
      'les agglomérations de plus de 50 000 habitants : à vérifier sur le simulateur officiel.',
  },
  non_tendue: {
    title: 'Hors zone tendue',
    detail:
      'Préavis de trois mois pour une location vide ; la taxe sur les logements vacants ne s’applique pas.',
  },
}

export function tenseZoneNotice(zone: MarcheLocatifData['zone_tendue']): Notice | null {
  return zone ? (TENSE_ZONES[zone.categorie] ?? null) : null
}

function plural(count: number): string {
  return `${count} collège${count > 1 ? 's' : ''} public${count > 1 ? 's' : ''}`
}

/** Ce que la carte scolaire permet de dire pour cette adresse, sans aller au-delà. */
export function sectorNotice(sector: Sector): Notice {
  const count = sector.colleges.length
  const shared = count > 1 ? `Secteur partagé entre ${plural(count)}` : 'Collège public de secteur'
  switch (sector.statut) {
    case 'commune':
      return { title: shared, detail: 'Toute la commune relève de ce secteur.' }
    case 'adresse':
      return { title: shared, detail: 'D’après le numéro et la voie de cette adresse.' }
    case 'voie':
      return count > 1
        ? {
            title: `${plural(count)} selon le numéro dans la voie`,
            detail: 'La carte scolaire découpe cette voie par numéros : elle ne tranche pas pour ce point.',
          }
        : { title: 'Collège public de secteur', detail: 'Seul collège de secteur recensé pour cette voie.' }
    case 'indetermine':
      return {
        title: 'Collège de secteur non déterminé',
        detail:
          `Cette voie ne figure pas sous ce nom dans la carte scolaire ; la commune est partagée entre ` +
          `${plural(sector.nb_colleges_commune)}.`,
      }
    default:
      return {
        title: 'Collège de secteur non publié',
        detail: 'La carte scolaire de ce département ne figure pas dans le jeu de données national.',
      }
  }
}

export const SECTOR_CAVEAT =
  'Carte scolaire des collèges publics (ministère de l’Éducation nationale). L’affectation relève des ' +
  'services départementaux de l’Éducation nationale : à confirmer avant tout engagement.'
