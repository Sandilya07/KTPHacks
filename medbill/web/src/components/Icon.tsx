import type { ReactNode } from 'react'

export type IconName =
  | 'cross' | 'globe' | 'trash' | 'arrow' | 'shield' | 'search' | 'document'
  | 'check' | 'upload' | 'pulse' | 'home' | 'message' | 'letter' | 'heart'

const paths: Record<IconName, ReactNode> = {
  cross: <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" />,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" /></>,
  trash: <path d="M4 7h16M10 3h4M6 7l1 13h10l1-13M10 11v6M14 11v6" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  shield: <><path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></>,
  document: <><path d="M6 3h8l5 5v13H6z" /><path d="M14 3v5h5M9 13h7M9 17h7" /></>,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M4 16v4h16v-4" />,
  pulse: <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />,
  home: <path d="M4 11l8-7 8 7M6 10v10h12V10M10 20v-6h4v6" />,
  message: <path d="M4 5h16v11H9l-5 4z" />,
  letter: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" /></>,
  heart: <path d="M12 20s-8-4.8-8-10.5A4.5 4.5 0 0112 7a4.5 4.5 0 018 2.5C20 15.2 12 20 12 20z" />,
}

export default function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return (
    <svg className={`icon ${className}`.trim()} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden focusable="false">
      {paths[name]}
    </svg>
  )
}

/** Decorative hero illustration on the welcome screen (purely visual). */
export function MedicalArt() {
  return (
    <div className="medical-art" aria-hidden>
      <div className="art-orbit" />
      <div className="art-orbit art-orbit-inner" />
      <div className="art-paper art-paper-back" />
      <div className="art-paper art-paper-front">
        <div className="art-paper-top">
          <span className="art-medical-mark"><Icon name="cross" /></span>
          <span className="art-paper-code" />
        </div>
        <div className="art-paper-title" />
        <div className="art-paper-subtitle" />
        <div className="art-bill-line art-bill-line-1"><span /><i /><b /></div>
        <div className="art-bill-line"><span /><i /><b /></div>
        <div className="art-bill-line"><span /><i /><b /></div>
        <div className="art-paper-total"><span /><b /></div>
        <svg className="art-pulse" viewBox="0 0 180 27" fill="none"><path d="M0 14h50l8-7 9 15 9-18 10 22 8-12h86" /></svg>
      </div>
      <div className="art-check-card">
        <span><Icon name="check" /></span>
        <div><i /><b /></div>
        <Icon name="shield" />
      </div>
      <div className="art-heart-card"><Icon name="heart" /></div>
      <span className="art-spark" style={{ left: '14%', top: '30%' }}>+</span>
      <span className="art-spark" style={{ right: '12%', top: '62%' }}>+</span>
    </div>
  )
}
