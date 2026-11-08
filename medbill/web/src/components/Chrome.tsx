import type { ReactNode } from 'react'
import { fmt, type Strings } from '../strings'
import Icon, { type IconName } from './Icon'

export function Banner({ s }: { s: Strings }) {
  return (
    <div role="note" className="privacy-banner">
      <Icon name="shield" /><span>{s.banner}</span>
    </div>
  )
}

const stepIcons: IconName[] = ['home', 'upload', 'document', 'search', 'message', 'letter']

export function Stepper({ s, step, available, onNavigate }: { s: Strings; step: number; available: boolean[]; onNavigate: (step: number) => void }) {
  return (
    <nav aria-label={fmt(s.stepOf, { n: step + 1, total: s.steps.length, name: s.steps[step] })} className="workflow-nav">
      <p className="nav-eyebrow">{s.workspace}</p>
      <ol className="workflow-list" role="list">
        {s.steps.map((name, i) => (
          <li key={i} aria-current={i === step ? 'step' : undefined}>
            <button className={`workflow-step ${i === step ? 'is-current' : ''} ${i < step ? 'is-complete' : ''}`}
              type="button" disabled={!available[i]} aria-current={i === step ? 'step' : undefined}
              title={name}
              onClick={() => onNavigate(i)}>
              <span className="step-icon"><Icon name={i < step ? 'check' : stepIcons[i]} /></span>
              <span className="step-label">{name}</span><span className="step-number" aria-hidden>{String(i + 1).padStart(2, '0')}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="workflow-progress"><span style={{ width: `${((step + 1) / s.steps.length) * 100}%` }} /></div>
      <p className="workflow-caption">{fmt(s.stepOf, { n: step + 1, total: s.steps.length, name: s.steps[step] })}</p>
      <div className="sidebar-care"><span className="sidebar-care-icon"><Icon name="shield" /></span><p>{s.privacyShort}</p><svg viewBox="0 0 180 40" fill="none" aria-hidden><path d="M0 20h40l8-7 10 15L70 3l14 34 11-17h30l6-8 7 8h42" /></svg></div>
    </nav>
  )
}

export function Spinner({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" className="card loading-card">
      <span className="loading-orbit" aria-hidden><Icon name="cross" /></span>
      <div><span className="text-lg font-semibold">{message}</span><div className="loading-dots" aria-hidden><i /><i /><i /></div></div>
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

export function Screen({ title, children, headingRef, hero, className = '' }: { title: string; children: ReactNode; headingRef?: React.Ref<HTMLHeadingElement>; hero?: ReactNode; className?: string }) {
  return (
    <section className={`screen ${className}`}>
      {hero ?? <div className="screen-heading"><h1 ref={headingRef} tabIndex={-1}>{title}</h1><div className="heading-rule" /></div>}
      <div className="screen-content">{children}</div>
    </section>
  )
}
