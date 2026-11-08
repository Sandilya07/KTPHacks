export interface Source { page: number; bbox: [number, number, number, number] }
interface BaseLine {
  id: string; date: string; code: string; modifiers: string[]
  source: Source | null; confidence: Record<string, number>; needs_review: boolean
}
export interface BillLine extends BaseLine { description: string; units: number; billed: number; patient_owed: number }
export interface EobLine extends BaseLine { allowed: number; plan_paid: number; patient_resp: number; status: string; adjustment_reason: string }
export interface Bill { provider: string; account_number: string; patient_balance: number; lines: BillLine[] }
export interface Eob { payer: string; network_status: string; total_patient_responsibility: number; lines: EobLine[] }
export interface PageDim { width: number; height: number }
export type Doc = 'bill' | 'eob'
export interface CaseView {
  case_id: string; confirmed: boolean; warnings: string[]; extractor: string; sample: string | null
  bill: Bill; eob: Eob; pages: Record<Doc, PageDim[]>
}
export interface Explanation { headline: string; what_happened: string; why_it_matters: string; what_you_can_do: string }
export interface Finding {
  id: string; rule: string; tier: 'definite' | 'likely' | 'ask'; tier_label: string; line_ids: string[]
  impact: number; evidence: string; source: string; explanation: Explanation
  translated: Explanation | null; translation_notice: string
}
export interface AuditResult {
  case_id: string; total_impact: number; findings: Finding[]; no_errors: boolean; only_questions: boolean
  checked: string[]; rules_data: Record<string, string>
  reconciliation: Reconciliation
}
export interface ReconciliationRow {
  bill_id: string; eob_id: string | null; code: string; date: string; eob_date: string | null
  bill_owed: number; eob_responsibility: number | null; difference: number | null
  match_basis: 'exact' | 'date' | 'code' | 'unmatched'; finding_ids: string[]; line_ids: string[]
}
export interface Reconciliation {
  bill_balance: number; bill_line_total: number; balance_matches_lines: boolean
  eob_total: number | null; statement_difference: number | null; matched_lines: number; total_lines: number
  rows: ReconciliationRow[]; unmatched_eob: { id: string; code: string; date: string; patient_responsibility: number }[]
  tiers: Record<Finding['tier'], { count: number; impact: number }>
}
export interface CorrectionResult {
  preview_only: boolean; line_id: string; original_line_amount: number; proposed_line_amount: number
  original_balance: number; proposed_balance: number; original_impact: number; proposed_impact: number
  impact_change: number; resolved_finding_ids: string[]; new_finding_ids: string[]; remaining_finding_count: number
}
export interface AskResult { answer: string; answer_en?: string; language: string; kind: string; citations: string[]; deferred: boolean; verified: boolean; notice: string }
export interface LetterSegment { section: string; english: string; translated: string; verified: boolean; notice: string }
export interface LetterResult { english: string; language: string; segments: LetterSegment[]; total: number; rows: number }
export interface Language { code: string; name: string; speech: string; reviewed: boolean }
export interface Config {
  llm_provider?: string | null; model?: string | null
  demo_mode: boolean; model_available: boolean; languages: Language[]
  samples: Record<string, string>; suggested_questions: string[]
}
export interface Highlight { ids: string[]; nonce: number }
