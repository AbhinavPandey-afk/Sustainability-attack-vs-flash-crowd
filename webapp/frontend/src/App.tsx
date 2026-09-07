import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { NavShell } from './components/NavShell'
import { StatusBar } from './components/StatusBar'
import { DEFAULT_PAGE, isPageId } from './nav'
import type { PageId } from './nav'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { AttackSimulatorPage } from './pages/AttackSimulatorPage'
import { DashboardPage } from './pages/DashboardPage'
import { DatasetExportPage } from './pages/DatasetExportPage'
import { ExperimentsPage } from './pages/ExperimentsPage'
import { FlashCrowdSimulatorPage } from './pages/FlashCrowdSimulatorPage'
import { LiveMonitorPage } from './pages/LiveMonitorPage'
import type { ExperimentExample, HistoryEntry, ResearchQuestion, RunStatus, SystemStatus } from './types'

function currentPageFromHash(): PageId {
  const hash = window.location.hash.replace('#', '')
  return isPageId(hash) ? hash : DEFAULT_PAGE
}

function App() {
  const [page, setPage] = useState<PageId>(currentPageFromHash())
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [research, setResearch] = useState<ResearchQuestion | null>(null)
  const [examples, setExamples] = useState<ExperimentExample[]>([])
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [demoStatus, setDemoStatus] = useState<RunStatus | null>(null)

  const demoRunning = demoStatus?.state === 'STARTING' || demoStatus?.state === 'RUNNING' || demoStatus?.state === 'SUMMARIZING'

  const navigate = useCallback((id: PageId) => {
    window.location.hash = id
    setPage(id)
  }, [])

  useEffect(() => {
    const onHashChange = () => setPage(currentPageFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const refreshExperiments = useCallback(() => {
    api.examples().then((ex) => {
      setExamples(ex)
      setSelectedId((prev) => prev ?? ex[0]?.experiment_id ?? null)
    })
    api.history().then(setHistory)
  }, [])

  useEffect(() => {
    api.researchQuestion().then(setResearch).catch(() => setResearch(null))
    refreshExperiments()
  }, [refreshExperiments])

  useEffect(() => {
    const poll = () => api.systemStatus().then(setStatus).catch(() => setStatus(null))
    poll()
    const id = window.setInterval(poll, 5000)
    return () => window.clearInterval(id)
  }, [])

  const handleRunStart = (id: string) => setRunningId(id)
  const handleRunFinished = useCallback(() => {
    setRunningId(null)
    refreshExperiments()
  }, [refreshExperiments])

  const handleRunDemo = useCallback(async () => {
    try {
      await api.startDemo()
      setDemoStatus({ experiment_id: '', state: 'STARTING' })
    } catch (err) {
      alert(`Could not start demo: ${(err as Error).message}`)
    }
  }, [])

  useEffect(() => {
    if (!demoRunning) return
    const poll = async () => {
      try {
        const s = await api.demoStatus()
        setDemoStatus(s)
        if (s.state === 'COMPLETED' || s.state === 'FAILED' || s.state === 'CANCELLED') {
          refreshExperiments()
        }
      } catch {
        // transient — next tick retries
      }
    }
    poll()
    const id = window.setInterval(poll, 2000)
    return () => window.clearInterval(id)
  }, [demoRunning, refreshExperiments])

  return (
    <div className="app-shell">
      <header className="header">
        <div className="header-top">
          <div className="brand">
            <h1>CASCADE</h1>
            <span className="sub">Cost-Aware Scaling and Application-behaviour Detection Engine</span>
          </div>
        </div>
        <StatusBar status={status} />
      </header>

      <NavShell active={page} onSelect={navigate} />

      {page === 'dashboard' && (
        <DashboardPage
          status={status}
          research={research}
          history={history}
          onRunDemo={handleRunDemo}
          demoRunning={demoRunning}
        />
      )}
      {page === 'live' && (
        <LiveMonitorPage runningId={runningId} history={history} onRunStart={handleRunStart} onRunFinished={handleRunFinished} />
      )}
      {page === 'attack-sim' && <AttackSimulatorPage status={status} />}
      {page === 'flashcrowd-sim' && <FlashCrowdSimulatorPage status={status} />}
      {page === 'experiments' && (
        <ExperimentsPage
          examples={examples}
          selectedId={selectedId}
          onSelect={setSelectedId}
          runningId={runningId}
          onRunStart={handleRunStart}
          onRunFinished={handleRunFinished}
        />
      )}
      {page === 'architecture' && <ArchitecturePage />}
      {page === 'dataset' && <DatasetExportPage history={history} />}

      <div className="footer-note">
        CASCADE research prototype — the cost model uses experimental cost units, independent of any specific cloud
        provider. All figures on this page are read from real artifacts on disk or live system checks; nothing is
        fabricated.
      </div>
    </div>
  )
}

export default App
