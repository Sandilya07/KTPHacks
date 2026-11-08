import { useRef, useState } from 'react'
import { createCase } from '../api'
import { ErrorBox, Screen, Spinner } from '../components/Chrome'
import { fmt, type Strings } from '../strings'
import type { CaseView, Config } from '../types'
import Icon from '../components/Icon'

interface Props {
  s: Strings; config: Config; onCase: (c: CaseView) => void; onBack: () => void
  onManual: () => void
}

function DropZone({ label, s, file, setFile, id }: { label: string; s: Strings; file: File | null; setFile: (f: File | null) => void; id: string }) {
  const input = useRef<HTMLInputElement>(null)
  const camera = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const pick = (f?: File | null) => f && setFile(f)
  return (
    <div
      className={`upload-zone ${over ? 'is-over' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]) }}
    >
      <span className="upload-zone-icon"><Icon name={id === 'bill' ? 'document' : 'shield'} /></span>
      <h2 className="text-xl font-semibold" id={`${id}-label`}>{label}</h2>
      <p className="mt-1 text-lg text-slate-700">{s.drop}</p>
      <div className="mt-3 flex flex-wrap justify-center gap-3">
        <button type="button" className="btn-secondary" aria-describedby={`${id}-label`} onClick={() => input.current?.click()}>{s.chooseFile}</button>
        <button type="button" className="btn-secondary" aria-describedby={`${id}-label`} onClick={() => camera.current?.click()}>{s.takePhoto}</button>
      </div>
      <input ref={input} data-testid={`${id}-input`} aria-labelledby={`${id}-label`} className="sr-only" type="file" accept="application/pdf,image/*" onChange={(e) => pick(e.target.files?.[0])} />
      <input ref={camera} aria-hidden tabIndex={-1} className="sr-only" type="file" accept="image/*" capture="environment" onChange={(e) => pick(e.target.files?.[0])} />
      {file && <p className="mt-3 text-lg font-semibold text-green-900" role="status">✓ {fmt(s.fileChosen, { name: file.name })}</p>}
    </div>
  )
}

export default function Upload({ s, config, onCase, onBack, onManual }: Props) {
  const [bill, setBill] = useState<File | null>(null)
  const [eob, setEob] = useState<File | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function submit(form: FormData) {
    setError('')
    setBusy(s.progress.reading)
    try {
      onCase(await createCase(form, (m) => setBusy(s.progress[(m === 'Checking the lines we read' ? 'checking_lines' : 'reading')])))
    } catch (e) {
      setError(e instanceof Error ? e.message : s.loading)
      setBusy('')
    }
  }
  function upload() {
    if (!bill || !eob) { setError(s.needBoth); return }
    const f = new FormData()
    f.append('bill', bill)
    f.append('eob', eob)
    void submit(f)
  }
  function sample(name: string) {
    const f = new FormData()
    f.append('sample', name)
    void submit(f)
  }

  return (
    <Screen title={s.uploadTitle}>
      {busy ? <Spinner message={busy} /> : (
        <>
          {error && <ErrorBox s={s} message={error} extra={<button type="button" className="btn-secondary" onClick={onManual}>{s.startManual}</button>} />}
          <div className="grid gap-5 md:grid-cols-2">
            <DropZone id="bill" label={s.bill} s={s} file={bill} setFile={setBill} />
            <DropZone id="eob" label={s.eob} s={s} file={eob} setFile={setEob} />
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" className="btn-primary text-xl" onClick={upload}>{s.readDocs}</button>
            <button type="button" className="btn-secondary" onClick={onBack}>{s.back}</button>
          </div>
          <div className="card sample-section">
            <p className="text-lg font-semibold">{s.orSample}</p>
            <div className="sample-grid">
              {Object.entries(config.samples).map(([key, label]) => (
                <div key={key} className="sample-card">
                  <span className="sample-icon"><Icon name={key.includes('photo') ? 'upload' : 'document'} /></span>
                  <button type="button" data-testid={`sample-${key}`} onClick={() => sample(key)}>{label}</button>
                  <div className="sample-links">
                    <a href={`/api/samples/${key}/bill`} download>{s.bill}</a>
                    <a href={`/api/samples/${key}/eob`} download>{s.eob}</a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </Screen>
  )
}
