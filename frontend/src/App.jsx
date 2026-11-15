import { useEffect, useState } from 'react'
import { api, wake } from './api'
import Setup from './components/Setup.jsx'
import Progress from './components/Progress.jsx'
import Workspace from './components/Workspace.jsx'

const fromHash = () => (window.location.hash.match(/^#\/ws\/([\w-]+)/) || [])[1] || null

export default function App() {
  const [id, setId] = useState(fromHash)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => { wake() }, [])
  useEffect(() => {
    function sync() { setId(fromHash()); setStatus(null); setError('') }
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  useEffect(() => {
    if (!id) return
    let active = true
    let timeout
    let failures = 0
    const tick = async () => {
      try {
        const response = await api.status(id)
        if (!active) return
        failures = 0
        setStatus(response)
        setError('')
        if (!['done', 'error'].includes(response.status)) timeout = setTimeout(tick, 2500)
      } catch (err) {
        if (!active) return
        failures += 1
        setError(`Unable to refresh investigation (${failures} attempt${failures === 1 ? '' : 's'}): ${err.message}`)
        timeout = setTimeout(tick, Math.min(15000, 3000 * failures))
      }
    }
    tick()
    return () => { active = false; clearTimeout(timeout) }
  }, [id, retry])
  const home = () => { window.location.hash = ''; setId(null); setStatus(null); setError('') }
  const open = (wsId) => { window.location.hash = `#/ws/${wsId}` }
  if (!id) return <Setup onCreated={open} onOpen={open} />
  if (status?.status === 'error') return <div className="app-shell"><div className="live-error-screen"><span className="eyebrow">INVESTIGATION ERROR</span><h1>The analysis could not finish.</h1><p>{status.error || 'The backend reported an error.'}</p><div className="live-actions"><button className="primary" onClick={home}>Start another investigation ↗</button><button onClick={async () => { try { await api.retry(id); setStatus(null); setRetry(r => r + 1) } catch (e) { setError(e.message) } }}>Retry this investigation</button><a className="link" href="#" onClick={async (e) => { e.preventDefault(); try { const d = await api.diagnostics(true); alert(JSON.stringify({ problems: d.config_problems, ...Object.fromEntries(Object.entries(d.checks).map(([k, v]) => [k, (v.ok ? 'OK: ' : 'FAIL: ') + v.detail])) }, null, 2)) } catch (err) { alert(err.message) } }}>Run diagnostics</a></div>{error && <p className="inline-error">{error}</p>}<p className="muted small">Workspace ID: {id}</p></div></div>
  if (!status) return <div className="app-shell"><div className="live-loading"><div className="spinner"/><h2>Connecting to your investigation…</h2><p>{error || 'Requesting status from your research backend.'}</p><button onClick={() => setRetry(r => r+1)}>Try again</button><button className="link" onClick={home}>Return home</button></div></div>
  if (status.status !== 'done' && status.status !== 'evaluating') return <Progress status={status} error={error} onRetry={()=>setRetry(r=>r+1)} onHome={home}/>
  return <Workspace id={id} status={status} onHome={home}/>
}
