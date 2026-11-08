import type { Strings } from '../strings'
import { Screen } from '../components/Chrome'
import Icon, { MedicalArt, type IconName } from '../components/Icon'
import { LiquidAccordion } from '@/components/ui/liquid-glass-accordion'

interface Props { s: Strings; onStart: () => void }
const featureIcons: IconName[] = ['document', 'globe', 'letter']

export default function Welcome({ s, onStart }: Props) {
  return <Screen title={s.welcomeTitle} className="welcome-screen" hero={
    <div className="welcome-hero">
      <div className="hero-text">
        <span className="eyebrow hero-eyebrow"><Icon name="pulse" />{s.heroEyebrow}</span>
        <h1 tabIndex={-1}>{s.welcomeTitle}<span className="heading-dot" aria-hidden /></h1>
        <p className="hero-copy">{s.welcomeBody}</p>
        <div className="hero-actions">
          <button type="button" className="btn-primary" onClick={onStart}>{s.start}<Icon name="arrow" className="directional-icon" /></button>
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
    <div className="card language-panel" id="language-support">
      <div className="language-intro"><span className="language-symbol" aria-hidden>文<span>/</span>A</span>
        <h2>{s.languageTitle}</h2><p>{s.languageHelp}</p>
        <div className="language-greetings" aria-hidden><span>Hello</span><i /> <span>Hola</span><i /><span lang="hi">नमस्ते</span><i /><span lang="ar">مرحبا</span></div>
      </div>
    </div>
    <section className="faq-band" aria-labelledby="faq-title">
      <h2 id="faq-title">{s.faqTitle}</h2>
      <LiquidAccordion tone="dark" defaultOpen={0} headingLevel={3} items={s.faqItems} style={{ maxWidth: 680 }} />
    </section>
  </Screen>
}
