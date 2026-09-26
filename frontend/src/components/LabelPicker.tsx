import type { ClassificationType, Label } from '../types/api'

interface Props {
  classificationType: ClassificationType
  labels: Label[]
  selected: number[]
  onChange: (labelIds: number[]) => void
}

export default function LabelPicker({ classificationType, labels, selected, onChange }: Props) {
  const isMultilabel = classificationType === 'multilabel'

  function toggle(labelId: number) {
    if (isMultilabel) {
      onChange(
        selected.includes(labelId)
          ? selected.filter((id) => id !== labelId)
          : [...selected, labelId]
      )
    } else {
      onChange([labelId])
    }
  }

  return (
    <fieldset className="label-picker">
      <legend>Label{isMultilabel ? '(s)' : ''}</legend>
      {labels.map((label) => (
        <label key={label.id} className="radio label-option" title={label.description ?? ''}>
          <input
            type={isMultilabel ? 'checkbox' : 'radio'}
            name="label"
            checked={selected.includes(label.id)}
            onChange={() => toggle(label.id)}
          />
          {label.name}
        </label>
      ))}
    </fieldset>
  )
}
