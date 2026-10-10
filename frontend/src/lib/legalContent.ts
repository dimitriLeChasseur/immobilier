import { HOSTS, PROCESSORS, PUBLISHER } from './legal'
import { OFFERS, PRO_DAILY_ADDRESSES } from './pricing'
import { DATA_SOURCES } from './sources'

export interface LegalSection {
  heading: string
  /** Paragraphes ; une entrée commençant par « - » est rendue en liste. */
  paragraphs: string[]
}

export interface LegalDocument {
  title: string
  description: string
  updated: string
  sections: LegalSection[]
}

export type LegalKey = 'mentions' | 'cgv' | 'confidentialite'

const UPDATED = '10 octobre 2026'
const P = PUBLISHER

const mentions: LegalDocument = {
  title: 'Mentions légales',
  description: `Éditeur, hébergeurs et conditions d’utilisation du site ${P.siteName}.`,
  updated: UPDATED,
  sections: [
    {
      heading: 'Éditeur du site',
      paragraphs: [
        `Le site ${P.siteUrl} est édité par ${P.name}, ${P.legalForm}.`,
        `- Adresse : ${P.address}`,
        `- Immatriculation : ${P.registration}`,
        `- TVA : ${P.vat}`,
        `- Directeur de la publication : ${P.director}`,
        `- Contact : ${P.email}`,
      ],
    },
    {
      heading: 'Hébergement',
      paragraphs: HOSTS.map((host) => `- ${host.role} : ${host.name}, ${host.address}`),
    },
    {
      heading: 'Nature du service',
      paragraphs: [
        `${P.siteName} rassemble, pour une adresse ou une rue, des informations issues de données publiques : ventes immobilières, risques, urbanisme, bâtiment, écoles, environnement et vie de quartier.`,
        'Ces informations sont fournies à titre indicatif. Elles ne constituent ni un diagnostic technique, ni un état des risques réglementaire, ni un conseil juridique, fiscal ou en investissement. Elles ne remplacent ni la visite du bien, ni les diagnostics obligatoires remis par le vendeur, ni l’avis d’un professionnel.',
        'Les données proviennent de sources tierces qui peuvent être incomplètes, anciennes ou erronées. Le rapport signale les sources qui n’ont pas répondu, mais l’éditeur ne garantit pas l’exactitude ni l’exhaustivité des données publiques reprises.',
      ],
    },
    {
      heading: 'Sources des données',
      paragraphs: [
        `Les rapports s’appuient sur les sources suivantes : ${DATA_SOURCES}.`,
        'Les données cartographiques des points d’intérêt sont © les contributeurs d’OpenStreetMap, sous licence ODbL. Le fond de carte est le Plan IGN. L’indice de la qualité de l’air est publié par Atmo France et les associations agréées de surveillance de la qualité de l’air.',
        'Les données « Demandes de valeurs foncières » sont publiées par la Direction générale des finances publiques. Conformément à leurs conditions de réutilisation, les rapports qui les contiennent ne sont pas proposés à l’indexation par les moteurs de recherche.',
      ],
    },
    {
      heading: 'Propriété intellectuelle',
      paragraphs: [
        'La présentation du site, ses textes, sa mise en forme et les rapports générés sont protégés. Le rapport acheté peut être utilisé librement par son acquéreur pour ses besoins propres, et remis à ses clients dans le cadre de l’offre Pro. Sa revente ou sa rediffusion en masse n’est pas autorisée.',
        'Les données publiques reprises restent soumises aux licences de leurs producteurs.',
      ],
    },
  ],
}

function offerLine(id: (typeof OFFERS)[number]['id']): string {
  const offer = OFFERS.find((item) => item.id === id)
  return offer ? `- ${offer.name} : ${offer.price} ${offer.priceNote}. ${offer.description}` : ''
}

