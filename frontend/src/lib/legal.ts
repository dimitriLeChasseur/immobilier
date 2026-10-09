/**
 * Identité de l'éditeur et prestataires, repris dans les pages légales.
 *
 * Les champs marqués TODO ne peuvent être renseignés que par l'éditeur : tant qu'il en reste,
 * les pages affichent « à compléter » et ne sont pas proposées à l'indexation.
 */

export const TODO = 'à compléter'

export const PUBLISHER = {
  siteName: 'Audit Immobilier',
  siteUrl: 'https://audit-immobilier.fr',
  /** Nom et prénom (entrepreneur individuel) ou dénomination sociale. */
  name: TODO,
  /** Forme juridique : « Entrepreneur individuel », « SAS au capital de … », etc. */
  legalForm: TODO,
  /** Adresse du siège ou du domicile professionnel. */
  address: TODO,
  /** Numéro SIREN ou SIRET, et ville du RCS le cas échéant. */
  registration: TODO,
  /** Numéro de TVA intracommunautaire, ou « TVA non applicable, art. 293 B du CGI ». */
  vat: TODO,
  /** Directeur de la publication. */
  director: TODO,
  /** Adresse de contact relevée par l'éditeur. */
  email: TODO,
  /** Médiateur de la consommation auquel l'éditeur a adhéré (nom et site). */
  mediator: TODO,
} as const

/** Vrai tant qu'une information obligatoire manque. */
export const LEGAL_INCOMPLETE = Object.values(PUBLISHER).includes(TODO)

export const HOSTS = [
  { role: 'Site web', name: 'Cloudflare, Inc.', address: '101 Townsend Street, San Francisco, CA 94107, États-Unis' },
  { role: 'Serveur applicatif et base de données', name: 'Contabo GmbH', address: 'Aschauer Straße 32a, 81549 Munich, Allemagne' },
] as const

/** Sous-traitants qui reçoivent des données personnelles, et pourquoi. */
export const PROCESSORS = [
  { name: 'Contabo GmbH (Allemagne)', purpose: 'hébergement de l’application et de la base de données' },
  { name: 'Cloudflare, Inc. (États-Unis)', purpose: 'diffusion du site, noms de domaine et stockage chiffré des sauvegardes' },
  { name: 'Stripe Payments Europe, Ltd. (Irlande)', purpose: 'paiement par carte, facturation et gestion des abonnements' },
  { name: 'Resend, Inc. (États-Unis, envoi depuis l’Irlande)', purpose: 'envoi des e-mails de confirmation de compte et des reçus' },
  { name: 'Google Ireland Limited', purpose: 'connexion « Continuer avec Google », si vous la choisissez' },
] as const
