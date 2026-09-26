import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Label, TaxonomyOut } from '../types/api'

interface DraftLabel {
  name: string
  description: string
  include_criteria: string
  exclude_criteria: string
  examples: string // one per line in the textarea
}

const emptyLabel = (): DraftLabel => ({
  name: '',
  description: '',
  include_criteria: '',
  exclude_criteria: '',
  examples: '',
})

// Loosely typed on purpose: this is data from an arbitrary uploaded file, not
// necessarily one LabelForge exported, so field naming may vary.
type ImportedLabel = Record<string, unknown>
type ImportedTaxonomy = Record<string, unknown>

// Accepts a few common spellings for each field, in priority order, so a
// hand-written or differently-shaped JSON file isn't silently dropped just
// because it says "include" instead of "include_criteria".
function firstString(raw: ImportedLabel, keys: string[]): string {
  for (const key of keys) {
    const value = raw[key]
    if (typeof value === 'string') return value
  }
  return ''
}

// Several real-world taxonomy files use a LIST of bullet points for
// include/exclude/examples (multiple criteria per label), not one sentence —
// this is the form the reported bug actually had. Joins list items with
// newlines to match the single multi-line textarea these fields edit as.
function firstTextOrList(raw: ImportedLabel, keys: string[]): string {
  for (const key of keys) {
    const value = raw[key]
    if (Array.isArray(value)) return value.filter((v) => typeof v === 'string').join('\n')
    if (typeof value === 'string') return value
  }
  return ''
}

function asDraftLabel(raw: ImportedLabel): DraftLabel {
  return {
    name: firstString(raw, ['name', 'label', 'label_name']),
    description: firstTextOrList(raw, ['description', 'definition']),
    include_criteria: firstTextOrList(raw, [
      'include_criteria',
      'include_criterion',
      'include',
      'includes',
      'inclusion_criteria',
    ]),
    exclude_criteria: firstTextOrList(raw, [
      'exclude_criteria',
      'exclude_criterion',
      'exclude',
      'excludes',
      'exclusion_criteria',
    ]),
    examples: firstTextOrList(raw, ['examples', 'example']),
  }
}

function findLabelsArray(parsed: ImportedTaxonomy): ImportedLabel[] | null {
  for (const key of ['labels', 'label_list', 'classes', 'categories']) {
    const value = parsed[key]
    if (Array.isArray(value) && value.length > 0) return value as ImportedLabel[]
  }
  return null
}

interface LabelEditCardProps {
  projectId: string | undefined
  label: Label
  onSaved: (updated: Label) => void
}

