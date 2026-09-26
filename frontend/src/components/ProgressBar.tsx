interface Props {
  completed: number
  total: number
}

export default function ProgressBar({ completed, total }: Props) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0
  return (
    <div className="progress">
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <span>
        {completed} / {total}
      </span>
    </div>
  )
}
