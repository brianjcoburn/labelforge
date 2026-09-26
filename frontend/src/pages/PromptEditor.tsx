import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import ModelSettings from '../components/ModelSettings'
import type { AnnotateNextResponse, ProjectDetail, PromptTestResult, PromptVersion } from '../types/api'

export default function PromptEditor() {
  const { projectId } = useParams()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [versions, setVersions] = useState<PromptVersion[]>([])
  const [draft, setDraft] = useState('')
  const [sampleRecord, setSampleRecord] = useState<AnnotateNextResponse['record']>(null)
  const [testResult, setTestResult] = useState<PromptTestResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function loadProject() {
    api.get<ProjectDetail>(`/projects/${projectId}`).then(setProject).catch(() => {})
  }

  function loadVersions() {
    api
      .get<PromptVersion[]>(`/projects/${projectId}/prompts`)
      .then(setVersions)
      .catch((e) => setError(e.message))
  }

  useEffect(() => {
    loadProject()
    loadVersions()
    api
      .get<AnnotateNextResponse>(`/projects/${projectId}/annotate/next`)
      .then((res) => setSampleRecord(res.record))
      .catch(() => {})
  }, [projectId])

  async function generateDraft() {
    setBusy(true)
    setError(null)
    try {
      const res = await api.post<{ template_text: string }>(
        `/projects/${projectId}/prompts/generate`
      )
      setDraft(res.template_text)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate draft')
    } finally {
      setBusy(false)
    }
  }

  async function saveVersion() {
    if (!draft.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.post(`/projects/${projectId}/prompts`, { template_text: draft })
      loadVersions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save prompt')
    } finally {
      setBusy(false)
    }
  }

  async function activate(versionId: number) {
    setBusy(true)
    try {
      await api.post(`/projects/${projectId}/prompts/${versionId}/activate`)
      loadVersions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to activate')
    } finally {
      setBusy(false)
    }
  }

  async function testOnSample() {
    if (!sampleRecord || !draft.trim()) return
    setBusy(true)
    setError(null)
    setTestResult(null)
    try {
      const res = await api.post<PromptTestResult>(`/projects/${projectId}/prompts/test`, {
        record_id: sampleRecord.id,
        template_text: draft,
      })
      setTestResult(res)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to test prompt — is ANTHROPIC_API_KEY configured?'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Prompt</h1>
        <Link to={`/projects/${projectId}`}>← Back to project</Link>
      </div>

      {project && <ModelSettings project={project} onSaved={loadProject} />}

      <h2>Prompt Template</h2>
      <div className="form">
        <label>
          Template ({'{{text}}'} is replaced with the record text)
          <textarea
            rows={14}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Generate a draft from the taxonomy, or write your own…"
          />
        </label>
        <div className="actions">
          <button className="secondary" onClick={generateDraft} disabled={busy}>
            Generate Draft
          </button>
          <button onClick={saveVersion} disabled={busy || !draft.trim()}>
            Save as New Version
          </button>
        </div>

        {sampleRecord && (
          <div className="suggestion-panel">
            <p>
              <strong>Sample record:</strong> {sampleRecord.text}
            </p>
            <button className="secondary" onClick={testOnSample} disabled={busy || !draft.trim()}>
              Test on this record
            </button>
            {testResult && (
              <p>
                Predicted: <strong>{testResult.predicted_label_names.join(', ') || '(none)'}</strong>
              </p>
            )}
          </div>
        )}

        {error && <p className="error">{error}</p>}
      </div>

      <h2>Versions</h2>
      <ul className="project-list">
        {versions.map((v) => (
          <li key={v.id}>
            <span>
              v{v.version_number} {v.is_active && <strong>(active)</strong>}
            </span>
            {!v.is_active && (
              <button className="secondary" onClick={() => activate(v.id)} disabled={busy}>
                Activate
              </button>
            )}
          </li>
        ))}
        {versions.length === 0 && <li>No saved prompt versions yet.</li>}
      </ul>
    </div>
  )
}
