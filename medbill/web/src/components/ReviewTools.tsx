import { useEffect, useRef, useState } from 'react'
import { downloadEvidenceReport, previewCorrection } from '../api'
import { fmt, money, type Strings } from '../strings'
import type { CaseView, CorrectionResult, Reconciliation } from '../types'
import Icon from './Icon'

export function ReconciliationPanel({ s, data, onEvidence }: { s: Strings; data: Reconciliation; onEvidence: (ids: string[]) => void }) {
  const matches = { exact: s.matchExact, date: s.matchDate, code: s.matchCode, unmatched: s.noMatch }
  return <section className="card comparison-panel" aria-labelledby="comparison-heading" data-testid="comparison">
    <div className="tool-heading"><span className="tool-symbol"><Icon name="document" /></span><div>
      <h2 id="comparison-heading">{s.reconcileTitle}</h2>
      <p>{fmt(s.matchCount, { matched: data.matched_lines, total: data.total_lines })}</p>
    </div></div>
    <p className="tool-help">{s.reconcileHelp}</p>
    <dl className="statement-totals">
      <div><dt>{s.billAsks}</dt><dd dir="ltr">{money(data.bill_balance)}</dd></div>
      <div><dt>{s.insuranceShare}</dt><dd dir={data.eob_total === null ? undefined : 'ltr'}>{data.eob_total === null ? s.notShown : money(data.eob_total)}</dd></div>
      <div><dt>{s.statementGap}</dt><dd dir={data.statement_difference === null ? undefined : 'ltr'}>{data.statement_difference === null ? s.notShown : money(data.statement_difference)}</dd></div>
    </dl>
    <details className="comparison-details">
      <summary>{s.reconcileTitle}<span aria-hidden>{data.rows.length}</span></summary>
      <div className="comparison-table" role="table" aria-label={s.reconcileTitle}>
        <div className="comparison-header" role="row">
          <span role="columnheader">{s.cols.code} / {s.cols.date}</span><span role="columnheader">{s.billTab}</span>
          <span role="columnheader">{s.eobTab}</span><span role="columnheader">{s.yourDocument}</span>
        </div>
        {data.rows.map((row) => <div key={row.bill_id} role="row" className={`comparison-row ${row.finding_ids.length ? 'has-finding' : ''}`}>
          <div role="cell"><strong dir="ltr">{row.code}</strong><small dir="ltr">{row.date}</small></div>
          <div role="cell"><span className="comparison-mobile-label">{s.billTab}</span><strong dir="ltr">{money(row.bill_owed)}</strong><small dir="ltr">{row.bill_id}</small></div>
          <div role="cell"><span className="comparison-mobile-label">{s.eobTab}</span><strong dir={row.eob_responsibility === null ? undefined : 'ltr'}>{row.eob_responsibility === null ? s.notShown : money(row.eob_responsibility)}</strong>
            <small className={row.match_basis === 'exact' ? '' : 'match-caution'}>{matches[row.match_basis]}{row.eob_date && row.eob_date !== row.date ? ` · ${row.eob_date}` : ''}</small></div>
          <div role="cell"><button type="button" className="line-evidence" onClick={() => onEvidence(row.line_ids)}>{fmt(s.sourceLine, { id: row.bill_id })}<Icon name="arrow" className="directional-icon" /></button></div>
        </div>)}
      </div>
      {data.unmatched_eob.length > 0 && <div className="extra-insurance"><h3>{s.extraInsurance}</h3>
        <ul>{data.unmatched_eob.map((row) => <li key={row.id}><span dir="ltr">{row.id} · {row.code} · {row.date} · {money(row.patient_responsibility)}</span>
          <button className="line-evidence" type="button" onClick={() => onEvidence([row.id])}>{fmt(s.sourceLine, { id: row.id })}</button></li>)}</ul>
      </div>}
    </details>
  </section>
}

