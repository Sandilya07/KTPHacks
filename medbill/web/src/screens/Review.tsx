import { useMemo, useState } from 'react'
import { confirmCase, patchLines } from '../api'
import { ErrorBox, Screen, Spinner } from '../components/Chrome'
import DocViewer from '../components/DocViewer'
import type { Strings } from '../strings'
import { fmt } from '../strings'
import type { BillLine, CaseView, Doc, EobLine, Highlight } from '../types'

type Row = { id: string; isNew: boolean; v: Record<string, string>; low: Set<string>; orig: Record<string, string> }
interface FieldDef { key: string; kind: 'text' | 'num' | 'money' | 'status'; group: string; width?: string }

const BILL_FIELDS: FieldDef[] = [
  { key: 'date', kind: 'text', group: 'date' }, { key: 'code', kind: 'text', group: 'code' },
  { key: 'modifiers', kind: 'text', group: 'code' }, { key: 'description', kind: 'text', group: 'description' },
  { key: 'units', kind: 'num', group: 'units' }, { key: 'billed', kind: 'money', group: 'amounts' },
  { key: 'patient_owed', kind: 'money', group: 'amounts' },
]
const EOB_FIELDS: FieldDef[] = [
  { key: 'date', kind: 'text', group: 'date' }, { key: 'code', kind: 'text', group: 'code' },
  { key: 'modifiers', kind: 'text', group: 'code' }, { key: 'allowed', kind: 'money', group: 'amounts' },
  { key: 'plan_paid', kind: 'money', group: 'amounts' }, { key: 'patient_resp', kind: 'money', group: 'amounts' },
  { key: 'status', kind: 'status', group: 'status' },
]
const STATUSES = ['processed', 'denied-duplicate', 'denied-bundled', 'denied-other']
const LOW = 0.8
// Column widths per document (md and up); on phones each line becomes a stacked card.
const COLS = { bill: '1.4fr 1fr .9fr 2fr .7fr 1.1fr 1.1fr 2.75rem', eob: '1.4fr 1fr .9fr 1.1fr 1.1fr 1.1fr 1.7fr 2.75rem' }

function toRow(l: BillLine | EobLine, fields: FieldDef[]): Row {
  const v: Record<string, string> = {}
  for (const f of fields) {
    const raw = (l as unknown as Record<string, unknown>)[f.key]
    v[f.key] = f.key === 'modifiers' ? (raw as string[]).join(', ') : String(raw ?? '')
  }
  const low = new Set<string>()
  for (const f of fields) if ((l.confidence[f.group] ?? 1) < LOW || (l.needs_review && (l.confidence[f.group] ?? 1) < 0.95)) low.add(f.key)
  return { id: l.id, isNew: false, v, low, orig: { ...v } }
}

function patchValue(f: FieldDef, s: string): unknown {
  if (f.key === 'modifiers') return s.split(/[,\s]+/).filter(Boolean)
  if (f.kind === 'money') return Number(s.replace(/[$,]/g, '')) || 0
  if (f.kind === 'num') return Math.max(1, parseInt(s, 10) || 1)
  return s.trim()
}

interface Props { s: Strings; kase: CaseView; onConfirmed: (c: CaseView) => void; onBack: () => void }

