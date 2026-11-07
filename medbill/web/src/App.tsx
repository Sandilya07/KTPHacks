import { useEffect, useRef, useState } from 'react'
import { deleteCase, getConfig } from './api'
import { Banner, ErrorBox, Screen, Spinner, Stepper } from './components/Chrome'
import Upload from './screens/Upload'
import Welcome from './screens/Welcome'
import { t } from './strings'
import type { CaseView, Config } from './types'

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [configError, setConfigError] = useState('')
  const [lang, setLang] = useState('en')
  const [step, setStep] = useState(0)
  const [kase, setCase] = useState<CaseView | null>(null)
  const main = useRef<HTMLElement>(null)
  const s = t(lang)

  useEffect(() => { getConfig().then(setConfig).catch(() => setConfigError('The server is not reachable. Please start the API and reload.')) }, [])
  useEffect(() => { document.documentElement.lang = lang; main.current?.querySelector('h1')?.focus() }, [lang, step])

  async function restart() {
    if (kase) await deleteCase(kase.case_id)
    setCase(null)
    setStep(0)
  }

  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-3">{s.skip}</a>
      <Banner s={s} />
      <header className="mx-auto flex max-w-5xl items-center justify-between px-4 pt-4">
        <span className="text-xl font-bold text-blue-900">{s.appName}</span>
        {kase && <button type="button" className="btn-secondary min-h-10 text-base" onClick={restart}>{s.deleteData}</button>}
      </header>
      <Stepper s={s} step={step} />
      <main id="main" ref={main}>
        {configError && <Screen title={s.errorTitle}><ErrorBox s={s} message={configError} onRetry={() => location.reload()} /></Screen>}
        {!config && !configError && <Screen title={s.appName}><Spinner message={s.loading} /></Screen>}
        {config && step === 0 && <Welcome s={s} config={config} lang={lang} setLang={setLang} onStart={() => setStep(1)} />}
        {config && step === 1 && <Upload s={s} config={config} onCase={(c) => { setCase(c); setStep(2) }} onBack={() => setStep(0)} onManual={() => setStep(2)} />}
        {config && step === 2 && <Screen title={s.reviewTitle}><p>{kase?.case_id}</p></Screen>}
      </main>
    </>
  )
}
