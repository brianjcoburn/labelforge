import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import LabelPicker from '../components/LabelPicker'
import ProgressBar from '../components/ProgressBar'
import type { AnnotateNextResponse, AnnotationResult, ProjectDetail, Suggestion, TaxonomyOut } from '../types/api'

interface Reveal {
  humanLabels: string[]
  suggestion: Suggestion
}

export default function AnnotationWorkspace() {
  const { projectId } = useParams()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [taxonomy, setTaxonomy] = useState<TaxonomyOut | null>(null)
  const [next, setNext] = useState<AnnotateNextResponse | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const [note, setNote] = useState('')
  const [revealed, setRevealed] = useState(false)
  const [postSubmitReveal, setPostSubmitReveal] = useState<Reveal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const loadNext = useCallback(
    (reveal = false) => {
      api
        .get<AnnotateNextResponse>(
          `/projects/${projectId}/annotate/next${reveal ? '?reveal_suggestion=true' : ''}`
        )
        .then((res) => {
          setNext(res)
          setSelected([])
          setNote('')
          setRevealed(reveal)
        })
        .catch((e) => setError(e.message))
    },
    [projectId]
  )

  useEffect(() => {
    api.get<ProjectDetail>(`/projects/${projectId}`).then(setProject).catch(() => {})
    api.get<TaxonomyOut>(`/projects/${projectId}/taxonomy`).then(setTaxonomy).catch(() => {})
    loadNext()
  }, [projectId, loadNext])

  async function act(outcome: 'submitted' | 'skipped' | 'flagged') {
    if (!next?.record) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.post<AnnotationResult>(
        `/projects/${projectId}/records/${next.record.id}/annotations`,
        {
          outcome,
          label_ids: outcome === 'skipped' ? [] : selected,
          note: note || null,
          saw_suggestion_before_submit:
            project?.settings.annotation_mode === 'on_demand' ? revealed : undefined,
        }
      )
      if (result.revealed_suggestion) {
        setPostSubmitReveal({
          humanLabels: result.current_labels,
          suggestion: result.revealed_suggestion,
        })
      } else {
        loadNext()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save annotation')
    } finally {
      setBusy(false)
    }
  }

  function continueAfterReveal() {
    setPostSubmitReveal(null)
    loadNext()
  }

  if (error) return <p className="error">{error}</p>
  if (!project || !taxonomy || !next) return <p>Loading…</p>

  return (
    <div>
      <div className="page-header">
        <h1>{project.name}</h1>
        <Link to={`/projects/${projectId}`}>← Back to project</Link>
      </div>
      <ProgressBar completed={next.progress.completed} total={next.progress.total} />

      {postSubmitReveal ? (
        <div className="annotation-card">
          <p>You said: <strong>{postSubmitReveal.humanLabels.join(', ') || '(none)'}</strong></p>
          <div className="suggestion-panel">
            <strong>AI predicted:</strong>{' '}
            {postSubmitReveal.suggestion.label_names.join(', ') || '(none)'}
          </div>
          <button onClick={continueAfterReveal}>Continue</button>
        </div>
      ) : !next.record ? (
        <p>All records have been reviewed. 🎉</p>
      ) : (
        <div className="annotation-card">
          <p className="record-text">{next.record.text}</p>

          {Object.keys(next.record.metadata).length > 0 && (
            <p className="metadata">
              {Object.entries(next.record.metadata)
                .map(([k, v]) => `${k}: ${v}`)
                .join(' · ')}
            </p>
          )}

          {next.suggestion && (
            <div className="suggestion-panel">
              <strong>{next.suggestion.source === 'imported' ? 'Imported' : 'AI'} suggestion:</strong>{' '}
              {next.suggestion.label_names.join(', ') || '(none)'}
            </div>
          )}

          {!next.suggestion &&
            project.settings.annotation_mode === 'on_demand' &&
            !revealed && (
              <button className="secondary" onClick={() => loadNext(true)}>
                Show Suggestion
              </button>
            )}

          <LabelPicker
            classificationType={project.classification_type}
            labels={taxonomy.labels}
            selected={selected}
            onChange={setSelected}
          />

          <label>
            Note (optional, used when flagging)
            <textarea value={note} onChange={(e) => setNote(e.target.value)} />
          </label>

          <div className="actions">
            <button onClick={() => act('submitted')} disabled={busy}>
              Submit
            </button>
            <button className="secondary" onClick={() => act('skipped')} disabled={busy}>
              Skip
            </button>
            <button className="secondary" onClick={() => act('flagged')} disabled={busy}>
              Flag
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
