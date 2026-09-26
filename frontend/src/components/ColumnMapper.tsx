export interface ColumnMapping {
  idColumn: string
  textColumn: string
  labelColumn: string
  metadataColumns: string[]
}

interface Props {
  columns: string[]
  value: ColumnMapping
  onChange: (mapping: ColumnMapping) => void
}

export default function ColumnMapper({ columns, value, onChange }: Props) {
  function toggleMetadata(column: string) {
    const next = value.metadataColumns.includes(column)
      ? value.metadataColumns.filter((c) => c !== column)
      : [...value.metadataColumns, column]
    onChange({ ...value, metadataColumns: next })
  }

  return (
    <div className="form">
      <label>
        Text column (required)
        <select
          value={value.textColumn}
          onChange={(e) => onChange({ ...value, textColumn: e.target.value })}
        >
          <option value="">— select —</option>
          {columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <label>
        ID column (optional)
        <select
          value={value.idColumn}
          onChange={(e) => onChange({ ...value, idColumn: e.target.value })}
        >
          <option value="">— none —</option>
          {columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <label>
        Existing label column (optional)
        <select
          value={value.labelColumn}
          onChange={(e) => onChange({ ...value, labelColumn: e.target.value })}
        >
          <option value="">— none —</option>
          {columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <fieldset>
        <legend>Keep as metadata</legend>
        {columns
          .filter((c) => c !== value.textColumn && c !== value.idColumn && c !== value.labelColumn)
          .map((c) => (
            <label key={c} className="radio">
              <input
                type="checkbox"
                checked={value.metadataColumns.includes(c)}
                onChange={() => toggleMetadata(c)}
              />
              {c}
            </label>
          ))}
      </fieldset>
    </div>
  )
}
