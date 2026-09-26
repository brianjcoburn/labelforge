import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AnnotationMode, LLMProviderChoice, LocalModelCatalogEntry, ProjectDetail } from '../types/api'

interface Props {
  project: ProjectDetail
  onSaved: () => void
}

const MODE_DESCRIPTIONS: Record<AnnotationMode, string> = {
  on_demand: "No suggestion shown unless you click \"Show Suggestion\" while labeling.",
  ai_first: 'The AI suggestion is shown before you label — you accept, change, or reject it.',
  human_first:
    'You label blind first; the AI suggestion is revealed right after you submit — good for measuring independent agreement.',
}

export default function ModelSettings({ project, onSaved }: Props) {
  const [provider, setProvider] = useState<LLMProviderChoice>(project.settings.llm_provider)
  const [modelId, setModelId] = useState<string | null>(project.settings.local_model_id)
  const [mode, setMode] = useState<AnnotationMode>(project.settings.annotation_mode)
  const [catalog, setCatalog] = useState<LocalModelCatalogEntry[]>([])
  const [downloading, setDownloading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function loadCatalog() {
    api.get<LocalModelCatalogEntry[]>('/models/local/catalog').then(setCatalog).catch(() => {})
  }

  useEffect(loadCatalog, [])

  async function download(catalogId: string) {
    setDownloading(catalogId)
    setError(null)
    try {
      await api.post(`/models/local/${catalogId}/download`)
      loadCatalog()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setDownloading(null)
    }
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await api.patch(`/projects/${project.id}/settings`, {
        llm_provider: provider,
        local_model_id: modelId,
        annotation_mode: mode,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="form">
      <fieldset>
        <legend>AI model</legend>
        <label className="radio">
          <input
            type="radio"
            checked={provider === 'local'}
            onChange={() => setProvider('local')}
          />
          Free, local, open-source model
        </label>
        <label className="radio">
          <input
            type="radio"
            checked={provider === 'anthropic'}
            onChange={() => setProvider('anthropic')}
          />
          Anthropic API (requires ANTHROPIC_API_KEY in the server's .env)
        </label>
      </fieldset>

      {provider === 'local' && (
        <ul className="project-list">
          {catalog.map((entry) => (
            <li key={entry.id} style={{ display: 'block' }}>
              <label className="radio">
                <input
                  type="radio"
                  name="local-model"
                  checked={modelId === entry.id}
                  disabled={!entry.downloaded}
                  onChange={() => setModelId(entry.id)}
                />
                <strong>{entry.display_name}</strong> ({entry.brand}) — {entry.size_gb} GB
              </label>
              <p className="metadata">{entry.notes}</p>
              {entry.downloaded ? (
                <span className="tag">✓ Downloaded</span>
              ) : (
                <button
                  className="secondary"
                  disabled={downloading !== null}
                  onClick={() => download(entry.id)}
                >
                  {downloading === entry.id
                    ? 'Downloading… this can take several minutes'
                    : 'Download'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <fieldset>
        <legend>When to show AI suggestions</legend>
        {(Object.keys(MODE_DESCRIPTIONS) as AnnotationMode[]).map((m) => (
          <label key={m} className="radio" style={{ alignItems: 'flex-start' }}>
            <input type="radio" checked={mode === m} onChange={() => setMode(m)} />
            <span>
              <strong>{m.replace('_', '-')}</strong> — {MODE_DESCRIPTIONS[m]}
            </span>
          </label>
        ))}
      </fieldset>

      {error && <p className="error">{error}</p>}
      <button onClick={save} disabled={saving || (provider === 'local' && !modelId)}>
        Save Model Settings
      </button>
    </div>
  )
}
