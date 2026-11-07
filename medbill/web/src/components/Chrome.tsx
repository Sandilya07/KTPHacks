import type { ReactNode } from 'react'
import { fmt, type Strings } from '../strings'

export function Banner({ s }: { s: Strings }) {
  return (
    <div role="note" className="border-b border-slate-200 bg-white px-4 py-2 text-center text-xs text-slate-600">
      {s.banner}
    </div>
  )
}

export function Stepper({ s, step }: { s: Strings; step: number }) {
  return (
    <nav aria-label={fmt(s.stepOf, { n: step + 1, total: s.steps.length, name: s.steps[step] })} className="mx-auto max-w-5xl px-4 pt-4">
      <ol className="flex items-center gap-1.5" role="list">
        {s.steps.map((name, i) => (
          <li key={name} className="flex-1" aria-current={i === step ? 'step' : undefined}>
            <div className={`h-2 rounded-full ${i < step ? 'bg-teal-800' : i === step ? 'bg-teal-600' : 'bg-slate-300'}`} />
            <span className={`mt-1 hidden text-sm sm:block ${i === step ? 'font-semibold text-slate-900' : 'text-slate-600'}`}>{name}</span>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-base font-semibold sm:hidden">{fmt(s.stepOf, { n: step + 1, total: s.steps.length, name: s.steps[step] })}</p>
    </nav>
  )
}

export function Spinner({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" className="card flex items-center gap-4">
      <span aria-hidden className="size-7 animate-spin rounded-full border-4 border-slate-300 border-t-teal-800" />
      <span className="text-lg">{message}</span>
    </div>
  )
}

export function ErrorBox({ s, message, onRetry, extra }: { s: Strings; message: string; onRetry?: () => void; extra?: ReactNode }) {
  return (
    <div role="alert" className="rounded-2xl border-2 border-red-700 bg-red-50 p-5">
      <h2 className="text-xl font-bold text-red-900">{s.errorTitle}</h2>
      <p className="mt-1 text-lg text-red-950">{message}</p>
      <div className="mt-3 flex flex-wrap gap-3">
        {onRetry && <button type="button" className="btn-secondary" onClick={onRetry}>{s.tryAgain}</button>}
        {extra}
      </div>
    </div>
  )
}

export function Screen({ title, children, headingRef }: { title: string; children: ReactNode; headingRef?: React.Ref<HTMLHeadingElement> }) {
  return (
    <section className="mx-auto max-w-5xl px-4 py-6">
      <h1 ref={headingRef} tabIndex={-1} className="mb-4 text-3xl font-bold outline-none">{title}</h1>
      <div className="space-y-5">{children}</div>
    </section>
  )
}
