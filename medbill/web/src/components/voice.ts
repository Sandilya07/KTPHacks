// Browser speech helpers (Web Speech API). Everything degrades gracefully: if the browser or the
// device has no support or no voice for a language, the buttons explain it instead of failing.
interface Recognition {
  lang: string; interimResults: boolean; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onend: (() => void) | null; onerror: (() => void) | null; start: () => void; stop: () => void
}
type RecognitionCtor = new () => Recognition

export function recognitionSupported(): boolean {
  const w = window as unknown as Record<string, unknown>
  return Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition)
}

export function listen(lang: string, onText: (t: string) => void, onEnd: () => void): () => void {
  const w = window as unknown as Record<string, RecognitionCtor | undefined>
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition
  if (!Ctor) { onEnd(); return () => undefined }
  const rec = new Ctor()
  rec.lang = lang
  rec.interimResults = false
  rec.onresult = (e) => onText(Array.from(e.results).map((r) => r[0].transcript).join(' '))
  rec.onend = onEnd
  rec.onerror = onEnd
  rec.start()
  return () => rec.stop()
}

export function voiceFor(speechLang: string): SpeechSynthesisVoice | undefined {
  if (!('speechSynthesis' in window)) return undefined
  const prefix = speechLang.slice(0, 2).toLowerCase()
  return window.speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith(prefix))
}

/** Returns false when this device has no voice for the language. */
export function speak(text: string, speechLang: string): boolean {
  const voice = voiceFor(speechLang)
  if (!voice) return false
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.voice = voice
  u.lang = voice.lang
  window.speechSynthesis.speak(u)
  return true
}
