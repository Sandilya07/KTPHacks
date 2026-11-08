import { useEffect, useRef } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import ShaderBackground from './ShaderBackground'
import Icon from './Icon'

const HEADLINE = "Language shouldn't hold you back from understanding your medical bills."
const GREETINGS = [
  { text: 'Hello', lang: 'en' }, { text: 'Hola', lang: 'es' }, { text: 'Сайн уу', lang: 'mn' },
  { text: 'Bonjour', lang: 'fr' }, { text: 'नमस्ते', lang: 'hi' }, { text: 'مرحبا', lang: 'ar' }, { text: '你好', lang: 'zh' },
]

/** Full-screen welcome shown every time someone opens the site. Dismiss with the button or Escape. */
export default function Intro({ onDone }: { onDone: () => void }) {
  const button = useRef<HTMLButtonElement>(null)
  const still = useReducedMotion()
  const words = HEADLINE.split(' ')

  useEffect(() => {
    button.current?.focus()
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onDone() }
    window.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = previous; window.removeEventListener('keydown', onKey) }
  }, [onDone])

  return (
    <motion.div role="dialog" aria-modal="true" aria-labelledby="intro-title" aria-describedby="intro-body" data-testid="intro"
      className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden bg-[#03120e] px-4"
      initial={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: still ? 0 : 0.6 } }}>
      <ShaderBackground />
      {/* A dark scrim keeps the white text readable over the brightest part of the shader. */}
      <div aria-hidden className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(3,18,14,.72),rgba(3,18,14,.35)_70%)]" />
      <div className="relative z-10 mx-auto flex max-w-3xl flex-col items-center text-center text-white">
        <motion.span initial={still ? false : { opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
          className="mb-6 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white/15 ring-1 ring-white/30 backdrop-blur">
          <Icon name="cross" className="!h-6 !w-6" />
        </motion.span>
        <h1 id="intro-title" className="!text-white text-[clamp(2.1rem,6vw,4rem)] font-bold leading-[1.1] tracking-tight [text-shadow:0_2px_24px_rgba(3,18,14,.6)]">
          {words.map((word, i) => (
            <motion.span key={i} className="mr-[0.28em] inline-block"
              initial={still ? false : { opacity: 0, y: 24, filter: 'blur(8px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              transition={{ delay: 0.25 + i * 0.09, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>{word}</motion.span>
          ))}
        </h1>
        <motion.p id="intro-body" className="mt-6 max-w-xl text-lg text-white/90 [text-shadow:0_1px_12px_rgba(3,18,14,.7)]"
          initial={still ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 + words.length * 0.09 + 0.2, duration: 0.8 }}>
          Upload your bill, ask your questions in your own language, and see exactly what to challenge.
        </motion.p>
        <motion.div className="mt-8 flex flex-col items-center gap-6"
          initial={still ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 + words.length * 0.09 + 0.5, duration: 0.7 }}>
          <button ref={button} type="button" onClick={onDone}
            className="inline-flex items-center gap-2 rounded-full bg-white px-8 py-3.5 text-lg font-semibold text-[#0b4a3a] shadow-[0_10px_40px_rgba(3,18,14,.45)] hover:bg-[#f4ffc7] hover:-translate-y-0.5 focus-visible:outline-white">
            Get started<Icon name="arrow" className="directional-icon" />
          </button>
          <p aria-hidden className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-sm text-white/80">
            {GREETINGS.map((g) => <span key={g.lang} lang={g.lang}>{g.text}</span>)}
          </p>
        </motion.div>
      </div>
    </motion.div>
  )
}
