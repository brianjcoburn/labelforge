import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import LabelPicker from '../components/LabelPicker'
import ProgressBar from '../components/ProgressBar'
import type {
  AnnotateNextResponse,
  AnnotationResult,
  ProjectDetail,
  RecordDetail,
  Suggestion,
  TaxonomyOut,
} from '../types/api'

interface Reveal {
  humanLabels: string[]
  suggestion: Suggestion
}

type RecordView = {
  id: number
  text: string
  metadata: Record<string, unknown>
  existingLabelRaw: string | null
  suggestion: Suggestion | null
  mode: 'annotate' | 'audit'
}

// null = still loading; 'done' = no unlabeled records remain (Previous still works)
type CurrentState = RecordView | 'done' | null

export default function AnnotationWorkspace() {
  const { projectId } = useParams()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [taxonomy, setTaxonomy] = useState<TaxonomyOut | null>(null)
  const [progress, setProgress] = useState<{ completed: number; total: number } | null>(null)
  const [current, setCurrent] = useState<CurrentState>(null)
  const [cursor, setCursor] = useState(-1)
  const [historyLength, setHistoryLength] = useState(0)
  const [selected, setSelected] = useState<number[]>([])
  const [note, setNote] = useState('')
  const [revealed, setRevealed] = useState(false)
  const [postSubmitReveal, setPostSubmitReveal] = useState<Reveal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Record ids visited this session, oldest first. A ref (not state) because
  // it needs to be read/written synchronously between the two async loaders
  // below — it never drives rendering directly, only `cursor`/`historyLength` do.
  const history = useRef<number[]>([])

  async function loadFreshNext(reveal = false) {
    setBusy(true)
    setError(null)
    setPostSubmitReveal(null)
    try {
      const res = await api.get<AnnotateNextResponse>(
        `/projects/${projectId}/annotate/next${reveal ? '?reveal_suggestion=true' : ''}`
      )
      setProgress(res.progress)
      if (!res.record) {
        setCurrent('done')
        return
      }
      const rec = res.record
      if (history.current[history.current.length - 1] !== rec.id) {
        history.current = [...history.current, rec.id]
      }
      setCursor(history.current.length - 1)
      setHistoryLength(history.current.length)
      setCurrent({
        id: rec.id,
        text: rec.text,
        metadata: rec.metadata,
        existingLabelRaw: rec.existing_label_raw,
        suggestion: res.suggestion,
        mode: res.mode,
      })
      // An audit's suggestion is pre-selected — accepting it is just
      // submitting as-is; editing before submit is how you "correct" it.
      setSelected(res.mode === 'audit' ? res.suggestion?.label_ids ?? [] : [])
      setNote('')
      setRevealed(reveal)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load next record')
    } finally {
      setBusy(false)
    }
  }

  async function loadHistoryRecord(index: number) {
    const recordId = history.current[index]
    if (recordId === undefined) return
    setBusy(true)
    setError(null)
    setPostSubmitReveal(null)
    try {
      const detail = await api.get<RecordDetail>(`/projects/${projectId}/records/${recordId}`)
      if (!detail.record) return
      setCursor(index)
      setCurrent({
        id: detail.record.id,
        text: detail.record.text,
        metadata: detail.record.metadata,
        existingLabelRaw: detail.record.existing_label_raw,
        suggestion: detail.suggestion,
        mode: 'annotate',
      })
      setSelected(detail.annotation?.current_label_ids ?? [])
      setNote('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load record')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    api.get<ProjectDetail>(`/projects/${projectId}`).then(setProject).catch(() => {})
    api.get<TaxonomyOut>(`/projects/${projectId}/taxonomy`).then(setTaxonomy).catch(() => {})
    loadFreshNext()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const isReviewingPast = cursor >= 0 && cursor < historyLength - 1

  async function act(outcome: 'submitted' | 'skipped' | 'flagged') {
    if (current === null || current === 'done') return
    setBusy(true)
    setError(null)
    try {
      const result = await api.post<AnnotationResult>(
        `/projects/${projectId}/records/${current.id}/annotations`,
        {
          outcome,
          label_ids: outcome === 'skipped' ? [] : selected,
          note: note || null,
          saw_suggestion_before_submit:
            !isReviewingPast && project?.settings.annotation_mode === 'on_demand'
              ? revealed
              : undefined,
        }
      )
      if (isReviewingPast) {
        // Editing a past record: just move forward through what you've
        // already visited — don't re-trigger first-exposure mode timing.
        await loadHistoryRecord(cursor + 1)
      } else if (result.revealed_suggestion) {
        setPostSubmitReveal({
          humanLabels: result.current_labels,
          suggestion: result.revealed_suggestion,
        })
      } else {
        await loadFreshNext()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save annotation')
    } finally {
      setBusy(false)
    }
  }

  function continueAfterReveal() {
    setPostSubmitReveal(null)
    loadFreshNext()
  }

  if (error) return <p className="error">{error}</p>
  if (!project || !taxonomy || current === null) return <p>Loading…</p>

  return (
    <div>
      <div className="page-header">
        <h1>{project.name}</h1>
        <Link to={`/projects/${projectId}`}>← Back to project</Link>
      </div>
      {progress && <ProgressBar completed={progress.completed} total={progress.total} />}

      <div className="actions" style={{ marginBottom: '1rem' }}>
        <button
          className="secondary"
          onClick={() => loadHistoryRecord(cursor - 1)}
          disabled={busy || cursor <= 0}
        >
          ← Previous
        </button>
        <button
          className="secondary"
          onClick={() => loadHistoryRecord(cursor + 1)}
          disabled={busy || !isReviewingPast}
        >
          Next →
        </button>
      </div>

      {postSubmitReveal ? (
        <div className="annotation-card">
          <p>You said: <strong>{postSubmitReveal.humanLabels.join(', ') || '(none)'}</strong></p>
          <div className="suggestion-panel">
            <strong>AI predicted:</strong>{' '}
            {postSubmitReveal.suggestion.label_names.join(', ') || '(none)'}
          </div>
          <button onClick={continueAfterReveal}>Continue</button>
        </div>
      ) : current === 'done' ? (
        <p>All records have been reviewed. 🎉 (You can still use Previous to review past ones.)</p>
      ) : (
        <div className="annotation-card">
          {isReviewingPast && (
            <p className="tag">Reviewing a previous record — saving here updates it.</p>
          )}
          {current.mode === 'audit' && (
            <p className="tag">
              Audit — this was auto-labeled. Accept it as-is, or change the label(s) below and submit to correct it.
            </p>
          )}
          <p className="record-text">{current.text}</p>

          {Object.keys(current.metadata).length > 0 && (
            <p className="metadata">
              {Object.entries(current.metadata)
                .map(([k, v]) => `${k}: ${v}`)
                .join(' · ')}
            </p>
          )}

          {current.suggestion && (
            <div className="suggestion-panel">
              <strong>
                {current.mode === 'audit'
                  ? 'Auto-labeled as'
                  : current.suggestion.source === 'imported'
                    ? 'Imported suggestion'
                    : 'AI suggestion'}
                :
              </strong>{' '}
              {current.suggestion.label_names.join(', ') || '(none)'}
            </div>
          )}

          {!current.suggestion &&
            !isReviewingPast &&
            project.settings.annotation_mode === 'on_demand' &&
            !revealed && (
              <button className="secondary" onClick={() => loadFreshNext(true)}>
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
              {current.mode === 'audit' ? 'Accept / Correct' : 'Submit'}
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
