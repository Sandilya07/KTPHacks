import type { CSSProperties } from 'react'

export type IconName = 'cross' | 'pulse' | 'upload' | 'document' | 'check' | 'shield' | 'message' | 'letter' | 'arrow' | 'globe' | 'trash' | 'search' | 'home' | 'heart'

const paths: Record<IconName, React.ReactNode> = {
  heart: <path d="M12 20s-8-4.8-8-10.5A4.5 4.5 0 0112 7a4.5 4.5 0 018 2.5C20 15.2 12 20 12 20z" />,
  cross: <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6Z" />,
  pulse: <path d="M2 12h5l3-8 4 16 3-8h5" />,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" /></>,
  document: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" /><path d="M14 3v6h6M8 13h8m-8 4h5" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  shield: <><path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6Z" /><path d="m8 12 3 3 5-6" /></>,
  message: <><path d="M21 11a8 8 0 0 1-8 8H6l-4 3V11a9 9 0 0 1 19 0Z" /><path d="M7 10h10m-10 4h6" /></>,
  letter: <><rect x="3" y="5" width="18" height="15" rx="3" /><path d="m3 7 9 7 9-7" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z" /></>,
  trash: <><path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7" /></>,
  search: <><circle cx="10" cy="10" r="7" /><path d="m15 15 6 6" /></>,
  home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" /><path d="M9 21v-8h6v8" /></>,
}

export default function Icon({ name, className = '', style }: { name: IconName; className?: string; style?: CSSProperties }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`icon ${className}`} style={style}>{paths[name]}</svg>
}

export function MedicalArt() {
  return <div className="medical-art" aria-hidden="true">
    <div className="art-orbit art-orbit-outer" /><div className="art-orbit art-orbit-inner" />
    <div className="art-spark spark-one">+</div><div className="art-spark spark-two">+</div>
    <div className="art-paper art-paper-back" />
    <div className="art-paper art-paper-front">
      <div className="art-paper-top"><span className="art-medical-mark"><Icon name="cross" /></span><span className="art-paper-code" /></div>
      <div className="art-paper-title" /><div className="art-paper-subtitle" />
      {[0, 1, 2].map((line) => <div className={`art-bill-line art-bill-line-${line}`} key={line}><span /><i /><b /></div>)}
      <div className="art-paper-total"><span /><b /></div>
      <svg className="art-pulse" viewBox="0 0 200 45" fill="none"><path d="M0 23h48l9-9 10 19 13-31 16 41 12-20h27l7-9 8 9h50" /></svg>
    </div>
    <div className="art-check-card"><span><Icon name="check" /></span><div><i /><b /></div><Icon name="shield" /></div>
    <div className="art-heart-card"><Icon name="pulse" /></div>
  </div>
}