function LabelEditCard({ projectId, label, onSaved }: LabelEditCardProps) {
  const [draft, setDraft] = useState<DraftLabel>({
    name: label.name,
    description: label.description ?? '',
    include_criteria: label.include_criteria ?? '',
    exclude_criteria: label.exclude_criteria ?? '',
    examples: label.examples.join('\n'),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  function update(field: keyof DraftLabel, value: string) {
    setDraft((prev) => ({ ...prev, [field]: value }))
    setSaved(false)
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const updated = await api.patch<Label>(
        `/projects/${projectId}/taxonomy/labels/${label.id}`,
        {
          name: draft.name,
          description: draft.description || null,
          include_criteria: draft.include_criteria || null,
          exclude_criteria: draft.exclude_criteria || null,
          examples: draft.examples
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean),
        }
      )
      onSaved(updated)
      setSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <fieldset>
      <legend>{label.name}</legend>
      <label>
        Name
        <input value={draft.name} onChange={(e) => update('name', e.target.value)} />
      </label>
      <label>
        Definition
        <textarea
          value={draft.description}
          onChange={(e) => update('description', e.target.value)}
        />
      </label>
      <label>
        Include
        <textarea
          value={draft.include_criteria}
          onChange={(e) => update('include_criteria', e.target.value)}
        />
      </label>
      <label>
        Exclude
        <textarea
          value={draft.exclude_criteria}
          onChange={(e) => update('exclude_criteria', e.target.value)}
        />
      </label>
      <label>
        Examples (one per line)
        <textarea
          value={draft.examples}
          onChange={(e) => update('examples', e.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="secondary" onClick={save} disabled={saving || !draft.name.trim()}>
        {saved ? '✓ Saved' : 'Save'}
      </button>
    </fieldset>
  )
}

export default function TaxonomyEditor() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [taxonomy, setTaxonomy] = useState<TaxonomyOut | null | 'none'>(null)
  const [name, setName] = useState('')
  const [labels, setLabels] = useState<DraftLabel[]>([emptyLabel(), emptyLabel()])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api
      .get<TaxonomyOut>(`/projects/${projectId}/taxonomy`)
      .then(setTaxonomy)
      .catch(() => setTaxonomy('none'))
  }, [projectId])

  function updateLabel(index: number, field: keyof DraftLabel, value: string) {
    setLabels((prev) =>
      prev.map((l, i) => (i === index ? { ...l, [field]: value } : l))
    )
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-selecting the same file later
    if (!file) return
    setError(null)
    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as ImportedTaxonomy
      const labelsArray = findLabelsArray(parsed)
      if (!labelsArray) {
        throw new Error(
          'No labels array found — expected a "labels" key with a non-empty array of ' +
            '{ name, description/definition, include, exclude, examples }'
        )
      }
      setName(firstString(parsed, ['name', 'taxonomy_name']) || name)
      setLabels(labelsArray.map(asDraftLabel))
    } catch (err) {
      setError(
        err instanceof Error
          ? `Couldn't read that file: ${err.message}`
          : "Couldn't read that file"
      )
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.post(`/projects/${projectId}/taxonomy`, {
        name,
        labels: labels
          .filter((l) => l.name.trim())
          .map((l) => ({
            name: l.name,
            description: l.description || null,
            include_criteria: l.include_criteria || null,
            exclude_criteria: l.exclude_criteria || null,
            examples: l.examples
              .split('\n')
              .map((line) => line.trim())
              .filter(Boolean),
          })),
      })
      navigate(`/projects/${projectId}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create taxonomy')
      setSubmitting(false)
    }
  }

  if (taxonomy === null) return <p>Loading…</p>

  if (taxonomy !== 'none') {
    return (
      <div>
        <div className="page-header">
          <h1>Taxonomy</h1>
          <Link to={`/projects/${projectId}`}>← Back to project</Link>
        </div>
        <p>
          {taxonomy.name} — version {taxonomy.active_version_number}
        </p>
        <p className="metadata">
          Editing a label's name, definition, include/exclude, or examples here is safe —
          it never invalidates existing annotations. Adding or removing labels isn't
          supported yet (that needs a taxonomy-versioning workflow that revalidates
          affected annotations, which isn't built).
        </p>
        <div className="form">
          {taxonomy.labels.map((label) => (
            <LabelEditCard
              key={label.id}
              projectId={projectId}
              label={label}
              onSaved={(updated) =>
                setTaxonomy((prev) =>
                  prev && prev !== 'none'
                    ? {
                        ...prev,
                        labels: prev.labels.map((l) => (l.id === updated.id ? updated : l)),
                      }
                    : prev
                )
              }
            />
          ))}
        </div>
        <p>
          <a href={`/api/projects/${projectId}/export/taxonomy.json`}>Export as JSON</a>
        </p>
      </div>
    )
  }

  return (
    <div>
      <h1>Create Taxonomy</h1>

      <label>
        Import from JSON (optional — from a previous LabelForge export, or your own file with
        a <code>labels</code> array of objects; accepts <code>include</code>/
        <code>include_criteria</code>, <code>exclude</code>/<code>exclude_criteria</code>,
        <code>description</code>/<code>definition</code>, and <code>examples</code> as either
        an array or a single string)
        <input type="file" accept=".json,application/json" onChange={handleImportFile} />
      </label>

      <form onSubmit={handleSubmit} className="form">
        <label>
          Taxonomy name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        {labels.map((label, i) => (
          <fieldset key={i}>
            <legend>Label {i + 1}</legend>
            <label>
              Name
              <input
                value={label.name}
                onChange={(e) => updateLabel(i, 'name', e.target.value)}
              />
            </label>
            <label>
              Definition
              <textarea
                value={label.description}
                onChange={(e) => updateLabel(i, 'description', e.target.value)}
              />
            </label>
            <label>
              Include
              <textarea
                value={label.include_criteria}
                onChange={(e) => updateLabel(i, 'include_criteria', e.target.value)}
              />
            </label>
            <label>
              Exclude
              <textarea
                value={label.exclude_criteria}
                onChange={(e) => updateLabel(i, 'exclude_criteria', e.target.value)}
              />
            </label>
            <label>
              Examples (one per line)
              <textarea
                value={label.examples}
                onChange={(e) => updateLabel(i, 'examples', e.target.value)}
              />
            </label>
          </fieldset>
        ))}
        <button
          type="button"
          className="secondary"
          onClick={() => setLabels((prev) => [...prev, emptyLabel()])}
        >
          + Add label
        </button>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting || !name}>
          Save Taxonomy
        </button>
      </form>
    </div>
  )
}
