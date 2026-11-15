import { useEffect, useState } from 'react'
import { api } from './api'
import Setup from './components/Setup.jsx'
import Progress from './components/Progress.jsx'
import Workspace from './components/Workspace.jsx'
import Demo from './components/Demo.jsx'

const readHash = () => (location.hash.match(/^#\/ws\/([\w-]+)/) || [])[1] || null
export default function App() {
  const [id, setId] = useState(readHash())
  const [demo, setDemo] = useState(location.hash === '#/preview')
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const on = () => { setStatus(null); setId(readHash()); setDemo(location.hash === '#/preview') }
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])
  useEffect(() => {
    if (!id) return
    let stop = false, timer
    const tick = async () => {
      try {
        const s = await api.status(id)
        if (stop) return
        setStatus(s); setError('')
        if (!['done', 'error'].includes(s.status)) timer = setTimeout(tick, 2500)
      } catch (e) { if (!stop) { setError(e.message); timer = setTimeout(tick, 5000) } }
    }
    tick()
    return () => { stop = true; clearTimeout(timer) }
  }, [id])
  const open = wsId => { location.hash = `#/ws/${wsId}` }
  const home = () => { location.hash = ''; setDemo(false); setId(null) }
  if (demo) return <Demo onHome={home}/>
  if (!id) return <Setup onCreated={open} onOpen={open} onDemo={() => { location.hash = '#/preview' }} />
  if (error && !status) return <div className="page narrow"><p className="error">{error}</p><button onClick={home}>Back</button></div>
  if (!status) return <div className="page narrow"><p className="muted">Loading workspace…</p></div>
  if (status.status === 'error') return <div className="page narrow"><h2>Investigation stopped</h2><p className="error">{status.error}</p><button onClick={home}>Start over</button></div>
  if (status.status !== 'done' && status.status !== 'evaluating') return <Progress status={status} onHome={home} />
  return <Workspace id={id} status={status} onHome={home} />
}
