import { useEffect, useState } from 'react'
import { runAudit } from '../api'
import { ErrorBox, Screen, Spinner } from '../components/Chrome'
import DocViewer from '../components/DocViewer'
import { fmt, money, type Strings } from '../strings'
import type { AuditResult, CaseView, Finding, Highlight } from '../types'
import Icon from '../components/Icon'

const TIER_STYLE = {
  definite: { border: 'tier-definite', badge: 'bg-red-800 text-white', icon: '■' },
  likely: { border: 'tier-likely', badge: 'bg-amber-800 text-white', icon: '▲' },
  ask: { border: 'tier-ask', badge: 'bg-blue-800 text-white', icon: '?' },
} as const

interface Props {
  s: Strings; lang: string; kase: CaseView; audit: AuditResult | null; auditKey: string; setAudit: (a: AuditResult, key: string) => void
  highlight: Highlight; setHighlight: (h: Highlight) => void; onAsk: () => void; onLetter: () => void; onBack: () => void
}

function FindingCard({ s, f, active, onEvidence }: { s: Strings; f: Finding; active: boolean; onEvidence: () => void }) {
  const st = TIER_STYLE[f.tier]
  const shown = f.translated ?? f.explanation
  return (
    <article className={`card finding-card ${st.border}`} aria-labelledby={`f-${f.id}`} data-testid={`finding-${f.rule}`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-base font-bold ${st.badge}`}><span aria-hidden>{st.icon}</span>{s.tiers[f.tier]}</span>
        <span className="text-base text-slate-700">{s.tierHelp[f.tier]}</span>
        {f.impact > 0 && <span className="ms-auto text-lg font-bold">{s.inQuestion}: {money(f.impact)}</span>}
      </div>
      <h3 id={`f-${f.id}`} className="mt-3 text-2xl font-bold" lang={f.translated ? undefined : 'en'}>{shown.headline}</h3>
      <dl className="mt-3 space-y-3 text-lg">
        <div><dt className="font-semibold">{s.whatHappened}</dt><dd>{shown.what_happened}</dd></div>
        <div><dt className="font-semibold">{s.whyMatters}</dt><dd>{shown.why_it_matters}</dd></div>
        <div><dt className="font-semibold">{s.whatToDo}</dt><dd>{shown.what_you_can_do}</dd></div>
      </dl>
      {f.translation_notice && <p role="note" className="mt-3 rounded-lg bg-amber-50 p-2 text-base">{s.notVerified}</p>}
      <p className="mt-3 text-base text-slate-700"><span className="font-semibold">{s.rule}:</span> <span lang="en">{f.source}</span></p>
      {f.translated && (
        <details className="mt-2">
          <summary className="cursor-pointer text-base font-semibold">English</summary>
          <div lang="en" className="mt-1 space-y-1 text-base"><p className="font-semibold">{f.explanation.headline}</p><p>{f.explanation.what_happened}</p><p>{f.explanation.why_it_matters}</p><p>{f.explanation.what_you_can_do}</p></div>
        </details>
      )}
      <button type="button" className="btn-secondary mt-4" aria-pressed={active} onClick={onEvidence} data-testid={`evidence-${f.rule}`}>
        {active ? `✓ ${s.evidenceShown}` : s.evidence}
      </button>
    </article>
  )
}

export default function Results({ s, lang, kase, audit, auditKey, setAudit, highlight, setHighlight, onAsk, onLetter, onBack }: Props) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  const key = `${kase.case_id}:${lang}`
  useEffect(() => {
    if (audit && auditKey === key && attempt === 0) return // already audited this case in this language
    let live = true
    setBusy(s.progress.rules); setError('')
    runAudit(kase.case_id, lang, (m) => live && setBusy(m.startsWith('Writing') ? s.progress.explaining : s.progress.rules))
      .then((a) => { if (live) { setAudit(a, key); setBusy('') } })
      .catch((e: Error) => { if (live) { setError(e.message); setBusy('') } })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kase.case_id, lang, attempt])

  const sampleParts = audit ? Object.entries(audit.rules_data).filter(([, v]) => v === 'sample').map(([k]) => k.toUpperCase()).join(', ') : ''
  const headline = !audit ? '' : audit.total_impact > 0 ? fmt(s.overcharged, { amount: money(audit.total_impact) }) : audit.no_errors ? s.noErrors : s.questionsHeadline
  const tone = audit?.no_errors ? 'is-clean' : audit?.total_impact === 0 ? 'is-question' : ''
  const amount = audit && audit.total_impact > 0 ? money(audit.total_impact) : ''
  const headlineParts = amount ? headline.split(amount) : [headline]

  return (
    <Screen title={s.resultsTitle}>
      {busy && <Spinner message={busy} />}
      {error && <ErrorBox s={s} message={error} onRetry={() => setAttempt((n) => n + 1)} />}
      {audit && !busy && (
        <>
          <div className={`result-summary ${tone}`} role="status" data-testid="headline">
            <p className="result-summary-label"><Icon name={audit.no_errors ? 'shield' : 'search'} />{s.resultsTitle}</p>
            <h2>{headlineParts[0]}{amount && <strong className="result-amount" dir="ltr">{amount}</strong>}{headlineParts[1]}</h2>
            {audit.no_errors && <p className="mt-3 text-sm leading-relaxed">{s.noErrorsBody}</p>}
          </div>
          <div className="result-metrics">
            <div className="result-metric"><Icon name="document" /><span><strong>{s.billTab}</strong><small>{fmt(s.lineCount, { n: kase.bill.lines.length })}</small></span></div>
            <div className="result-metric"><Icon name="shield" /><span><strong>{s.eobTab}</strong><small>{fmt(s.lineCount, { n: kase.eob.lines.length })}</small></span></div>
            <div className="result-metric"><Icon name="check" /><span><strong>{fmt(s.checkCount, { n: audit.checked.length })}</strong><small>{s.workspace}</small></span></div>
          </div>
          <div className="results-grid">
            <div className="space-y-5">
              {audit.findings.map((f) => (
                <FindingCard key={f.id} s={s} f={f} active={highlight.ids.join() === f.line_ids.join()}
                  onEvidence={() => setHighlight({ ids: f.line_ids, nonce: highlight.nonce + 1 })} />
              ))}
              <details className="card" open={audit.no_errors}>
                <summary className="cursor-pointer text-xl font-semibold">{s.checkedTitle}</summary>
                <ul className="mt-2 list-disc space-y-1 ps-6 text-lg">{audit.checked.map((c) => <li key={c}>{c}</li>)}</ul>
                {sampleParts && <p className="mt-3 text-base text-slate-700">{fmt(s.rulesDataNote, { parts: sampleParts })}</p>}
              </details>
            </div>
            <div className="results-evidence"><DocViewer s={s} kase={kase} highlight={highlight} /></div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" className="btn-primary text-xl" onClick={onAsk}>{s.askNext}</button>
            <button type="button" className="btn-secondary text-xl" onClick={onLetter}>{s.writeLetter}</button>
            <button type="button" className="btn-secondary" onClick={onBack}>{s.back}</button>
          </div>
        </>
      )}
    </Screen>
  )
}
