import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import ColumnMapper, { type ColumnMapping } from '../components/ColumnMapper'

interface UploadResult {
  dataset_id: number
  columns: string[]
  preview_rows: Record<string, string>[]
}

interface ImportResult {
  record_count: number
  matched_label_count: number
  unmatched_label_count: number
}

export default function DatasetImport() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [upload, setUpload] = useState<UploadResult | null>(null)
  const [mapping, setMapping] = useState<ColumnMapping>({
    idColumn: '',
    textColumn: '',
    labelColumn: '',
    metadataColumns: [],
  })
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await api.postForm<UploadResult>(
        `/projects/${projectId}/datasets/upload`,
        form
      )
      setUpload(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleImport() {
    if (!upload) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.post<ImportResult>(
        `/projects/${projectId}/datasets/${upload.dataset_id}/import`,
        {
          name: `Dataset ${upload.dataset_id}`,
          id_column: mapping.idColumn || null,
          text_column: mapping.textColumn,
          label_column: mapping.labelColumn || null,
          metadata_columns: mapping.metadataColumns,
        }
      )
      setResult(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <div>
        <h1>Import complete</h1>
        <p>{result.record_count} records imported.</p>
        {result.matched_label_count > 0 && (
          <p>
            {result.matched_label_count} existing labels matched the taxonomy and are
            shown as Imported suggestions.
          </p>
        )}
        {result.unmatched_label_count > 0 && (
          <p>
            {result.unmatched_label_count} existing label values didn't match any
            taxonomy label — kept as reference metadata only.
          </p>
        )}
        <Link className="button" to={`/projects/${projectId}/annotate`}>
          Start Annotating
        </Link>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Import Data</h1>
        <Link to={`/projects/${projectId}`}>← Back to project</Link>
      </div>

      {!upload && (
        <label>
          Choose a CSV file
          <input type="file" accept=".csv" onChange={handleUpload} disabled={busy} />
        </label>
      )}

      {upload && (
        <>
          <p>{upload.columns.length} columns detected. Map them below:</p>
          <ColumnMapper columns={upload.columns} value={mapping} onChange={setMapping} />
          <button onClick={handleImport} disabled={busy || !mapping.textColumn}>
            Import Records
          </button>
        </>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}
