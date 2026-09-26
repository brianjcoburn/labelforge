import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ClassificationType, Project } from '../types/api'

export default function ProjectCreate() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [classificationType, setClassificationType] =
    useState<ClassificationType>('multiclass')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const project = await api.post<Project>('/projects', {
        name,
        description: description || null,
        classification_type: classificationType,
      })
      navigate(`/projects/${project.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project')
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h1>New Project</h1>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Description
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <fieldset>
          <legend>Classification type</legend>
          {(['binary', 'multiclass', 'multilabel'] as ClassificationType[]).map((t) => (
            <label key={t} className="radio">
              <input
                type="radio"
                name="classification_type"
                value={t}
                checked={classificationType === t}
                onChange={() => setClassificationType(t)}
              />
              {t}
            </label>
          ))}
        </fieldset>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting || !name}>
          Create Project
        </button>
      </form>
    </div>
  )
}
