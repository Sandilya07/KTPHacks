import { useEffect, useRef, useState } from 'react'
import { askQuestion } from '../api'
import { ErrorBox, Screen } from '../components/Chrome'
import { listen, recognitionSupported, speak } from '../components/voice'
import { t, type Strings } from '../strings'
import type { AskResult, AuditResult, CaseView, Config, Highlight } from '../types'

export interface Msg { role: 'user' | 'assistant'; text: string; result?: AskResult; lang: string }
interface Props {
  s: Strings; config: Config; lang: string; kase: CaseView; audit: AuditResult | null
  msgs: Msg[]; setMsgs: React.Dispatch<React.SetStateAction<Msg[]>> // kept by the App so history survives a jump to the evidence
  onJump: (h: Highlight) => void; onLetter: () => void; onBack: () => void
}

export default function Ask({ s, config, lang, kase, audit, msgs, setMsgs, onJump, onLetter, onBack }: Props) {
  const [askLang, setAskLang] = useState(lang)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [listening, setListening] = useState(false)
  const [voiceNote, setVoiceNote] = useState('')
  const stop = useRef<() => void>(() => undefined)
  const end = useRef<HTMLDivElement>(null)
  const as = t(askLang)
  const speech = config.languages.find((l) => l.code === askLang)?.speech ?? 'en-US'
  const suggestions = askLang === 'en' ? config.suggested_questions : as.suggestedList

  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }) }, [msgs, busy])
  useEffect(() => () => { stop.current(); window.speechSynthesis?.cancel() }, [])

  async function send(q: string) {
    const question = q.trim()
    if (!question || busy) return
    setMsgs((m) => [...m, { role: 'user', text: question, lang: askLang }])
    setText(''); setBusy(true); setError('')
    try {
      const r = await askQuestion(kase.case_id, question, askLang)
      setMsgs((m) => [...m, { role: 'assistant', text: r.answer, result: r, lang: r.verified || r.deferred ? askLang : 'en' }])
    } catch (e) {
      setError(e instanceof Error ? e.message : s.tryAgain)
    }
    setBusy(false)
  }

  function toggleMic() {
    if (listening) { stop.current(); return }
    setListening(true)
    stop.current = listen(speech, (txt) => setText(txt), () => setListening(false))
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
        <label className="flex flex-wrap items-center gap-3 text-lg font-semibold">{s.chooseLanguage}
          <select className="field max-w-xs" value={askLang} onChange={(e) => setAskLang(e.target.value)} data-testid="ask-language">
            {config.languages.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.name}</option>)}
          </select>
        </label>
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
              <p className="text-lg" lang={m.lang}>{m.text}</p>
              {m.result && !m.result.verified && !m.result.deferred && m.result.notice && <p role="note" className="mt-2 rounded-lg bg-amber-50 p-2 text-base">{s.notVerified}</p>}
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
              {m.role === 'assistant' && (
                <button type="button" className="btn-secondary mt-2 min-h-10 text-base" onClick={() => setVoiceNote(speak(m.text, m.lang === 'en' ? 'en-US' : speech) ? '' : as.noVoice)}>
                  <span aria-hidden>🔊</span> {s.listen}
                </button>
              )}
            </div>
          ))}
          {busy && <p className="text-lg text-slate-700" role="status">{s.thinking}</p>}
          <div ref={end} />
        </div>
        {voiceNote && <p role="status" className="text-base font-semibold text-amber-900">{voiceNote}</p>}
        <form className="flex flex-wrap gap-3" onSubmit={(e) => { e.preventDefault(); void send(text) }}>
          <label className="sr-only" htmlFor="q">{s.askPlaceholder}</label>
          <input id="q" className="field min-w-0 flex-1" placeholder={s.askPlaceholder} value={text} onChange={(e) => setText(e.target.value)} lang={askLang} />
          {recognitionSupported() && (
            <button type="button" className="btn-secondary" aria-pressed={listening} onClick={toggleMic}>
              <span aria-hidden>{listening ? '■' : '🎤'}</span> {listening ? s.micStop : s.mic}
            </button>
          )}
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
