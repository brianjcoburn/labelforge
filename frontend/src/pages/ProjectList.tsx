import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Project } from '../types/api'

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<Project[]>('/projects')
      .then(setProjects)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1>Projects</h1>
        <Link className="button" to="/projects/new">
          New Project
        </Link>
      </div>
      {error && <p className="error">{error}</p>}
      {projects === null && !error && <p>Loading…</p>}
      {projects?.length === 0 && <p>No projects yet. Create one to get started.</p>}
      <ul className="project-list">
        {projects?.map((p) => (
          <li key={p.id}>
            <Link to={`/projects/${p.id}`}>{p.name}</Link>
            <span className="tag">{p.classification_type}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
