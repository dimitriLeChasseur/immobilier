import { jsPDF } from 'jspdf'
import autoTable from 'jspdf-autotable'

import type { AuditLocation, ReportMeta } from '../types/audit'
import { CHECKLIST_ITEMS, CHECKLIST_TITLE } from './checklist'
import { formatDate } from './format'
import type { ReportSection } from './report'
import { DATA_SOURCES } from './sources'

export interface ChartImage {
  title: string
  dataUrl: string
  /** largeur / hauteur */
  ratio: number
}

interface ReportInput {
  location: AuditLocation
  meta: ReportMeta | null
  sections: ReportSection[]
  charts: ChartImage[]
  /** Libellés des sources restées sans réponse. */
  unavailable: string[]
  /** Identifiants des points de la checklist déjà cochés par l'utilisateur. */
  checkedItems?: readonly string[]
  /** Marque blanche (offre Pro) : nom et logo du professionnel qui remet le rapport. */
  branding?: ReportBranding | null
}

export interface ReportBranding {
  company: string
  /** URL « data: » d'un PNG ou d'un JPEG, ou null sans logo. */
  logo: string | null
  /** Couleur du bandeau et des titres (« #rrggbb »). */
  color?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
  address?: string | null
}

type Rgb = [number, number, number]

/** « #1e40af » -> [30, 64, 175] ; null si la valeur n'est pas une couleur hexadécimale. */
export function hexToRgb(hex: string | null | undefined): Rgb | null {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex ?? '')
  if (!match) return null
  return [parseInt(match[1] ?? '', 16), parseInt(match[2] ?? '', 16), parseInt(match[3] ?? '', 16)]
}

