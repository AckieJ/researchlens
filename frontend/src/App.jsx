import { useEffect, useState } from 'react'
import { api } from './api'
import Setup from './components/Setup.jsx'
import Progress from './components/Progress.jsx'
import Workspace from './components/Workspace.jsx'

const readHash = () => (location.hash.match(/^#\/ws\/([\w-]+)/) || [])[1] || null

export default function App() {
  const [id, setId] = useState(readHash())
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const on = () => { setStatus(null); setId(readHash()) }
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])

  useEffect(() => {
    if (!id) return
    let stop = false
    const tick = async () => {
      try {
        const s = await api.status(id)
        if (stop) return
        setStatus(s); setError('')
        if (!['done', 'error'].includes(s.status)) setTimeout(tick, 2500)
      } catch (e) { if (!stop) { setError(e.message); setTimeout(tick, 5000) } }
    }
    tick()
    return () => { stop = true }
  }, [id])

  const open = (wsId) => { location.hash = `#/ws/${wsId}` }
  const home = () => { location.hash = '' }

  if (!id) return <Setup onCreated={open} onOpen={open} />
  if (error && !status) return <div className="page narrow"><p className="error">{error}</p><button onClick={home}>Back</button></div>
  if (!status) return <div className="page narrow"><p className="muted">Loading workspace…</p></div>
  if (status.status === 'error') return <div className="page narrow"><h2>The investigation stopped</h2><p className="error">{status.error}</p><button onClick={home}>Start over</button></div>
  if (status.status !== 'done' && status.status !== 'evaluating') return <Progress status={status} onHome={home} />
  return <Workspace id={id} status={status} onHome={home} />
}