const cgv: LegalDocument = {
  title: 'Conditions générales de vente',
  description: `Offres, prix, paiement, droit de rétractation et responsabilité pour les audits vendus sur ${P.siteName}.`,
  updated: UPDATED,
  sections: [
    {
      heading: '1. Objet et vendeur',
      paragraphs: [
        `Les présentes conditions régissent la vente des audits et abonnements proposés sur ${P.siteUrl} par ${P.name} (${P.legalForm}, ${P.registration}), ci-après « le vendeur ».`,
        'Toute commande implique l’acceptation de ces conditions, dans leur version en vigueur au jour de la commande.',
      ],
    },
    {
      heading: '2. Offres et prix',
      paragraphs: [
        'Le service fournit un contenu numérique : le rapport d’audit complet d’une adresse française, consultable en ligne et exportable en PDF. Un aperçu gratuit est accessible avant tout achat.',
        offerLine('unit'),
        offerLine('pack'),
        offerLine('pro'),
        'Les prix sont indiqués en euros. Le prix applicable est celui affiché au moment de la commande.',
        'Les crédits du Pack Investisseur n’ont pas de date d’expiration tant que le compte existe. Ils ne sont ni cessibles ni remboursables une fois utilisés.',
      ],
    },
    {
      heading: '3. Commande et paiement',
      paragraphs: [
        'La commande nécessite un compte. Le paiement s’effectue par carte bancaire sur la page sécurisée de notre prestataire Stripe ; le vendeur n’a jamais accès aux coordonnées bancaires.',
        'La commande est définitive à la confirmation du paiement. Un reçu accompagné de la facture est envoyé par e-mail à l’adresse du compte.',
      ],
    },
    {
      heading: '4. Livraison',
      paragraphs: [
        'L’audit est débloqué immédiatement après confirmation du paiement, en général en quelques secondes. Il reste accessible depuis la rubrique « Mon compte ».',
        'Si une source publique ne répond pas au moment de la consultation, le rapport l’indique et la donnée est redemandée automatiquement lors d’une consultation ultérieure, sans frais.',
      ],
    },
    {
      heading: '5. Droit de rétractation',
      paragraphs: [
        'Le consommateur dispose en principe d’un délai de quatorze jours pour se rétracter d’un achat à distance.',
        'Toutefois, conformément à l’article L. 221-28 du Code de la consommation, ce droit ne peut pas être exercé pour un contenu numérique fourni immédiatement, dès lors que le consommateur a demandé l’exécution avant la fin du délai et reconnu qu’il perdait son droit de rétractation. En validant son paiement, l’acheteur demande expressément l’accès immédiat à l’audit et renonce à son droit de rétractation pour les audits débloqués.',
        'Les crédits non utilisés d’un Pack Investisseur peuvent être remboursés sur demande dans les quatorze jours suivant l’achat, au prorata des crédits restants.',
      ],
    },
    {
      heading: '6. Abonnement Pro',
      paragraphs: [
        'L’abonnement Pro est mensuel, sans engagement de durée, et renouvelé tacitement chaque mois. Il peut être résilié à tout moment depuis « Mon compte », rubrique « Gérer ou résilier ». La résiliation prend effet à la fin de la période déjà payée.',
        `L’abonnement ouvre l’audit complet de toute adresse, sans décompte de crédits, dans la limite de ${PRO_DAILY_ADDRESSES} adresses différentes par période de 24 heures. Cette limite protège le service et les sources publiques qu’il interroge ; les adresses déjà consultées restent accessibles une fois la limite atteinte. L’extraction automatisée des rapports est interdite.`,
        'La marque blanche permet d’apposer le nom, le logo et les coordonnées de l’abonné sur les rapports PDF. L’abonné est seul responsable des éléments qu’il y fait figurer et de l’usage qu’il fait des rapports auprès de ses clients. Les sources des données restent citées sur chaque rapport.',
      ],
    },
    {
      heading: '7. Garanties et responsabilité',
      paragraphs: [
        'Le vendeur est tenu de la garantie légale de conformité du contenu numérique (articles L. 224-25-12 et suivants du Code de la consommation) et de la garantie des vices cachés (articles 1641 et suivants du Code civil).',
        'Le service restitue des données publiques produites par des tiers. Le vendeur s’engage à les restituer fidèlement et à signaler celles qui manquent, mais ne garantit ni leur exactitude ni leur exhaustivité. Le rapport est une aide à la décision : il ne remplace ni la visite, ni les diagnostics obligatoires, ni le conseil d’un professionnel, et ne saurait fonder à lui seul une décision d’achat.',
        'La responsabilité du vendeur ne saurait excéder le montant payé pour la commande concernée, sauf faute lourde ou dispositions légales impératives contraires.',
      ],
    },
    {
      heading: '8. Réclamations et médiation',
      paragraphs: [
        `Toute réclamation peut être adressée à ${P.email}. Le vendeur s’efforce de répondre sous sept jours.`,
        `À défaut de solution amiable, le consommateur peut recourir gratuitement au médiateur de la consommation : ${P.mediator}. Il peut aussi utiliser la plateforme européenne de règlement en ligne des litiges.`,
      ],
    },
    {
      heading: '9. Droit applicable',
      paragraphs: [
        'Les présentes conditions sont soumises au droit français. Le consommateur conserve le bénéfice des dispositions impératives de la loi de son pays de résidence et peut saisir la juridiction de son domicile.',
      ],
    },
  ],
}

