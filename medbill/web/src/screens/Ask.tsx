import { useEffect, useRef, useState } from 'react'
import { askQuestion, detectLanguage } from '../api'
import { ErrorBox, Screen } from '../components/Chrome'
import { interfaceText, type Strings } from '../strings'
import type { AskResult, AuditResult, CaseView, Config, Highlight } from '../types'

export interface Msg { role: 'user' | 'assistant'; text: string; result?: AskResult; lang: string }
interface Props {
  onLanguage: (lang: string, values?: Record<string, string>) => void
  s: Strings; config: Config; lang: string; kase: CaseView; audit: AuditResult | null
  msgs: Msg[]; setMsgs: React.Dispatch<React.SetStateAction<Msg[]>> // kept by the App so history survives a jump to the evidence
  onJump: (h: Highlight) => void; onLetter: () => void; onBack: () => void
}

export default function Ask({ onLanguage, s, config, lang, kase, audit, msgs, setMsgs, onJump, onLetter, onBack }: Props) {
  const askLang = lang
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const requestVersion = useRef(0)
  const suggestions = askLang === 'en' ? config.suggested_questions : s.suggestedList

  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }) }, [msgs, busy])
  useEffect(() => () => { requestVersion.current += 1 }, [])

  async function send(q: string) {
    const question = q.trim()
    if (!question || busy) return
    const version = ++requestVersion.current
    const questionIndex = msgs.length
    setMsgs((m) => [...m, { role: 'user', text: question, lang: askLang }])
    setText(''); setBusy(true); setError('')
    try {
      const history = msgs.slice(-8).map(({ role, text }) => ({ role, text: text.slice(0, 12000) }))
      const r = await askQuestion(kase.case_id, question, 'auto', history)
      if (version !== requestVersion.current) return
      setMsgs((m) => [...m.map((message, index) => index === questionIndex ? { ...message, lang: r.language } : message),
        { role: 'assistant', text: r.answer, result: r, lang: r.verified ? r.language : 'en' }])
      try {
        if (r.language !== lang) {
          const locale = await detectLanguage(question, interfaceText(), r.language)
          if (version !== requestVersion.current) return
          onLanguage(locale.language, locale.strings)
        }
      } catch { if (version === requestVersion.current) setError('Your answer is ready, but the interface translation could not be updated. Please try again.') }
    } catch (e) {
      if (version === requestVersion.current) setError(e instanceof Error ? e.message : s.tryAgain)
    }
    if (version === requestVersion.current) setBusy(false)
  }


  /** A citation is either a bill/EOB line id or a finding id; both resolve to lines to highlight. */
  function cite(id: string): { label: string; ids: string[] } {
    const f = audit?.findings.find((x) => x.id === id)
    return f ? { label: f.tier_label, ids: f.line_ids } : { label: id, ids: [id] }
  }

  return (
    <Screen title={s.askTitle}>
      <p className="text-xl">{s.askIntro}</p>
      {error && <ErrorBox s={s} message={error} />}
      <div className="card space-y-4">
        <p className="text-sm text-slate-600">{s.welcomePoints[1]}</p>
        <div>
          <p className="text-lg font-semibold">{s.suggested}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {suggestions.map((q) => <button key={q} type="button" className="btn-secondary min-h-11 text-base" lang={askLang} onClick={() => void send(q)}>{q}</button>)}
          </div>
        </div>
        <div role="log" aria-live="polite" aria-label={s.askTitle} tabIndex={0} className="max-h-[50vh] min-h-24 space-y-3 overflow-auto rounded-xl bg-slate-50 p-3" data-testid="chat-log">
          {msgs.map((m, i) => (
            <div key={i} className={m.role === 'user' ? 'ms-8 rounded-xl bg-blue-100 p-3' : 'me-8 rounded-xl border border-slate-300 bg-white p-3'} data-testid={`msg-${m.role}`}>
              <p className="text-sm font-semibold text-slate-700">{m.role === 'user' ? s.you : s.assistant}</p>
              <p className="text-lg" dir="auto" lang={m.lang}>{m.text}</p>
              {m.result?.answer_en && m.result.answer_en !== m.text && (
                <details className="mt-2 text-sm">
                  <summary className="cursor-pointer font-semibold">{s.originalEnglish}</summary>
                  <p className="mt-2" lang="en" dir="ltr">{m.result.answer_en}</p>
                </details>
              )}
              {m.result && !m.result.verified && m.result.notice && <p role="note" className="mt-2 rounded-lg bg-amber-50 p-2 text-base">{s.notVerified}</p>}
              {m.result?.deferred && <p className="mt-1 text-base font-semibold text-slate-700">{s.deferred}</p>}
              {m.result && m.result.citations.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="text-base font-semibold">{s.citations}:</span>
                  {[...new Set(m.result.citations)].slice(0, 8).map((c) => {
                    const { label, ids } = cite(c)
                    return <button key={c} type="button" data-testid="citation" className="btn-secondary min-h-10 px-3 text-base" onClick={() => onJump({ ids, nonce: Date.now() })}>{label}</button>
                  })}
                </div>
              )}

            </div>
          ))}
          {busy && <p className="text-lg text-slate-700" role="status">{s.thinking}</p>}
          <div ref={end} />
        </div>
        <form className="flex flex-wrap gap-3" onSubmit={(e) => { e.preventDefault(); void send(text) }}>
          <label className="sr-only" htmlFor="q">{s.askPlaceholder}</label>
          <input id="q" className="field min-w-0 flex-1" placeholder={s.askPlaceholder} value={text} onChange={(e) => setText(e.target.value)} dir="auto" maxLength={4000} />

          <button type="submit" className="btn-primary" disabled={busy || !text.trim()}>{s.send}</button>
        </form>
      </div>
      <div className="flex flex-wrap gap-3">
        <button type="button" className="btn-primary text-xl" onClick={onLetter}>{s.writeLetter}</button>
        <button type="button" className="btn-secondary" onClick={onBack}>{s.back}</button>
      </div>
    </Screen>
  )
}
