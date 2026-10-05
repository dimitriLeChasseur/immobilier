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
}

const MARGIN = 15
const PAGE_BOTTOM = 274
const BRAND: [number, number, number] = [15, 118, 110]
const MUTED: [number, number, number] = [100, 116, 139]
const CHART_WIDTH = 85
const CHART_GAP = 10
const CHECKBOX_SIZE = 4.2
const CHECKLIST_TEXT_WIDTH = 165

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
  doc.setFillColor(...BRAND)
  doc.rect(0, 0, 210, 30, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold').setFontSize(16)
  doc.text("Rapport d'audit immobilier", MARGIN, 13)
  doc.setFont('helvetica', 'normal').setFontSize(11)
  doc.text(pdfSafe(input.location.label), MARGIN, 21)

  doc.setTextColor(...MUTED).setFontSize(9)
  const generated = formatDate(input.meta?.generated_at ?? new Date().toISOString())
  doc.text(
    pdfSafe(`Généré le ${generated} - Code INSEE ${input.location.citycode} - ` +
      `${input.location.lat.toFixed(5)}, ${input.location.lon.toFixed(5)}`),
    MARGIN,
    37,
  )
  return 45
}

function drawSection(doc: jsPDF, section: ReportSection, startY: number): number {
  let y = ensureRoom(doc, startY, 25)
  doc.setTextColor(...BRAND).setFont('helvetica', 'bold').setFontSize(12)
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
      headStyles: { fillColor: BRAND },
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
  doc.setTextColor(...BRAND).setFont('helvetica', 'bold').setFontSize(12)
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
  doc.setTextColor(...BRAND).setFont('helvetica', 'bold').setFontSize(12)
  doc.text(pdfSafe(CHECKLIST_TITLE), MARGIN, y)
  y += 7

  for (const item of CHECKLIST_ITEMS) {
    const lines = doc.splitTextToSize(pdfSafe(item.label), CHECKLIST_TEXT_WIDTH) as string[]
    // Case à cocher dessinée : vide pour être remplie à la main, cochée si déjà vérifiée.
    doc.setDrawColor(...MUTED).setLineWidth(0.4)
    doc.rect(MARGIN, y - CHECKBOX_SIZE + 0.8, CHECKBOX_SIZE, CHECKBOX_SIZE)
    if (checkedItems.includes(item.id)) {
      doc.setDrawColor(...BRAND).setLineWidth(0.7)
      doc.line(MARGIN + 0.9, y - 1.3, MARGIN + 1.9, y - 0.2)
      doc.line(MARGIN + 1.9, y - 0.2, MARGIN + 3.6, y - 3)
    }
    doc.setTextColor(30, 41, 59).setFont('helvetica', 'normal').setFontSize(10)
    doc.text(lines, MARGIN + CHECKBOX_SIZE + 3, y)
    y += lines.length * lineHeight + 3
  }
  return y
}

function drawFooters(doc: jsPDF): void {
  const pages = doc.getNumberOfPages()
  for (let page = 1; page <= pages; page += 1) {
    doc.setPage(page)
    doc.setTextColor(...MUTED).setFont('helvetica', 'normal').setFontSize(8)
    doc.text(
      `Sources : ${DATA_SOURCES}. Document informatif, sans valeur contractuelle.`,
      MARGIN,
      284,
      { maxWidth: 160 },
    )
    doc.text(`${page} / ${pages}`, 195, 284, { align: 'right' })
  }
}

export function buildReportPdf(input: ReportInput): jsPDF {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
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
  drawFooters(doc)
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