const confidentialite: LegalDocument = {
  title: 'Politique de confidentialité',
  description: `Données personnelles traitées par ${P.siteName}, finalités, durées de conservation et droits.`,
  updated: UPDATED,
  sections: [
    {
      heading: 'Responsable du traitement',
      paragraphs: [`Le responsable du traitement est ${P.name}, ${P.address}. Contact : ${P.email}.`],
    },
    {
      heading: 'Données traitées et finalités',
      paragraphs: [
        '- Sans compte : l’adresse recherchée est transmise à la Base Adresse Nationale pour l’autocomplétion et à notre serveur pour produire l’aperçu. Votre adresse IP est utilisée, en mémoire seulement, pour limiter le nombre de requêtes.',
        '- Compte : adresse e-mail et mot de passe (conservé sous forme d’empreinte irréversible), ou identifiant et e-mail fournis par Google si vous choisissez cette connexion. Finalité : vous authentifier et retrouver vos audits.',
        '- Achats : offre choisie, adresses débloquées, crédits, état de l’abonnement, identifiant client chez Stripe. Les coordonnées bancaires sont saisies chez Stripe et ne nous parviennent jamais.',
        '- Offre Pro : nom, logo et coordonnées professionnelles que vous choisissez d’apposer sur vos rapports.',
        '- E-mails : votre adresse sert à envoyer la confirmation de compte et les reçus. Aucune lettre d’information n’est envoyée.',
      ],
    },
    {
      heading: 'Bases légales',
      paragraphs: [
        'L’exécution du contrat pour le compte, les achats et la fourniture des audits ; nos obligations légales pour la conservation des factures ; notre intérêt légitime pour la sécurité du service et la prévention des abus.',
      ],
    },
    {
      heading: 'Cookies et stockage local',
      paragraphs: [
        'Le site n’utilise ni cookie publicitaire ni traceur tiers. La fréquentation est mesurée par Cloudflare Web Analytics, sans cookie, sans identifiant propre à votre navigateur et sans suivi d’un site à l’autre : seules des statistiques d’ensemble sont produites. Il enregistre dans votre navigateur ce qui est strictement nécessaire à son fonctionnement : votre session de connexion et, le temps de l’inscription et du paiement, l’adresse que vous souhaitez débloquer. Aucun consentement n’est requis pour ces usages.',
        'La page de paiement est hébergée par Stripe, qui dépose ses propres cookies de sécurité.',
        'Les formulaires de création de compte et de connexion peuvent être protégés par le défi anti-robot Cloudflare Turnstile, qui analyse des signaux techniques de votre navigateur pour distinguer un visiteur d’un automate, sans cookie publicitaire.',
      ],
    },
    {
      heading: 'Destinataires',
      paragraphs: [
        'Vos données ne sont ni vendues ni cédées. Elles sont traitées par les prestataires suivants, pour les seuls besoins indiqués :',
        ...PROCESSORS.map((processor) => `- ${processor.name} : ${processor.purpose}`),
        'Certains de ces prestataires sont établis aux États-Unis. Les transferts sont encadrés par le cadre de protection des données UE–États-Unis ou par les clauses contractuelles types de la Commission européenne.',
      ],
    },
    {
      heading: 'Durées de conservation',
      paragraphs: [
        '- Compte, audits débloqués et marque blanche : jusqu’à la suppression du compte.',
        '- Factures et pièces comptables : dix ans, conformément au Code de commerce.',
        '- Rapports mis en cache : sept jours ; ils ne contiennent pas de donnée personnelle.',
        '- Sauvegardes : quatorze jours sur le serveur et quatre-vingt-dix jours sur le stockage externe.',
      ],
    },
    {
      heading: 'Vos droits',
      paragraphs: [
        `Vous disposez d’un droit d’accès, de rectification, d’effacement, de limitation, d’opposition et de portabilité. Vous pouvez supprimer votre compte vous-même depuis « Mon compte ». Pour exercer vos autres droits, écrivez à ${P.email}. Une réponse vous est apportée sous un mois.`,
        'Vous pouvez introduire une réclamation auprès de la CNIL (www.cnil.fr).',
      ],
    },
    {
      heading: 'Sécurité',
      paragraphs: [
        'Les échanges sont chiffrés (HTTPS). Les mots de passe ne sont jamais conservés en clair. L’accès à la base de données est restreint et celle-ci n’est pas exposée sur Internet.',
      ],
    },
  ],
}

export const LEGAL_DOCUMENTS: Record<LegalKey, LegalDocument> = { mentions, cgv, confidentialite }
