export type ClassificationType = 'binary' | 'multiclass' | 'multilabel'
export type AnnotationMode = 'ai_first' | 'human_first' | 'on_demand'
export type TrainingStrategy = 'manual' | 'batch' | 'adaptive'
export type SamplingStrategy = 'random' | 'balanced' | 'uncertainty' | 'smart'
export type AnnotationOutcome = 'submitted' | 'skipped' | 'flagged'
export type SuggestionSource = 'imported' | 'llm' | 'classifier'

export type LLMProviderChoice = 'anthropic' | 'local'

export interface ProjectSettings {
  annotation_mode: AnnotationMode
  training_strategy: TrainingStrategy
  sampling_strategy: SamplingStrategy
  batch_training_threshold: number
  llm_provider: LLMProviderChoice
  local_model_id: string | null
}

export interface LocalModelCatalogEntry {
  id: string
  display_name: string
  brand: string
  size_gb: number
  notes: string
  warning: string | null
  downloaded: boolean
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

export interface AnnotationResult {
  record_id: number
  outcome: AnnotationOutcome
  state: string
  current_labels: string[]
  current_label_ids: number[]
  revealed_suggestion: Suggestion | null
}

export interface RecordDetail {
  record: AnnotateNextResponse['record']
  suggestion: Suggestion | null
  annotation: AnnotationResult | null
}

export interface Progress {
  total: number
  submitted: number
  skipped: number
  flagged: number
  remaining: number
  label_distribution: Record<string, number>
  llm_agreement: number | null
}

export interface PromptVersion {
  id: number
  version_number: number
  template_text: string
  provider: string
  model_name: string
  is_active: boolean
  created_at: string
}

export interface PromptTestResult {
  predicted_label_ids: number[]
  predicted_label_names: string[]
  raw_response: string
}
