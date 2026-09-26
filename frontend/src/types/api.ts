export type ClassificationType = 'binary' | 'multiclass' | 'multilabel'
export type AnnotationMode = 'ai_first' | 'human_first' | 'on_demand'
export type TrainingStrategy = 'manual' | 'batch' | 'adaptive'
export type SamplingStrategy = 'random' | 'balanced' | 'uncertainty' | 'smart'
export type AnnotationOutcome = 'submitted' | 'skipped' | 'flagged'
export type SuggestionSource = 'imported' | 'llm' | 'classifier'

export interface ProjectSettings {
  annotation_mode: AnnotationMode
  training_strategy: TrainingStrategy
  sampling_strategy: SamplingStrategy
  batch_training_threshold: number
}

export interface Project {
  id: number
  name: string
  description: string | null
  classification_type: ClassificationType
  data_type: 'text'
}

export interface ProjectDetail extends Project {
  settings: ProjectSettings
  has_taxonomy: boolean
  dataset_count: number
  record_count: number
  annotated_count: number
}

export interface Label {
  id: number
  name: string
  description: string | null
  include_criteria: string | null
  exclude_criteria: string | null
  examples: string[]
}

export interface TaxonomyOut {
  id: number
  name: string
  active_version_number: number
  labels: Label[]
}

export interface DatasetPreview {
  dataset_id: number
  columns: string[]
  preview_rows: Record<string, string>[]
}

export interface Suggestion {
  source: SuggestionSource
  label_ids: number[]
  label_names: string[]
}

export interface AnnotateNextResponse {
  record: {
    id: number
    text: string
    metadata: Record<string, unknown>
    existing_label_raw: string | null
  } | null
  suggestion: Suggestion | null
  progress: { completed: number; total: number }
}

export interface Progress {
  total: number
  submitted: number
  skipped: number
  flagged: number
  remaining: number
  label_distribution: Record<string, number>
}
