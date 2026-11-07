import { useState } from 'react'
import type { Config } from '../types'
import { type Strings, interfaceText } from '../strings'
import { detectLanguage } from '../api'
import { Screen } from '../components/Chrome'

interface Props { s: Strings; config: Config; lang: string; setLang: (l: string, values?: Record<string, string>) => void; onStart: () => void }
export default function Welcome({ s, config, lang, setLang, onStart }: Props) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  async function detect() {
    if (text.trim().length < 2 || busy) return
    setBusy(true); setNotice('')
    try {
      const result = await detectLanguage(text.trim(), interfaceText())
      setLang(result.language, result.strings)
      setNotice(result.notice || '')
    } catch (e) { setNotice(e instanceof Error ? e.message : s.tryAgain) }
    finally { setBusy(false) }
  }
  return <Screen title={s.welcomeTitle}>
    <div className="welcome-grid">
      <div className="hero-panel">
        <span className="eyebrow">{s.appName}</span>
        <p className="hero-copy">{s.welcomeBody}</p>
        <div className="feature-list">{s.welcomePoints.map((point, i) => <div key={point}><span className="feature-number">0{i + 1}</span><p>{point}</p></div>)}</div>
        <button type="button" className="btn-primary" disabled={busy} onClick={onStart}>{s.start} <span aria-hidden>→</span></button>
      </div>
      <div className="card language-card">
        <div className="language-icon" aria-hidden>文 / A</div>
        <h2 className="text-2xl font-semibold">{s.askTitle}</h2>
        <p className="mt-3 text-slate-600">{s.welcomePoints[1]}</p>
        <form className="mt-5 space-y-3" onSubmit={(e) => { e.preventDefault(); void detect() }}>
          <label htmlFor="language-text" className="block font-semibold">{s.askPlaceholder}</label>
          <textarea id="language-text" dir="auto" className="field min-h-32" maxLength={4000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Hola, quiero entender mi factura…" />
          <button className="btn-secondary w-full" disabled={busy || text.trim().length < 2}>{busy ? s.loading : s.send}</button>
        </form>
        <p className="mt-4 text-sm text-slate-600" role="status">{notice || (lang === 'en' ? 'Type in your language. We detect it and translate your experience.' : lang.toUpperCase())}</p>
        {config.demo_mode && <p className="mt-3 text-sm text-slate-600">Offline demo: English · Español · Монгол</p>}
      </div>
    </div>
  </Screen>
}
