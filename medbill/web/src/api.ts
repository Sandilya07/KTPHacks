import type { AskResult, AuditResult, CaseView, Config, LetterResult } from './types'

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
export const askQuestion = (id: string, question: string, language: string) =>
  fetch(`${BASE}/cases/${id}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, language }) }).then((r) => json<AskResult>(r))
export const letterUrl = (id: string, p: Record<string, string>) => `${BASE}/cases/${id}/letter?${new URLSearchParams(p)}`
export const getLetter = (id: string, p: Record<string, string>) => fetch(letterUrl(id, { ...p, format: 'json' })).then((r) => json<LetterResult>(r))
export const sourceUrl = (id: string, doc: string, page: number) => `${BASE}/cases/${id}/source/${page}?doc=${doc}`
export const deleteCase = (id: string) => fetch(`${BASE}/cases/${id}`, { method: 'DELETE' }).catch(() => undefined)
