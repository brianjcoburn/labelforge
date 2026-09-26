import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ModelMetrics, ModelVersion, TrainingRun } from '../types/api'

function MetricsView({ metrics }: { metrics: ModelMetrics }) {
  const perClass = metrics.per_class ?? metrics.per_label
  return (
    <div>
      <p className="metadata">
        Trained on {metrics.n_train} examples, evaluated on {metrics.n_held_out} held out.
      </p>
      <dl className="stat-grid">
        {metrics.accuracy !== undefined && (
          <div>
            <dt>Accuracy</dt>
            <dd>{(metrics.accuracy * 100).toFixed(1)}%</dd>
          </div>
        )}
        {metrics.macro_f1 !== undefined && (
          <div>
            <dt>Macro F1</dt>
            <dd>{metrics.macro_f1.toFixed(3)}</dd>
          </div>
        )}
        {metrics.micro_f1 !== undefined && (
          <div>
            <dt>Micro F1</dt>
            <dd>{metrics.micro_f1.toFixed(3)}</dd>
          </div>
        )}
        {metrics.precision !== undefined && (
          <div>
            <dt>Precision</dt>
            <dd>{metrics.precision.toFixed(3)}</dd>
          </div>
        )}
        {metrics.recall !== undefined && (
          <div>
            <dt>Recall</dt>
            <dd>{metrics.recall.toFixed(3)}</dd>
          </div>
        )}
        {metrics.roc_auc !== undefined && (
          <div>
            <dt>ROC-AUC</dt>
            <dd>{metrics.roc_auc.toFixed(3)}</dd>
          </div>
        )}
        {metrics.hamming_loss !== undefined && (
          <div>
            <dt>Hamming loss</dt>
            <dd>{metrics.hamming_loss.toFixed(3)}</dd>
          </div>
        )}
      </dl>

      {perClass && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Label</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>F1</th>
                <th>Support</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(perClass).map(([name, m]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{m.precision.toFixed(2)}</td>
                  <td>{m.recall.toFixed(2)}</td>
                  <td>{m.f1.toFixed(2)}</td>
                  <td>{m.support}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {metrics.confusion_matrix && (
        <div style={{ overflowX: 'auto' }}>
          <p className="metadata">Confusion matrix (rows = actual, columns = predicted)</p>
          <table>
            <thead>
              <tr>
                <th></th>
                {metrics.confusion_matrix.labels.map((l) => (
                  <th key={l}>{l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.confusion_matrix.matrix.map((row, i) => (
                <tr key={metrics.confusion_matrix!.labels[i]}>
                  <th>{metrics.confusion_matrix!.labels[i]}</th>
                  {row.map((cell, j) => (
                    <td key={j}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function ModelsPage() {
  const { projectId } = useParams()
  const [models, setModels] = useState<ModelVersion[]>([])
  const [runs, setRuns] = useState<TrainingRun[]>([])
  const [training, setTraining] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    api.get<ModelVersion[]>(`/projects/${projectId}/models`).then(setModels).catch(() => {})
    api
      .get<TrainingRun[]>(`/projects/${projectId}/training-runs`)
      .then(setRuns)
      .catch(() => {})
  }

  useEffect(load, [projectId])

  async function trainNow() {
    setTraining(true)
    setError(null)
    try {
      await api.post(`/projects/${projectId}/models/train`)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Training failed')
    } finally {
      setTraining(false)
    }
  }

  async function activate(modelId: number) {
    setError(null)
    try {
      await api.post(`/projects/${projectId}/models/${modelId}/activate`)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to activate')
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Models</h1>
        <Link to={`/projects/${projectId}`}>← Back to project</Link>
      </div>

      <p>
        Trains a baseline classifier (TF-IDF + logistic regression) on your human-confirmed
        annotations, evaluated on a held-out split. Needs at least 10 confirmed annotations
        with at least 2 different labels represented.
      </p>
      <button onClick={trainNow} disabled={training}>
        {training ? 'Training…' : 'Train Now'}
      </button>
      {error && <p className="error">{error}</p>}

      {runs.length > 0 && (
        <>
          <h2>Training runs</h2>
          <ul className="project-list">
            {runs.map((run) => (
              <li key={run.id}>
                {run.trigger_reason} — {run.annotation_count_snapshot} annotations
                <span className="tag">{run.status}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h2>Model versions</h2>
      {models.length === 0 && <p>No models trained yet.</p>}
      <div className="form">
        {models.map((model) => (
          <fieldset key={model.id}>
            <legend>
              v{model.version_number} {model.state === 'active' && <strong>(active)</strong>}
            </legend>
            {model.metrics_json && <MetricsView metrics={model.metrics_json} />}
            {model.state !== 'active' && (
              <button className="secondary" onClick={() => activate(model.id)}>
                Activate
              </button>
            )}
          </fieldset>
        ))}
      </div>
    </div>
  )
}
