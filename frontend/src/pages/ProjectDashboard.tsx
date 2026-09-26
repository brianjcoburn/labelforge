import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Progress, ProjectDetail } from '../types/api'

export default function ProjectDashboard() {
  const { projectId } = useParams()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<ProjectDetail>(`/projects/${projectId}`)
      .then(setProject)
      .catch((e) => setError(e.message))
    api
      .get<Progress>(`/projects/${projectId}/progress`)
      .then(setProgress)
      .catch(() => {})
  }, [projectId])

  if (error) return <p className="error">{error}</p>
  if (!project) return <p>Loading…</p>

  return (
    <div>
      <div className="page-header">
        <h1>{project.name}</h1>
        <Link to="/">← All projects</Link>
      </div>
      {project.description && <p>{project.description}</p>}
      <dl className="stat-grid">
        <div>
          <dt>Classification</dt>
          <dd>{project.classification_type}</dd>
        </div>
        <div>
          <dt>Dataset</dt>
          <dd>{project.record_count} records</dd>
        </div>
        <div>
          <dt>Annotations</dt>
          <dd>
            {project.annotated_count} / {project.record_count}
          </dd>
        </div>
        <div>
          <dt>Annotation mode</dt>
          <dd>{project.settings.annotation_mode}</dd>
        </div>
        <div>
          <dt>Sampling</dt>
          <dd>{project.settings.sampling_strategy}</dd>
        </div>
        {progress && (
          <>
            <div>
              <dt>Skipped</dt>
              <dd>{progress.skipped}</dd>
            </div>
            <div>
              <dt>Flagged (needs review)</dt>
              <dd>{progress.flagged}</dd>
            </div>
            <div>
              <dt>Remaining</dt>
              <dd>{progress.remaining}</dd>
            </div>
          </>
        )}
      </dl>

      {progress && Object.keys(progress.label_distribution).length > 0 && (
        <>
          <h2>Label distribution</h2>
          <ul className="project-list">
            {Object.entries(progress.label_distribution).map(([label, count]) => (
              <li key={label}>
                {label}
                <span className="tag">{count}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <nav className="actions">
        <Link className="button" to={`/projects/${project.id}/taxonomy`}>
          {project.has_taxonomy ? 'View Taxonomy' : 'Create Taxonomy'}
        </Link>
        {project.has_taxonomy && (
          <>
            <Link className="button" to={`/projects/${project.id}/import`}>
              Import Data
            </Link>
            {project.record_count > 0 && (
              <Link className="button" to={`/projects/${project.id}/annotate`}>
                Continue Labeling
              </Link>
            )}
          </>
        )}
      </nav>

      {project.record_count > 0 && (
        <>
          <h2>Export</h2>
          <nav className="actions">
            <a className="button secondary" href={`/api/projects/${project.id}/export/annotations.csv`}>
              Annotations CSV
            </a>
            <a className="button secondary" href={`/api/projects/${project.id}/export/taxonomy.json`}>
              Taxonomy JSON
            </a>
            <a className="button secondary" href={`/api/projects/${project.id}/export/config.json`}>
              Config JSON
            </a>
          </nav>
        </>
      )}
    </div>
  )
}
