import { ref, type Ref } from 'vue'

import { fetchBranding, type Branding } from '../api/account'
import { buildReportSections, synthesisSections, unavailableSources } from '../lib/report'
import { SOURCE_INFO } from '../lib/sources'
import type { AuditLocation, ReportMeta, SourceName, SourceResults } from '../types/audit'
import { useAccount } from './useAccount'
import { useAuth } from './useAuth'

interface ReportState {
  location: Ref<AuditLocation | null>
  meta: Ref<ReportMeta | null>
  sources: Ref<SourceResults>
  /** Points de la checklist de seconde visite cochés par l'utilisateur. */
  checkedItems: Ref<string[]>
}

/** Export PDF du rapport affiché ; jamais pour un aperçu, dont les valeurs sont masquées. */
export function usePdfExport(report: ReportState, locked: Ref<boolean>) {
  const { accessToken } = useAuth()
  const { account } = useAccount()
  const exporting = ref(false)
  const exportFailed = ref(false)

  /** Marque blanche de l'abonné ; son absence ou une panne n'empêche jamais l'export. */
  async function loadBranding(): Promise<Branding | null> {
    if (!accessToken.value || !account.value?.subscription_active) return null
    try {
      return await fetchBranding(accessToken.value)
    } catch {
      return null
    }
  }

  async function exportPdf(): Promise<void> {
    const location = report.location.value
    if (!location || locked.value) return
    exporting.value = true
    exportFailed.value = false
    try {
      // jsPDF (~400 Ko) n'est téléchargé qu'au premier export.
      const { buildReportPdf, collectCharts, reportFileName } = await import('../lib/pdf')
      const meta = report.meta.value
      const unavailable = unavailableSources(report.sources.value).map(
        (name) => SOURCE_INFO[name as SourceName]?.title ?? name,
      )
      buildReportPdf({
        location,
        meta,
        sections: [...synthesisSections(meta?.synthese), ...buildReportSections(report.sources.value)],
        charts: collectCharts(),
        unavailable,
        checkedItems: report.checkedItems.value,
        branding: await loadBranding(),
      }).save(reportFileName(location))
    } catch (error) {
      console.error('Export PDF impossible', error)
      exportFailed.value = true
    } finally {
      exporting.value = false
    }
  }

  return { exporting, exportFailed, exportPdf }
}