export default function Review({ s, kase, onConfirmed, onBack }: Props) {
  const [doc, setDoc] = useState<Doc>('bill')
  const [rows, setRows] = useState<Record<Doc, Row[]>>(() => ({
    bill: kase.bill.lines.map((l) => toRow(l, BILL_FIELDS)), eob: kase.eob.lines.map((l) => toRow(l, EOB_FIELDS)),
  }))
  const [removed, setRemoved] = useState<Record<Doc, string[]>>({ bill: [], eob: [] })
  const [balance, setBalance] = useState(String(kase.bill.patient_balance))
  const [selected, setSelected] = useState<Highlight>({ ids: [], nonce: 0 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fields = doc === 'bill' ? BILL_FIELDS : EOB_FIELDS
  const flagged = useMemo(() => rows.bill.some((r) => r.low.size) || rows.eob.some((r) => r.low.size), [rows])

  const setCell = (id: string, key: string, value: string) =>
    setRows((r) => ({ ...r, [doc]: r[doc].map((x) => (x.id === id ? { ...x, v: { ...x.v, [key]: value }, low: new Set([...x.low].filter((k) => k !== key)) } : x)) }))
  const select = (id: string) => setSelected((h) => ({ ids: [id], nonce: h.nonce + 1 }))
  const addLine = () => setRows((r) => {
    const empty = Object.fromEntries(fields.map((f) => [f.key, f.kind === 'text' ? '' : f.kind === 'status' ? 'processed' : f.key === 'units' ? '1' : '0']))
    empty.date = new Date().toISOString().slice(0, 10)
    return { ...r, [doc]: [...r[doc], { id: `new${Date.now()}`, isNew: true, v: empty, low: new Set(), orig: {} }] }
  })
  const removeLine = (id: string) => {
    setRows((r) => ({ ...r, [doc]: r[doc].filter((x) => x.id !== id) }))
    if (!id.startsWith('new')) setRemoved((x) => ({ ...x, [doc]: [...x[doc], id] }))
  }

  async function submit() {
    setBusy(true); setError('')
    try {
      const body: Record<string, unknown> = {}
      if (Number(balance) !== kase.bill.patient_balance) body.bill = { patient_balance: Number(balance) || 0 }
      for (const d of ['bill', 'eob'] as const) {
        const defs = d === 'bill' ? BILL_FIELDS : EOB_FIELDS
        const edits: Record<string, Record<string, unknown>> = {}
        const adds: Record<string, unknown>[] = []
        for (const r of rows[d]) {
          if (r.isNew) { adds.push(Object.fromEntries(defs.map((f) => [f.key, patchValue(f, r.v[f.key])]))); continue }
          const changed = defs.filter((f) => r.v[f.key] !== r.orig[f.key])
          if (changed.length) edits[r.id] = Object.fromEntries(changed.map((f) => [f.key, patchValue(f, r.v[f.key])]))
        }
        if (Object.keys(edits).length) body[`${d}_lines`] = edits
        if (adds.length) body[`add_${d}_lines`] = adds
        if (removed[d].length) body[`delete_${d}_lines`] = removed[d]
      }
      if (Object.keys(body).length) await patchLines(kase.case_id, body)
      onConfirmed(await confirmCase(kase.case_id))
    } catch (e) {
      setError(e instanceof Error ? e.message : s.tryAgain)
      setBusy(false)
    }
  }

  return (
    <Screen title={s.reviewTitle}>
      <p className="text-xl">{s.reviewIntro}</p>
      {kase.warnings.length > 0 && (
        <ul className="list-disc rounded-xl border-2 border-amber-500 bg-amber-50 py-3 ps-8 pe-4 text-base">
          {kase.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
      {error && <ErrorBox s={s} message={error} />}
      {busy ? <Spinner message={s.loading} /> : (
        <div className="grid gap-5 2xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="space-y-4">
            <div role="tablist" aria-label={s.reviewTitle} className="flex gap-2">
              {(['bill', 'eob'] as const).map((d) => (
                <button key={d} role="tab" type="button" aria-selected={doc === d} onClick={() => setDoc(d)}
                  className={`min-h-11 rounded-lg border-2 px-4 font-semibold ${doc === d ? 'border-blue-800 bg-blue-50' : 'border-slate-400 bg-white'}`}>
                  {d === 'bill' ? s.billTab : s.eobTab}
                </button>
              ))}
            </div>
            {doc === 'bill' && (
              <label className="block text-lg font-semibold">{s.balanceLabel}
                <input className="field mt-1 max-w-xs" inputMode="decimal" value={balance} onChange={(e) => setBalance(e.target.value)} />
              </label>
            )}
            <div role="table" aria-label={doc === 'bill' ? s.billTab : s.eobTab} className="space-y-3" style={{ '--cols': COLS[doc] } as React.CSSProperties}>
              <div role="row" className="hidden gap-2 px-3 text-sm font-semibold text-slate-700 md:grid md:grid-cols-(--cols)">
                {fields.map((f) => <div role="columnheader" key={f.key}>{s.cols[f.key as keyof typeof s.cols]}</div>)}
                <div role="columnheader" className="sr-only">{s.removeLine.replace('{id}', '')}</div>
              </div>
              {rows[doc].map((r) => (
                <div role="row" key={r.id} aria-label={r.id} onFocus={() => !r.isNew && select(r.id)}
                  className={`grid grid-cols-2 gap-2 rounded-xl border-2 bg-white p-3 md:grid-cols-(--cols) md:p-3 ${selected.ids[0] === r.id ? 'border-blue-700' : 'border-slate-300'}`}>
                  {fields.map((f) => {
                    const low = r.low.has(f.key)
                    const id = `${doc}-${r.id}-${f.key}`
                    const label = s.cols[f.key as keyof typeof s.cols]
                    return (
                      <div role="cell" key={f.key} className={f.key === 'description' ? 'col-span-2 md:col-span-1' : ''}>
                        <label htmlFor={id} className="text-sm font-semibold text-slate-700 md:sr-only">{label}</label>
                        {f.kind === 'status' ? (
                          <select id={id} className="field" value={r.v[f.key]} onChange={(e) => setCell(r.id, f.key, e.target.value)}>
                            {STATUSES.map((x) => <option key={x}>{x}</option>)}
                          </select>
                        ) : (
                          <input id={id} className={`field ${low ? 'border-amber-600 bg-yellow-100' : ''}`} value={r.v[f.key]} aria-describedby={low ? `${id}-hint` : undefined}
                            inputMode={f.kind === 'money' ? 'decimal' : f.kind === 'num' ? 'numeric' : undefined} onChange={(e) => setCell(r.id, f.key, e.target.value)} />
                        )}
                        {low && <p id={`${id}-hint`} className="mt-0.5 text-sm font-semibold text-amber-900"><span aria-hidden>⚠ </span>{s.checkThis}</p>}
                      </div>
                    )
                  })}
                  <button type="button" className="btn-secondary col-span-2 min-h-11 md:col-span-1 md:px-0" aria-label={fmt(s.removeLine, { id: r.isNew ? '' : r.id })}
                    onClick={() => removeLine(r.id)}><span aria-hidden>✕</span></button>
                </div>
              ))}
            </div>
            <button type="button" className="btn-secondary" onClick={addLine}>+ {s.addLine}</button>
          </div>
          <div className="2xl:sticky 2xl:top-4 2xl:self-start">
            <DocViewer s={s} kase={kase} highlight={selected} />
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-3 pt-2">
        <button type="button" className="btn-primary text-xl" disabled={busy} onClick={submit} data-testid="looks-right">{s.looksRight}</button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={onBack}>{s.back}</button>
        {flagged && <p className="self-center text-base font-semibold text-amber-900"><span aria-hidden>⚠ </span>{s.checkThis}</p>}
      </div>
    </Screen>
  )
}
