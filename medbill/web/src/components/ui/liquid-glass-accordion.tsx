"use client"

/**
 * Nimbus UI · Liquid Accordion — static glass edition.
 * Based on the "Spillway" accordion by guglielmogiannattasio.it (MIT). The WebGL water, droplets, ripples and
 * motion were removed on request: this version is a plain frosted-glass accordion. Real buttons, aria-expanded,
 * arrow/Home/End keys. The open question sits on a slightly brighter pane of glass. No dependencies besides React.
 */

import * as React from "react"

export type LiquidAccordionItem = {
  question: string
  answer: React.ReactNode
  id?: string
}

export type LiquidAccordionProps = {
  items?: LiquidAccordionItem[]
  /** index open at start (null = all closed) */
  defaultOpen?: number | null
  /** controlled open index */
  open?: number | null
  onOpenChange?: (index: number | null) => void
  /** allow closing the open item (default true) */
  collapsible?: boolean
  /** "light" glass for bright backgrounds, "dark" for dark ones */
  tone?: "light" | "dark"
  /** heading level of each question (default 3) */
  headingLevel?: 2 | 3 | 4 | 5 | 6
  className?: string
  style?: React.CSSProperties
}

const DEFAULT_ITEMS: LiquidAccordionItem[] = [
  { question: "What is this?", answer: "A frosted-glass accordion. Open a question to read its answer." },
  { question: "Does it need WebGL?", answer: "No. It is plain HTML and CSS." },
  { question: "Is it accessible?", answer: "Yes: real buttons, aria-expanded and arrow keys." },
]

const R = 20 // pane corner radius

const NF_CSS = `
.nimbus-faq{--f-tint:rgba(255,255,255,.22);--f-fg:#0B132B;--f-soft:rgba(11,19,43,.74);--f-line:rgba(11,19,43,.1);--f-rim:rgba(255,255,255,.72);--f-open:rgba(255,255,255,.34);
  position:relative;box-sizing:border-box;width:100%;max-width:640px;padding:8px;border-radius:28px;isolation:isolate;
  font-family:ui-sans-serif,-apple-system,"SF Pro Text","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased;-webkit-tap-highlight-color:transparent;
  background:var(--f-tint);-webkit-backdrop-filter:blur(18px) saturate(1.25);backdrop-filter:blur(18px) saturate(1.25);
  box-shadow:inset 0 1px 1px var(--f-rim),inset 0 0 0 1px rgba(255,255,255,.2),0 18px 44px -20px rgba(0,40,90,.5)}
.nimbus-faq[data-tone="dark"]{--f-tint:rgba(255,255,255,.07);--f-fg:#F1F7FF;--f-soft:rgba(241,247,255,.8);--f-line:rgba(241,247,255,.12);--f-rim:rgba(255,255,255,.28);--f-open:rgba(255,255,255,.12);
  box-shadow:inset 0 1px 1px var(--f-rim),inset 0 0 0 1px rgba(255,255,255,.12),0 18px 44px -20px rgba(0,0,0,.7)}
.nf-item{position:relative;border-radius:${R}px}
.nf-item+.nf-item::before{content:"";position:absolute;left:22px;right:22px;top:0;height:1px;background:var(--f-line)}
.nf-item[data-open="true"]{background:var(--f-open);box-shadow:inset 0 1px 1px var(--f-rim),inset 0 0 0 1px rgba(255,255,255,.16)}
.nf-item[data-open="true"]::before,.nf-item[data-open="true"]+.nf-item::before{opacity:0}
.nf-h{margin:0;font:inherit}
.nf-q{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:16px;width:100%;min-height:58px;padding:14px 14px 14px 22px;border-radius:${R}px;cursor:pointer;
  color:var(--f-fg);font-weight:560;font-size:15px;line-height:1.35;letter-spacing:-.01em;user-select:none;-webkit-user-select:none}
.nf-q:focus-visible{outline:2px solid #6fe0c5;outline-offset:-2px}
.nf-qt{flex:1;min-width:0}
.nf-ico{position:relative;flex:none;width:28px;height:28px;border-radius:50%;color:var(--f-fg);background:rgba(255,255,255,.12);
  box-shadow:inset 0 1px 1px var(--f-rim),inset 0 0 0 1px rgba(255,255,255,.18)}
.nf-ico::before,.nf-ico::after{content:"";position:absolute;left:50%;top:50%;width:11px;height:1.8px;margin:-.9px 0 0 -5.5px;border-radius:2px;background:currentColor}
.nf-ico::after{transform:rotate(90deg)}
.nf-item[data-open="true"] .nf-ico::after{display:none}
.nf-a{padding:0 64px 22px 22px;color:var(--f-soft);font-size:14px;line-height:1.62}
.nf-a>*:first-child{margin-top:0}.nf-a>*:last-child{margin-bottom:0}
@media (max-width:520px){.nf-q{padding-left:18px;font-size:14.5px}.nf-a{padding:0 18px 20px 18px}}
`

export function LiquidAccordion({
  items = DEFAULT_ITEMS,
  defaultOpen = 0,
  open,
  onOpenChange,
  collapsible = true,
  tone = "light",
  headingLevel = 3,
  className,
  style,
}: LiquidAccordionProps) {
  const [inner, setInner] = React.useState<number | null>(defaultOpen)
  const current = open !== undefined ? open : inner
  const uid = React.useId().replace(/:/g, "")
  const btnRefs = React.useRef<(HTMLButtonElement | null)[]>([])
  const H = `h${headingLevel}` as "h3"

  const toggle = (i: number) => {
    const next = current === i ? (collapsible ? null : i) : i
    if (next === current) return
    if (open === undefined) setInner(next)
    onOpenChange?.(next)
  }

  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    const n = items.length
    let j = -1
    if (e.key === "ArrowDown") j = (i + 1) % n
    else if (e.key === "ArrowUp") j = (i - 1 + n) % n
    else if (e.key === "Home") j = 0
    else if (e.key === "End") j = n - 1
    if (j < 0) return
    e.preventDefault()
    btnRefs.current[j]?.focus()
  }

  return (
    <div className={["nimbus-faq", className].filter(Boolean).join(" ")} data-tone={tone} style={style}>
      <style dangerouslySetInnerHTML={{ __html: NF_CSS }} />
      {items.map((it, i) => {
        const isOpen = current === i
        const base = `${uid}-${it.id ?? i}`
        return (
          <div className="nf-item" key={it.id ?? i} data-open={isOpen}>
            <H className="nf-h">
              <button
                ref={(el) => { btnRefs.current[i] = el }}
                type="button"
                id={`${base}-q`}
                className="nf-q"
                aria-expanded={isOpen}
                aria-controls={`${base}-a`}
                aria-disabled={isOpen && !collapsible ? true : undefined}
                onClick={() => toggle(i)}
                onKeyDown={(e) => onKeyDown(e, i)}
              >
                <span className="nf-qt">{it.question}</span>
                <span className="nf-ico" aria-hidden="true" />
              </button>
            </H>
            <div id={`${base}-a`} role="region" aria-labelledby={`${base}-q`} hidden={!isOpen}>
              <div className="nf-a">{it.answer}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** alias for registries that import { Component } */
export { LiquidAccordion as Component }

export default LiquidAccordion
