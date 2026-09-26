export type ClassificationType = 'binary' | 'multiclass' | 'multilabel'
export type AnnotationMode = 'ai_first' | 'human_first' | 'on_demand' | 'audit'
export type TrainingTrigger = 'bootstrap' | 'scheduled' | 'taxonomy_invalidated' | 'manual'
export type AnnotationOutcome = 'submitted' | 'skipped' | 'flagged'
export type SuggestionSource = 'imported' | 'llm' | 'classifier' | 'auto_label'

export type LLMProviderChoice = 'anthropic' | 'local'

export interface ProjectSettings {
  annotation_mode: AnnotationMode
  automation_enabled: boolean
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
  // "audit": this record was already auto-labeled and is being sampled for
  // a human spot-check, not labeled from scratch. Always "annotate" unless
  // automation_enabled is on for the project.
  mode: 'annotate' | 'audit'
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
  auto_labeled: number
  trust_tier: string | null
  audit_accuracy: number | null
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

export type ModelState = 'inactive' | 'active' | 'invalid_for_current_taxonomy'

interface PerClassMetric {
  precision: number
  recall: number
  f1: number
  support: number
}

export interface ModelMetrics {
  // binary / multiclass
  accuracy?: number
  precision?: number
  recall?: number
  f1?: number
  roc_auc?: number
  per_class?: Record<string, PerClassMetric>
  confusion_matrix?: { labels: string[]; matrix: number[][] }
  // multilabel
  micro_f1?: number
  hamming_loss?: number
  per_label?: Record<string, PerClassMetric>
  // shared
  macro_f1?: number
  n_train: number
  n_held_out: number
  // present only when this candidate was compared against a previously
  // active model (automation on) — see training_service._maybe_auto_activate
  comparison?: {
    vs_active_model_id: number
    active_score: number
    candidate_score: number
    metric: string
    regressed: boolean
  }
}

export interface ModelVersion {
  id: number
  version_number: number
  classifier_type: string
  state: ModelState
  metrics_json: ModelMetrics | null
  activated_at: string | null
  deactivated_at: string | null
  created_at: string
}

export interface TrainingRun {
  id: number
  trigger: TrainingTrigger
  trigger_reason: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  annotation_count_snapshot: number
  started_at: string | null
  completed_at: string | null
  resulting_model_version_id: number | null
  error_message: string | null
}
