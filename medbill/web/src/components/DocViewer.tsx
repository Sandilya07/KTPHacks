import { useEffect, useMemo, useRef, useState } from 'react'
import { sourceUrl } from '../api'
import type { CaseView, Doc, Highlight } from '../types'
import type { Strings } from '../strings'

export interface Box { doc: Doc; page: number; bbox: [number, number, number, number] }

/** Map every line id (bill "B1", EOB "E1") to where it sits on its page image. */
export function boxesOf(c: CaseView): Record<string, Box> {
  const out: Record<string, Box> = {}
  for (const doc of ['bill', 'eob'] as const) {
    for (const l of c[doc].lines) if (l.source) out[l.id] = { doc, page: l.source.page, bbox: l.source.bbox }
  }
  return out
}

interface Props { s: Strings; kase: CaseView; highlight: Highlight; className?: string; scrollToHighlight?: boolean }

export default function DocViewer({ s, kase, highlight, className = '', scrollToHighlight = true }: Props) {
  const boxes = useMemo(() => boxesOf(kase), [kase])
  const lit = highlight.ids.filter((id) => boxes[id])
  const [doc, setDoc] = useState<Doc>('bill')
  const first = useRef<HTMLDivElement | null>(null)
  const panel = useRef<HTMLDivElement | null>(null)

  // Switch to the document that holds the highlighted line, then scroll it into view.
  useEffect(() => {
    if (lit.length && boxes[lit[0]].doc !== doc) setDoc(boxes[lit[0]].doc)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlight.nonce])
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (scrollToHighlight) first.current?.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' })
    else if (first.current && panel.current) {
      const target = first.current.getBoundingClientRect()
      const bounds = panel.current.getBoundingClientRect()
      panel.current.scrollTo({ top: panel.current.scrollTop + target.top - bounds.top - bounds.height / 2 + target.height / 2,
        behavior: reduce ? 'auto' : 'smooth' })
    }
  }, [highlight.nonce, doc])

  const names: Record<Doc, string> = { bill: s.billTab, eob: s.eobTab }
  const dims = kase.pages[doc]
  const count = (d: Doc) => lit.filter((id) => boxes[id].doc === d).length
  let firstSet = false

  return (
    <div className={`card ${className}`} data-testid="doc-viewer">
      <div role="tablist" aria-label={s.yourDocument} className="mb-3 flex gap-2">
        {(['bill', 'eob'] as const).map((d) => (
          <button key={d} role="tab" type="button" id={`tab-${d}`} aria-selected={doc === d} aria-controls="doc-panel"
            className="doc-tab"
            onClick={() => setDoc(d)}>
            {names[d]}{count(d) > 0 && <span aria-label={`${count(d)} highlighted`} className="ms-2 rounded-full bg-yellow-300 px-2 text-sm">{count(d)}</span>}
          </button>
        ))}
      </div>
      <div ref={panel} id="doc-panel" role="tabpanel" aria-labelledby={`tab-${doc}`} tabIndex={0} className="max-h-[70vh] overflow-auto rounded-lg border border-slate-300 bg-slate-100">
        {dims.length === 0 && <p className="p-4">{s.noPreview}</p>}
        {dims.map((dim, page) => (
          <div key={page} className="relative" style={{ aspectRatio: `${dim.width} / ${dim.height}` }}>
            <img src={sourceUrl(kase.case_id, doc, page)} alt={`${names[doc]}, page ${page + 1}`} className="absolute inset-0 size-full select-none" draggable={false} />
            {lit.filter((id) => boxes[id].doc === doc && boxes[id].page === page).map((id) => {
              const [x0, y0, x1, y1] = boxes[id].bbox
              const ref = !firstSet ? ((firstSet = true), first) : undefined
              return (
                <div key={id} ref={ref} role="img" aria-label={`${s.evidenceShown}: ${id}`} data-testid={`highlight-${id}`}
                  className="absolute rounded-sm border-4 border-blue-700 bg-yellow-300/30"
                  style={{ left: `${(x0 / dim.width) * 100}%`, top: `${(y0 / dim.height) * 100}%`, width: `${((x1 - x0) / dim.width) * 100}%`, height: `${((y1 - y0) / dim.height) * 100}%` }} />
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
