import { useEffect, useState } from 'react'
import { getLetter, letterUrl } from '../api'
import { ErrorBox, Screen, Spinner } from '../components/Chrome'
import type { Strings } from '../strings'
import type { CaseView, LetterResult } from '../types'

interface Props { s: Strings; lang: string; kase: CaseView; onBack: () => void }

export default function Letter({ s, lang, kase, onBack }: Props) {
  const [fields, setFields] = useState({ name: '', address: '', account: kase.bill.account_number })
  const [letter, setLetter] = useState<LetterResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  const [copied, setCopied] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let live = true
    setBusy(true); setError('')
    const timer = setTimeout(() => {
      getLetter(kase.case_id, { lang, ...fields })
        .then((l) => { if (live) { setLetter(l); setBusy(false) } })
        .catch((e: Error) => { if (live) { setError(e.message); setBusy(false) } })
    }, tick === 0 ? 0 : 400)
    return () => { live = false; clearTimeout(timer) }
  }, [kase.case_id, lang, fields, tick])

  async function copy() {
    if (!letter) return
    try { await navigator.clipboard.writeText(letter.english) } catch {
      const ta = document.createElement('textarea'); ta.value = letter.english; document.body.append(ta); ta.select(); document.execCommand('copy'); ta.remove()
    }
    setCopied(true); setTimeout(() => setCopied(false), 2500)
  }
  const set = (k: keyof typeof fields) => (e: React.ChangeEvent<HTMLInputElement>) => setFields((f) => ({ ...f, [k]: e.target.value }))
  const params = { name: fields.name, address: fields.address, account: fields.account }
  const header = letter?.english.split('\n\n').slice(0, 3).join('\n\n') ?? ''

  return (
    <Screen title={s.letterTitle}>
      <p className="text-xl">{s.letterIntro}</p>
      <div className="card grid gap-4 md:grid-cols-3">
        <label className="text-lg font-semibold">{s.yourName}<input className="field mt-1" value={fields.name} onChange={set('name')} autoComplete="name" /></label>
        <label className="text-lg font-semibold">{s.yourAddress}<input className="field mt-1" value={fields.address} onChange={set('address')} autoComplete="street-address" /></label>
        <label className="text-lg font-semibold">{s.accountNumber}<input className="field mt-1" value={fields.account} onChange={set('account')} /></label>
      </div>
      {error && <ErrorBox s={s} message={error} onRetry={() => setTick((n) => n + 1)} />}
      {busy && !letter && <Spinner message={s.loading} />}
      {letter && (
        <div className={busy ? 'opacity-60' : ''} aria-busy={busy}>
          {lang === 'en' ? (
            <section aria-labelledby="en-h" className="card">
              <h2 id="en-h" className="text-xl font-bold">{s.english}</h2>
              <pre lang="en" dir="ltr" className="mt-2 whitespace-pre-wrap font-sans text-base" data-testid="letter-english">{letter.english}</pre>
            </section>
          ) : (
            <div className="space-y-4" data-testid="letter-side-by-side">
              <div className="hidden grid-cols-2 gap-4 md:grid">
                <h2 className="text-xl font-bold">{s.english}</h2>
                <h2 className="text-xl font-bold">{s.translation}</h2>
              </div>
              <div className="card"><pre lang="en" dir="ltr" className="whitespace-pre-wrap font-sans text-base">{header}</pre></div>
              {letter.segments.map((seg, i) => (
                <div key={i} className="grid gap-3 md:grid-cols-2">
                  <div className="card" lang="en" dir="ltr"><p className="mb-1 text-sm font-semibold text-slate-600 md:hidden">{s.english}</p><p className="text-base">{seg.english}</p></div>
                  <div className="card" lang={seg.verified ? lang : 'en'}>
                    <p className="mb-1 text-sm font-semibold text-slate-600 md:hidden">{s.translation}</p>
                    <p className="text-base">{seg.translated}</p>
                    {!seg.verified && <p role="note" className="mt-2 rounded-lg bg-amber-50 p-2 text-sm">{s.notVerified}</p>}
                  </div>
                </div>
              ))}
              <details className="card"><summary className="cursor-pointer text-lg font-semibold">{s.english}</summary>
                <pre lang="en" dir="ltr" className="mt-2 whitespace-pre-wrap font-sans text-base">{letter.english}</pre></details>
            </div>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <button type="button" className="btn-primary text-xl" onClick={copy} disabled={!letter}>{copied ? `✓ ${s.copied}` : s.copy}</button>
        <a className="btn-secondary" href={letterUrl(kase.case_id, { ...params, format: 'pdf' })} download="billing-review-request.pdf">{s.downloadPdf}</a>
        <a className="btn-secondary" href={letterUrl(kase.case_id, { ...params, format: 'txt' })} download="billing-review-request.txt">{s.downloadTxt}</a>
        <button type="button" className="btn-secondary" onClick={onBack}>{s.back}</button>
      </div>
      <p role="status" aria-live="polite" className="sr-only">{copied ? s.copied : ''}</p>
    </Screen>
  )
}
