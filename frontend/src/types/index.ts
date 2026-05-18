/** 8D 知识图谱平台 - TypeScript 类型定义（v0.2 KGtestV2） */

import type { AxiosRequestConfig } from 'axios'

// =============================================================================
// 基础类型
// =============================================================================

export type ReviewStatus =
  | 'auto_committed'
  | 'pending_review'
  | 'in_review'
  | 'approved'
  | 'rejected'
  | 'modified'
  | 'on_hold'
  | 'committed'

export type Sensitivity = 'public' | 'restricted' | 'confidential'

// =============================================================================
// 实体类型（对应 v0.2 KGtestV2 EntityType）
// =============================================================================

export interface BaseNode {
  node_id?: string
  business_key: string
  supporting_chunks: string[]
  source_doc_id?: string | null
  source_section: string[]
  confidence: number
  extraction_version: string
  schema_version: string
  review_status: ReviewStatus
  description?: string | null
  summary?: string | null
  owner_id?: string | null
  sensitivity: Sensitivity
  created_at?: string | null
  updated_at?: string | null
}

// EightDReport 实体
export interface EightDReport extends BaseNode {
  report_no: string
  issue_title?: string | null
  report_status?: string | null
  d2_problem_statement?: string | null
  d4_root_cause_summary?: string | null
  d5_permanent_correction_summary?: string | null
  d7_prevention_summary?: string | null
  owner_name?: string | null
  owner_role?: string | null
}

// ProductEvent 实体
export interface ProductEvent extends BaseNode {
  event_id: string
  event_code?: string | null
  event_type?: string | null
  severity?: string | null
  symptom?: string | null
  event_time?: string | null
  status?: string | null
  reporter_name?: string | null
}

// FailureMode 实体
export interface FailureMode extends BaseNode {
  mode_code: string
  mode_name?: string | null
  category?: string | null
}

// CauseItem 实体
export interface CauseItem extends BaseNode {
  cause_id: string
  title?: string | null
  cause_type?: string | null
  is_verified?: boolean | null
  evidence?: string | null
}

// ActionItem 实体
export interface ActionItem extends BaseNode {
  action_id: string
  title?: string | null
  action_type?: string | null
  status?: string | null
  owner_name?: string | null
  due_date?: string | null
}

// ProductInstance 实体
export interface ProductInstance extends BaseNode {
  serial_number: string
  asset_code?: string | null
  commission_date?: string | null
  status?: string | null
  owner_name?: string | null
  site_city?: string | null
  site_country?: string | null
  site_code?: string | null
}

// PartSerial 实体
export interface PartSerial extends BaseNode {
  part_key: string
  serial_number?: string | null
  batch_no?: string | null
  status?: string | null
  supplier_name?: string | null
}

// Organization 实体
export interface Organization extends BaseNode {
  org_code: string
  org_name?: string | null
  org_type?: string | null
}

// Chunk 实体（治理）
export interface Chunk {
  chunk_id: string
  document_id: string
  section_path: string[]
  para_idx: number
  chunk_role?: string | null
  text: string
  token_count: number
  is_table: boolean
  is_placeholder: boolean
  table_type?: string | null
  has_referenced_image: boolean
  created_at?: string | null
}

// =============================================================================
// 关系类型（对应 v0.2 ALLOWED_REL_TYPES）
// =============================================================================

export type RelationType =
  // 主线
  | 'HAS_8D_REPORT'
  | 'RELATED_FAILURE_MODE'
  | 'ROOT_CAUSE'
  | 'CORRECTIVE_ACTION'
  | 'PREVENTIVE_ACTION'
  | 'VERIFIES_CAUSE'
  // 可选
  | 'HAPPENED_ON'
  | 'RELATED_SERIAL'
  | 'AFFECTED_PRODUCT'
  | 'AFFECTED_SERIAL'
  | 'RESPONSIBLE_ORG'
  | 'TARGET_SERIAL'
  | 'TARGET_PRODUCT'
  | 'INSTALLED_ON'
  | 'SUPPLIED_BY'
  // 治理
  | 'MENTIONED_IN'
  | 'MENTIONS'

export interface RelationTriple {
  from_label: string
  from_key: string
  to_label: string
  to_key: string
  rel_type: RelationType
  properties: Record<string, unknown>
}

// =============================================================================
// 抽取结果（ExtractionResult）
// =============================================================================

