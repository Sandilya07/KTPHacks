import { useEffect, useRef, useState } from 'react'
import { createManual, deleteCase, getConfig } from './api'
import { Banner, ErrorBox, Screen, Spinner, Stepper } from './components/Chrome'
import { AnimatePresence } from 'framer-motion'
import Icon from './components/Icon'
import Intro from './components/Intro'
import ShaderBackground from './components/ShaderBackground'
import Ask, { type Msg } from './screens/Ask'
import Letter from './screens/Letter'
import Results from './screens/Results'
import Review from './screens/Review'
import Upload from './screens/Upload'
import Welcome from './screens/Welcome'
import { t, translatedStrings, languageDirection, type Strings } from './strings'
import type { AuditResult, CaseView, Config, Highlight } from './types'

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [configError, setConfigError] = useState('')
  const [lang, setLang] = useState('en')
  const [step, setStep] = useState(0)
  // The intro shows on every visit; `?intro=0` skips it (used by the automated browser tests).
  const [intro, setIntro] = useState(() => new URLSearchParams(location.search).get('intro') !== '0')
  const [kase, setCase] = useState<CaseView | null>(null)
  const [audit, setAudit] = useState<AuditResult | null>(null)
  const [auditKey, setAuditKey] = useState('')
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [highlight, setHighlight] = useState<Highlight>({ ids: [], nonce: 0 })
  const main = useRef<HTMLElement>(null)
  const [copy, setCopy] = useState<Strings | null>(null)
  const s = copy ?? t(lang)
  const available = [true, true, Boolean(kase), Boolean(kase?.confirmed) && step !== 2, Boolean(kase?.confirmed) && step !== 2, Boolean(kase?.confirmed) && step !== 2]
  const localeName = (() => { try { return new Intl.DisplayNames([lang], { type: 'language' }).of(lang) ?? lang } catch { return lang } })()
  function languageChanged(code: string, values?: Record<string, string>) {
    setLang(code)
    setCopy(values ? translatedStrings(code, values) : null)
  }

  // While the intro is up, the app behind it is removed from layout, focus order and the page height.
  useEffect(() => {
    document.documentElement.toggleAttribute('data-intro', intro)
    if (intro) return
    // A link like /#language-support could not scroll while the app was hidden; do it once the intro closes.
    const target = location.hash.length > 1 ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null
    if (target) requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }))
  }, [intro])
  useEffect(() => { getConfig().then(setConfig).catch(() => setConfigError('The server is not reachable. Please start the API and reload.')) }, [])
  useEffect(() => { document.documentElement.lang = lang; document.documentElement.dir = languageDirection(lang) }, [lang])
  // Move focus to the new screen's heading when the step changes (not on first load, and not when the
  // language changes, which would pull focus away from the control being used).
  const shownStep = useRef(step) // compare with the last step we focused: robust to StrictMode double effects
  useEffect(() => {
    if (shownStep.current === step) return
    shownStep.current = step
    main.current?.querySelector('h1')?.focus()
  }, [step])

  async function restart() {
    if (kase) await deleteCase(kase.case_id)
    setCase(null)
    setAudit(null)
    setAuditKey('')
    setMsgs([])
    setHighlight({ ids: [], nonce: 0 })
    setStep(0)
  }

  return (
    <>
      <AnimatePresence>{intro && <Intro key="intro" onDone={() => setIntro(false)} />}</AnimatePresence>
      {/* Same "Mesh drift" shader as the intro, rendered small and capped at 30fps as a calm backdrop for the whole app. */}
      {!intro && <div className="app-backdrop" aria-hidden><ShaderBackground resolution={0.4} fps={30} /></div>}
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-3">{s.skip}</a>
      <Banner s={s} />
      <header className="app-header">
        <div className="header-inner">
          <button type="button" className="brand" onClick={() => setStep(0)}>
            <span className="brand-mark"><Icon name="cross" /></span><span>{s.appName}<small>{s.heroEyebrow}</small></span>
          </button>
          <div className="header-tools">
            <span className="locale-badge"><Icon name="globe" /><span lang={lang} title={localeName}>{localeName}</span><i aria-hidden /></span>
            {kase && <button type="button" className="header-reset" aria-label={s.deleteData} onClick={restart}><Icon name="trash" /><span>{s.deleteData}</span></button>}
          </div>
        </div>
      </header>
      <div className="app-shell">
      <aside className="app-sidebar"><Stepper s={s} step={step} available={available} onNavigate={(next) => { if (available[next]) setStep(next) }} /></aside>
      <main id="main" ref={main} data-step={step}>
        <div className="page-transition" key={step}>
        {configError && <Screen title={s.errorTitle}><ErrorBox s={s} message={configError} onRetry={() => location.reload()} /></Screen>}
        {!config && !configError && <Screen title={s.appName}><Spinner message={s.loading} /></Screen>}
        {config && step === 0 && <Welcome s={s} onStart={() => setStep(1)} />}
        {config && step === 1 && <Upload s={s} config={config} onCase={(c) => { setCase(c); setStep(2) }} onBack={() => setStep(0)} onManual={() => createManual().then((c) => { setCase(c); setStep(2) })} />}
        {config && step === 2 && kase && <Review key={kase.case_id} s={s} kase={kase} onConfirmed={(c) => { setCase(c); setAudit(null); setAuditKey(''); setMsgs([]); setHighlight({ ids: [], nonce: 0 }); setStep(3) }} onBack={() => setStep(1)} />}
        {config && step === 3 && kase && <Results s={s} lang={lang} kase={kase} audit={audit} auditKey={auditKey} setAudit={(a, k) => { setAudit(a); setAuditKey(k) }} highlight={highlight} setHighlight={setHighlight} onAsk={() => setStep(4)} onLetter={() => setStep(5)} onBack={() => setStep(2)} />}
        {config && step === 5 && kase && <Letter s={s} lang={lang} kase={kase} onBack={() => setStep(4)} />}
        {config && step === 4 && kase && <Ask onLanguage={languageChanged} s={s} config={config} lang={lang} kase={kase} audit={audit} msgs={msgs} setMsgs={setMsgs} onJump={(h) => { setHighlight(h); setStep(3) }} onLetter={() => setStep(5)} onBack={() => setStep(3)} />}
        </div>
      </main>
      </div>
    </>
  )
}
