import type { Config } from '../types'
import { type Strings } from '../strings'
import { Screen } from '../components/Chrome'

interface Props { s: Strings; config: Config; lang: string; setLang: (l: string) => void; onStart: () => void }

export default function Welcome({ s, config, lang, setLang, onStart }: Props) {
  return (
    <Screen title={s.welcomeTitle}>
      <fieldset className="card">
        <legend className="px-1 text-xl font-semibold">{s.chooseLanguage}</legend>
        <div className="mt-2 flex flex-wrap gap-3">
          {config.languages.map((l) => (
            <label key={l.code} className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-xl border-2 px-4 py-2 text-lg ${lang === l.code ? 'border-blue-800 bg-blue-50 font-semibold' : 'border-slate-400 bg-white'}`}>
              <input type="radio" name="language" className="size-5 accent-blue-800" checked={lang === l.code} onChange={() => setLang(l.code)} lang={l.code} />
              <span lang={l.code}>{l.name}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="card">
        <p className="text-xl">{s.welcomeBody}</p>
        <ul className="mt-4 list-disc space-y-1 ps-6 text-lg">
          {s.welcomePoints.map((p) => <li key={p}>{p}</li>)}
        </ul>
      </div>
      <button type="button" className="btn-primary text-xl" onClick={onStart}>{s.start}</button>
    </Screen>
  )
}