export interface ExtractionResult {
  report: EightDReport | null
  event: ProductEvent | null
  failure_modes: FailureMode[]
  causes: CauseItem[]
  actions: ActionItem[]
  product_instances: ProductInstance[]
  part_serials: PartSerial[]
  organizations: Organization[]
  relationships: RelationTriple[]
  chunks: Chunk[]
  stats: Record<string, number | string>
}

// =============================================================================
// 任务（Task / ExtractionRun）
// =============================================================================

export type TaskStatus = 'pending' | 'running' | 'succeeded' | 'failed'

export interface StageMetric {
  stage_name: string
  started_at: string
  finished_at?: string
  duration_ms?: number
  ok: boolean
  error?: string
  output_summary: Record<string, unknown>
}

export interface Task {
  id: string
  document_id: string
  document_file_name?: string | null
  pipeline_version: string
  llm_model?: string
  status: TaskStatus
  started_at: string
  finished_at?: string
  token_input?: number
  token_output?: number
  cost_estimate?: number
  stage_metrics?: StageMetric[] | Record<string, unknown>
  error_detail?: Record<string, unknown>
}

export interface TaskListResponse {
  items: Task[]
  total: number
  offset: number
  limit: number
}

// =============================================================================
// 图谱查询结果（Subgraph / QueryResult）
// =============================================================================

export interface SubgraphNode {
  business_key: string | null
  labels: string[]
  properties: Record<string, unknown>
}

export interface SubgraphRelationship {
  type: string
  start_bk: string | null
  start_label: string | null
  end_bk: string | null
  end_label: string | null
  properties: Record<string, unknown>
}

export interface SubgraphResponse {
  center: { business_key: string; label: string }
  depth: number
  nodes: SubgraphNode[]
  relationships: SubgraphRelationship[]
  stats: { node_count: number; relationship_count: number }
}

// =============================================================================
// 文档类型
// =============================================================================

export interface DocumentResponse {
  id: string
  file_name: string
  file_size: number
  mime_type: string
  sha256: string
  minio_key: string
  status: string
  created_at: string
}

export interface UploadResponse {
  document: DocumentResponse
  already_exists: boolean
}

export interface DocumentListResponse {
  items: DocumentResponse[]
  total: number
  offset: number
  limit: number
}

// =============================================================================
// 枚举常量
// =============================================================================

export const ENTITY_LABELS = [
  'EightDReport',
  'ProductEvent',
  'FailureMode',
  'CauseItem',
  'ActionItem',
  'ProductInstance',
  'PartSerial',
  'Organization',
  'Chunk',
] as const

export const RELATION_TYPES = [
  'HAS_8D_REPORT',
  'RELATED_FAILURE_MODE',
  'ROOT_CAUSE',
  'CORRECTIVE_ACTION',
  'PREVENTIVE_ACTION',
  'VERIFIES_CAUSE',
  'HAPPENED_ON',
  'RELATED_SERIAL',
  'AFFECTED_PRODUCT',
  'AFFECTED_SERIAL',
  'RESPONSIBLE_ORG',
  'TARGET_SERIAL',
  'TARGET_PRODUCT',
  'INSTALLED_ON',
  'SUPPLIED_BY',
  'MENTIONED_IN',
  'MENTIONS',
] as const

export const REVIEW_STATUS_OPTIONS: ReviewStatus[] = [
  'auto_committed',
  'pending_review',
  'in_review',
  'approved',
  'rejected',
  'modified',
  'on_hold',
  'committed',
]

export const SENSITIVITY_OPTIONS: Sensitivity[] = ['public', 'restricted', 'confidential']

export const TASK_STATUS_OPTIONS: TaskStatus[] = ['pending', 'running', 'succeeded', 'failed']

// =============================================================================
// API 请求参数类型
// =============================================================================

export interface DocumentListParams {
  offset?: number
  limit?: number
}

export interface SubgraphQueryParams {
  label: string
  business_key: string
  depth?: number
  /** 过滤 Chunk 与 MENTIONED_IN，默认 true 便于查看业务关系 */
  exclude_chunks?: boolean
}

export interface GraphCenterItem {
  business_key: string
  label: string
  title: string
  degree: number
}

export interface GraphCentersResponse {
  items: GraphCenterItem[]
}

export interface ExtractionTriggerResponse {
  run_id: string
  document_id: string
  status: string
  message: string
}

// =============================================================================
// Axios 请求配置扩展
// =============================================================================

export interface RequestConfig extends AxiosRequestConfig {
  _tag?: string
}