export function CorrectionPreview({ s, kase, data }: { s: Strings; kase: CaseView; data: Reconciliation }) {
  const suggested = [...data.rows].sort((a, b) => (b.difference ?? 0) - (a.difference ?? 0))[0]
  const [line, setLine] = useState(suggested?.bill_id ?? '')
  const [amount, setAmount] = useState(String(suggested?.eob_responsibility ?? suggested?.bill_owed ?? 0))
  const [result, setResult] = useState<CorrectionResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const request = useRef(0)
  useEffect(() => () => { request.current += 1 }, [])
  async function preview() {
    if (busy || !amount.trim() || !Number.isFinite(Number(amount))) return
    const version = ++request.current
    setBusy(true); setError(''); setResult(null)
    try {
      const response = await previewCorrection(kase.case_id, line, Number(amount))
      if (version === request.current) setResult(response)
    } catch (e) { if (version === request.current) setError(e instanceof Error ? e.message : s.tryAgain) }
    finally { if (version === request.current) setBusy(false) }
  }
  function chooseLine(id: string) {
    const row = data.rows.find((row) => row.bill_id === id)
    setLine(id); setAmount(String(row?.eob_responsibility ?? row?.bill_owed ?? 0)); setResult(null); setError('')
  }
  return <details id="correction-preview" className="card correction-tool" data-testid="correction-tool">
    <summary><span className="tool-symbol"><Icon name="pulse" /></span>{s.previewTitle}</summary>
    <p className="tool-help">{s.previewHelp}</p>
    <form className="correction-form" onSubmit={(event) => { event.preventDefault(); void preview() }}>
      <label>{s.previewLine}<select className="field" value={line} disabled={busy} onChange={(event) => chooseLine(event.target.value)}>
        {kase.bill.lines.map((row) => <option key={row.id} value={row.id}>{row.id} · {row.code} · {money(row.patient_owed)}</option>)}
      </select></label>
      <label>{s.previewAmount}<input className="field" type="number" min="0" max="10000000" step="0.01" required inputMode="decimal" value={amount} disabled={busy}
        onChange={(event) => { setAmount(event.target.value); setResult(null); setError('') }} /></label>
      <button type="submit" className="btn-primary" disabled={busy || !amount.trim()}>{busy ? s.loading : s.previewButton}<Icon name="arrow" /></button>
    </form>
    {error && <p className="tool-error" role="alert">{error}</p>}
    {result && <div className="correction-result" role="status" data-testid="correction-result">
      <div className="scenario-comparison">
        <div><span>{s.previewOriginal}</span><strong dir="ltr">{money(result.original_balance)}</strong><small>{s.billAsks}</small></div>
        <Icon name="arrow" />
        <div><span>{s.previewScenario}</span><strong dir="ltr">{money(result.proposed_balance)}</strong><small>{s.billAsks}</small></div>
      </div>
      <div className="scenario-remaining"><span>{s.previewRemaining}</span><strong dir="ltr">{money(result.proposed_impact)}</strong></div>
      <p>{fmt(s.previewResolved, { n: result.resolved_finding_ids.length })}</p>
      {result.new_finding_ids.length > 0 && <p>{fmt(s.previewNew, { n: result.new_finding_ids.length })}</p>}
    </div>}
    <p className="preview-notice"><Icon name="shield" />{s.previewNotice}</p>
  </details>
}

export function EvidenceDownload({ s, caseId }: { s: Strings; caseId: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function download() {
    if (busy) return
    setBusy(true); setError('')
    try { await downloadEvidenceReport(caseId) }
    catch (e) { setError(e instanceof Error ? e.message : s.tryAgain) }
    finally { setBusy(false) }
  }
  return <section id="evidence-report" className="card evidence-download" aria-labelledby="report-heading">
    <span className="tool-symbol"><Icon name="letter" /></span>
    <div><h2 id="report-heading">{s.reportTitle}</h2><p>{s.reportHelp}</p><small>{s.reportLanguage}</small>
      {error && <p className="tool-error" role="alert">{error}</p>}</div>
    <button className="btn-primary" type="button" onClick={() => void download()} disabled={busy} data-testid="download-report">{busy ? s.loading : s.reportDownload}<Icon name="document" /></button>
  </section>
}
