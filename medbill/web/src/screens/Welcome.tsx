import { useState } from 'react'
import type { CaseView, Config } from '../types'
import { type Strings, interfaceText } from '../strings'
import { createCase, detectLanguage } from '../api'
import { Screen } from '../components/Chrome'
import Icon, { MedicalArt, type IconName } from '../components/Icon'

interface Props { s: Strings; config: Config; lang: string; setLang: (l: string, values?: Record<string, string>) => void; onStart: () => void; onExample: (kase: CaseView) => void }
const featureIcons: IconName[] = ['document', 'globe', 'letter']

export default function Welcome({ s, config, lang, setLang, onStart, onExample }: Props) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  async function example() {
    if (busy) return
    setBusy(true); setNotice('')
    const form = new FormData(); form.append('sample', 'overcharge')
    try { onExample(await createCase(form, () => {})) }
    catch (e) { setNotice(e instanceof Error ? e.message : s.tryAgain) }
    finally { setBusy(false) }
  }
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
  return <Screen title={s.welcomeTitle} className="welcome-screen" hero={
    <div className="welcome-hero">
      <div className="hero-text">
        <span className="eyebrow hero-eyebrow"><Icon name="pulse" />{s.heroEyebrow}</span>
        <h1 tabIndex={-1}>{s.welcomeTitle}<span className="heading-dot" aria-hidden /></h1>
        <p className="hero-copy">{s.welcomeBody}</p>
        <div className="hero-actions">
          <button type="button" className="btn-primary" disabled={busy} onClick={onStart}>{s.start}<Icon name="arrow" className="directional-icon" /></button>
          <a className="text-link" href="#language-support">{s.languageLink}<Icon name="globe" /></a>
        </div>
      </div>
      <MedicalArt />
    </div>
  }>
    <div className="feature-grid">
      {s.welcomePoints.map((point, i) => <div className="feature-card" key={i}>
        <span className="feature-icon"><Icon name={featureIcons[i]} /></span>
        <div><h2>{s.featureTitles[i]}</h2><p>{point}</p></div>
      </div>)}
    </div>
    <section className="example-strip" aria-labelledby="example-title">
      <span className="example-symbol"><Icon name="search" /></span><div><h2 id="example-title">{s.exampleTitle}</h2><p>{s.exampleHelp}</p></div>
      <button className="btn-secondary" type="button" disabled={busy} onClick={() => void example()} data-testid="welcome-example">{busy ? s.loading : s.tryExample}<Icon name="arrow" className="directional-icon" /></button>
    </section>
    <div className="card language-panel" id="language-support">
      <div className="language-intro"><span className="language-symbol" aria-hidden>文<span>/</span>A</span>
        <h2>{s.languageTitle}</h2><p>{s.languageHelp}</p>
        <div className="language-greetings" aria-hidden><span>Hello</span><i /> <span>Hola</span><i /><span lang="hi">नमस्ते</span><i /><span lang="ar">مرحبا</span></div>
      </div>
      <form className="language-form" onSubmit={(e) => { e.preventDefault(); void detect() }}>
        <label htmlFor="language-text">{s.askPlaceholder}</label>
        <div className="language-input-wrap"><textarea id="language-text" dir="auto" className="field" maxLength={4000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Hola, quiero entender mi factura..." /></div>
        <div className="language-form-bottom"><span className="language-status" role="status">{notice || (lang !== 'en' ? lang.toUpperCase() : s.welcomePoints[1])}</span>
          <button className="btn-secondary" disabled={busy || text.trim().length < 2}>{busy ? s.loading : s.send}<Icon name={busy ? 'pulse' : 'arrow'} className={busy ? 'pulse-icon' : 'directional-icon'} /></button>
        </div>
        {config.demo_mode && <p className="demo-label">Offline demo: English / Español / Монгол</p>}
      </form>
    </div>
  </Screen>
}