/** Vrai si un texte blanc reste lisible sur cette couleur (luminance relative, WCAG). */
export function isDark([red, green, blue]: Rgb): boolean {
  const channel = (value: number) => {
    const ratio = value / 255
    return ratio <= 0.03928 ? ratio / 12.92 : ((ratio + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue) < 0.4
}

/** Coordonnées du professionnel sur une ligne, dans l'ordre où on les lit. */
export function contactLine(branding: ReportBranding): string {
  return [branding.company, branding.address, branding.phone, branding.email, branding.website]
    .filter((part): part is string => Boolean(part))
    .join(' - ')
}

const MARGIN = 15
const PAGE_BOTTOM = 274
const BRAND: Rgb = [15, 118, 110]
// Couleur d'accent du document en cours : celle de l'abonné en marque blanche, sinon la nôtre.
let accent: Rgb = BRAND
const MUTED: Rgb = [100, 116, 139]
const DARK_TEXT: Rgb = [15, 23, 42]
const WHITE: Rgb = [255, 255, 255]
const CHART_WIDTH = 85
const CHART_GAP = 10
const CHECKBOX_SIZE = 4.2
const CHECKLIST_TEXT_WIDTH = 165
const LOGO_MAX_WIDTH = 42
const LOGO_MAX_HEIGHT = 18

// Les polices standard du PDF ne connaissent pas ces caractères typographiques.
const REPLACEMENTS: [RegExp, string][] = [
  [/[   ]/g, ' '],
  [/[’‘]/g, "'"],
  [/[—–]/g, '-'],
  [/≈/g, '~'],
  [/…/g, '...'],
]

export function pdfSafe(text: string): string {
  return REPLACEMENTS.reduce((value, [pattern, replacement]) => value.replace(pattern, replacement), text)
}

function tableBottom(doc: jsPDF): number {
  return (doc as jsPDF & { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? MARGIN
}

function ensureRoom(doc: jsPDF, y: number, needed: number): number {
  if (y + needed <= PAGE_BOTTOM) return y
  doc.addPage()
  return MARGIN + 5
}

function drawHeader(doc: jsPDF, input: ReportInput): number {
  doc.setFillColor(...accent)
  doc.rect(0, 0, 210, 30, 'F')
  // Sur une couleur claire choisie par l'abonné, le texte passe en foncé pour rester lisible.
  doc.setTextColor(...(isDark(accent) ? WHITE : DARK_TEXT))
  doc.setFont('helvetica', 'bold').setFontSize(16)
  doc.text("Rapport d'audit immobilier", MARGIN, 13)
  doc.setFont('helvetica', 'normal').setFontSize(11)
  doc.text(pdfSafe(input.location.label), MARGIN, 21, { maxWidth: input.branding ? 130 : 180 })
  if (input.branding) drawBranding(doc, input.branding)

  doc.setTextColor(...MUTED).setFontSize(9)
  const generated = formatDate(input.meta?.generated_at ?? new Date().toISOString())
  doc.text(
    pdfSafe(`Généré le ${generated} - Code INSEE ${input.location.citycode} - ` +
      `${input.location.lat.toFixed(5)}, ${input.location.lon.toFixed(5)}`),
    MARGIN,
    37,
  )
  const contact = input.branding ? contactLine(input.branding) : ''
  if (!contact) return 45
  const lines = doc.splitTextToSize(pdfSafe(contact), 180) as string[]
  doc.text(lines, MARGIN, 42)
  return 46 + lines.length * 4
}

/** Logo de l'abonné dans un cartouche blanc, à droite du bandeau ; à défaut, son nom. */
function drawBranding(doc: jsPDF, branding: ReportBranding): void {
  const right = 210 - MARGIN
  if (branding.logo) {
    try {
      const { width, height } = doc.getImageProperties(branding.logo)
      const scale = Math.min(LOGO_MAX_WIDTH / width, LOGO_MAX_HEIGHT / height)
      const [w, h] = [width * scale, height * scale]
      doc.setFillColor(255, 255, 255)
      doc.roundedRect(right - w - 4, (30 - h) / 2 - 2, w + 4, h + 4, 1.5, 1.5, 'F')
      doc.addImage(branding.logo, right - w - 2, (30 - h) / 2, w, h)
      return
    } catch {
      // Logo illisible par le moteur PDF : le nom du professionnel en tient lieu.
    }
  }
  doc.setTextColor(...(isDark(accent) ? WHITE : DARK_TEXT)).setFont('helvetica', 'bold').setFontSize(11)
  doc.text(pdfSafe(branding.company), right, 13, { align: 'right', maxWidth: 55 })
}

function drawSection(doc: jsPDF, section: ReportSection, startY: number): number {
  let y = ensureRoom(doc, startY, 25)
  doc.setTextColor(...accent).setFont('helvetica', 'bold').setFontSize(12)
  doc.text(pdfSafe(section.title), MARGIN, y)
  y += 3

  autoTable(doc, {
    startY: y,
    margin: { left: MARGIN, right: MARGIN },
    theme: 'plain',
    styles: { fontSize: 9.5, cellPadding: 1.6 },
    columnStyles: { 0: { textColor: MUTED, cellWidth: 75 } },
    body: section.rows.map(([label, value]) => [pdfSafe(label), pdfSafe(value)]),
  })
  y = tableBottom(doc) + 3

  if (section.table?.body.length) {
    autoTable(doc, {
      startY: y,
      margin: { left: MARGIN, right: MARGIN },
      theme: 'striped',
      styles: { fontSize: 8.5, cellPadding: 1.5 },
      headStyles: { fillColor: accent },
      head: [section.table.head.map(pdfSafe)],
      body: section.table.body.map((row) => row.map(pdfSafe)),
    })
    y = tableBottom(doc) + 3
  }
  return y + 5
}

function drawCharts(doc: jsPDF, charts: ChartImage[], startY: number): number {
  if (!charts.length) return startY
  let y = ensureRoom(doc, startY, 70)
  doc.setTextColor(...accent).setFont('helvetica', 'bold').setFontSize(12)
  doc.text('Graphiques', MARGIN, y)
  y += 6

  charts.forEach((chart, index) => {
    const column = index % 2
    const height = CHART_WIDTH / chart.ratio
    if (column === 0) y = ensureRoom(doc, y, height + 12)
    const x = MARGIN + column * (CHART_WIDTH + CHART_GAP)
    doc.setTextColor(...MUTED).setFont('helvetica', 'normal').setFontSize(8.5)
    doc.text(pdfSafe(chart.title), x, y, { maxWidth: CHART_WIDTH })
    doc.addImage(chart.dataUrl, 'PNG', x, y + 3, CHART_WIDTH, height)
    if (column === 1 || index === charts.length - 1) y += height + 14
  })
  return y
}

function drawChecklist(doc: jsPDF, checkedItems: readonly string[], startY: number): number {
  const lineHeight = 4.6
  let y = ensureRoom(doc, startY, 20 + CHECKLIST_ITEMS.length * 12)
  doc.setTextColor(...accent).setFont('helvetica', 'bold').setFontSize(12)
  doc.text(pdfSafe(CHECKLIST_TITLE), MARGIN, y)
  y += 7

  for (const item of CHECKLIST_ITEMS) {
    const lines = doc.splitTextToSize(pdfSafe(item.label), CHECKLIST_TEXT_WIDTH) as string[]
    // Case à cocher dessinée : vide pour être remplie à la main, cochée si déjà vérifiée.
    doc.setDrawColor(...MUTED).setLineWidth(0.4)
    doc.rect(MARGIN, y - CHECKBOX_SIZE + 0.8, CHECKBOX_SIZE, CHECKBOX_SIZE)
    if (checkedItems.includes(item.id)) {
      doc.setDrawColor(...accent).setLineWidth(0.7)
      doc.line(MARGIN + 0.9, y - 1.3, MARGIN + 1.9, y - 0.2)
      doc.line(MARGIN + 1.9, y - 0.2, MARGIN + 3.6, y - 3)
    }
    doc.setTextColor(30, 41, 59).setFont('helvetica', 'normal').setFontSize(10)
    doc.text(lines, MARGIN + CHECKBOX_SIZE + 3, y)
    y += lines.length * lineHeight + 3
  }
  return y
}

function drawFooters(doc: jsPDF, branding?: ReportBranding | null): void {
  // Les sources restent citées : leurs licences l'exigent, marque blanche ou non.
  const author = branding ? `Rapport remis par ${branding.company}. ` : ''
  const pages = doc.getNumberOfPages()
  for (let page = 1; page <= pages; page += 1) {
    doc.setPage(page)
    doc.setTextColor(...MUTED).setFont('helvetica', 'normal').setFontSize(8)
    doc.text(
      pdfSafe(`${author}Sources : ${DATA_SOURCES}. Document informatif, sans valeur contractuelle.`),
      MARGIN,
      284,
      { maxWidth: 160 },
    )
    doc.text(`${page} / ${pages}`, 195, 284, { align: 'right' })
  }
}

export function buildReportPdf(input: ReportInput): jsPDF {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  accent = hexToRgb(input.branding?.color) ?? BRAND
  let y = drawHeader(doc, input)

  if (input.unavailable.length) {
    doc.setTextColor(180, 83, 9).setFont('helvetica', 'normal').setFontSize(9)
    const notice = `Rapport partiel. Sources sans réponse au moment de l'audit : ${input.unavailable.join(', ')}.`
    const lines = doc.splitTextToSize(pdfSafe(notice), 180) as string[]
    doc.text(lines, MARGIN, y)
    y += lines.length * 4.5 + 4
  }

  for (const section of input.sections) y = drawSection(doc, section, y)
  y = drawCharts(doc, input.charts, y)
  drawChecklist(doc, input.checkedItems ?? [], y)
  drawFooters(doc, input.branding)
  return doc
}

export function reportFileName(location: AuditLocation): string {
  const slug = location.label
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean)
    .join('-')
    .slice(0, 60)
  return `audit-${slug || 'adresse'}.pdf`
}

/** Images des graphiques affichés, prises directement sur leurs canevas. */
export function collectCharts(root: ParentNode = document): ChartImage[] {
  return [...root.querySelectorAll<HTMLCanvasElement>('canvas[data-pdf-chart]')]
    .filter((canvas) => canvas.width > 0 && canvas.height > 0)
    .map((canvas) => ({
      title: canvas.dataset.pdfChart ?? '',
      dataUrl: canvas.toDataURL('image/png'),
      ratio: canvas.width / canvas.height,
    }))
}
