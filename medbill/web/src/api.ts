import type { AskResult, AuditResult, CaseView, Config, CorrectionResult, LetterResult } from './types'

const BASE = '/api'

export class ApiProblem extends Error {}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = 'Something went wrong. Please try again.'
    try { msg = (await res.json()).detail ?? msg } catch { /* keep the plain message */ }
    throw new ApiProblem(typeof msg === 'string' ? msg : 'Please check the values you entered.')
  }
  return res.json() as Promise<T>
}

export const getConfig = () => fetch(`${BASE}/config`).then((r) => json<Config>(r))

/** POST that streams server-sent events (fetch, because EventSource cannot POST). */
async function streamPost<T>(url: string, body: BodyInit | undefined, onProgress: (message: string) => void): Promise<T> {
  const res = await fetch(`${BASE}${url}${url.includes('?') ? '&' : '?'}stream=1`, { method: 'POST', body })
  if (!res.ok || !res.body) return json<T>(res)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let result: T | undefined
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let i: number
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i)
      buf = buf.slice(i + 2)
      const name = /^event: (.*)$/m.exec(chunk)?.[1]
      const data = JSON.parse(/^data: (.*)$/m.exec(chunk)?.[1] ?? '{}')
      if (name === 'progress') onProgress(data.message)
      else if (name === 'error') throw new ApiProblem(data.message)
      else if (name === 'result') result = data as T
    }
  }
  if (!result) throw new ApiProblem('The connection closed early. Please try again.')
  return result
}

export function createCase(form: FormData, onProgress: (m: string) => void) {
  return streamPost<CaseView>('/cases', form, onProgress)
}
export const patchLines = (id: string, body: object) =>
  fetch(`${BASE}/cases/${id}/lines`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((r) => json<CaseView>(r))
export const confirmCase = (id: string) => fetch(`${BASE}/cases/${id}/confirm`, { method: 'POST' }).then((r) => json<CaseView>(r))
export const runAudit = (id: string, lang: string, onProgress: (m: string) => void) =>
  streamPost<AuditResult>(`/cases/${id}/audit?lang=${lang}`, undefined, onProgress)
export const previewCorrection = (id: string, line_id: string, patient_owed: number) =>
  fetch(`${BASE}/cases/${id}/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ line_id, patient_owed }) })
    .then((r) => json<CorrectionResult>(r))

export async function downloadEvidenceReport(id: string) {
  const response = await fetch(`${BASE}/cases/${id}/report`)
  if (!response.ok) { await json(response); return }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url; link.download = 'medbill-evidence-report.pdf'
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export const askQuestion = (id: string, question: string, language = 'auto', history: { role: 'user' | 'assistant'; text: string }[] = []) =>
  fetch(`${BASE}/cases/${id}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, language, history }) }).then((r) => json<AskResult>(r))
export const letterUrl = (id: string, p: Record<string, string>) => `${BASE}/cases/${id}/letter?${new URLSearchParams(p)}`
export const getLetter = (id: string, p: Record<string, string>) => fetch(letterUrl(id, { ...p, format: 'json' })).then((r) => json<LetterResult>(r))
export const sourceUrl = (id: string, doc: string, page: number) => `${BASE}/cases/${id}/source/${page}?doc=${doc}`
export const deleteCase = (id: string) => fetch(`${BASE}/cases/${id}`, { method: 'DELETE' }).catch(() => undefined)

export function createManual() {
  const today = new Date().toISOString().slice(0, 10)
  const body = {
    bill: { patient_balance: 0, lines: [{ id: 'B1', date: today, code: '', billed: 0, patient_owed: 0 }] },
    eob: { lines: [{ id: 'E1', date: today, code: '', allowed: 0, plan_paid: 0, patient_resp: 0 }] },
  }
  return fetch(`${BASE}/cases/manual`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((r) => json<CaseView>(r))
}

export const detectLanguage = (text: string, strings: Record<string, string>, language?: string) =>
  fetch(BASE + '/language', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, strings, language }) })
    .then((r) => json<{ language: string; strings: Record<string, string>; notice?: string }>(r))
