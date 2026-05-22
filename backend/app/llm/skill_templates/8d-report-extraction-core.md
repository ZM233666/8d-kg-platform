# 8d-report-extraction-core

你当前运行在 `full_report_single_pass` 路径下，目标是在**整份报告一次性抽取**的同时，保持输出严格兼容当前 runtime。

## 当前 runtime 兼容约束

- 最终输出必须严格符合当前 `ExtractionResult` schema。
- 当前 runtime 只支持这些业务实体：
  - `EightDReport`
  - `ProductEvent`
  - `FailureMode`
  - `CauseItem`
  - `ActionItem`
  - `ProductInstance`
  - `PartSerial`
  - `Organization`
  - `Person`
  - `FailureProduct`
  - `FailureProductMention`
- 当前 runtime **不支持**：
  - `Installation`
  - raw 时间辅助字段
  - `timePrecision`
  - schema 之外的任何额外字段

## 当前 runtime 可安全使用的关系

优先使用当前系统已经支持的主线关系：

- `HAS_8D_REPORT`
- `RELATED_FAILURE_MODE`
- `ROOT_CAUSE`
- `CORRECTIVE_ACTION`
- `PREVENTIVE_ACTION`
- `VERIFIES_CAUSE`
- `HAPPENED_ON`
- `RELATED_SERIAL`
- `AFFECTED_PRODUCT`
- `AFFECTED_SERIAL`
- `RESPONSIBLE_ORG`
- `REPORTED_BY_PERSON`
- `OWNED_BY_PERSON`
- `TARGET_SERIAL`
- `TARGET_PRODUCT`
- `INSTALLED_ON`
- `SUPPLIED_BY`
- `MENTIONS_FAILURE_PRODUCT`
- `INSTANCE_OF_FAILURE_PRODUCT`

治理边说明：

- `CHUNK_OF_REPORT` 由 writer 层生成，不作为 LLM 直接输出关系。

如果某个未来 v0.3 文档里提到的关系当前 runtime 不支持，例如：

- `LEADS_TO`
- `RELATED_PART`
- `RELATED_EVENT`
- `TARGET_PART`

则不要直接输出为关系，改为保留在：

- `d4_root_cause_summary`
- `CauseItem.evidence`
- `d5_permanent_correction_summary`

## 全局抽取优先级

1. 先保住主线：
   - `report`
   - `event`
   - `failure_modes`
   - `causes`
   - `actions`
2. 再补可选实体：
   - `product_instances`
   - `part_serials`
   - `organizations`
   - `failure_products`
   - `failure_product_mentions`
   - `organizations` 中 `org_type` 可用值建议覆盖：`公司`、`供应商`、`客户`、`运营商`、`部门`、`项目组`
3. 最后补关系：
   - 只输出能在当前实体集合中闭合的关系
   - 关系不要依赖“脑补出来但没有实体支撑”的端点

## Business Key 纪律

- `report.business_key = report_no`
- `event.business_key = event_id`
- `failure_mode.business_key = mode_code`
- `cause.business_key = cause_id`
- `action.business_key = action_id`
- `product_instance.business_key = serial_number`
- `part_serial.business_key = part_key`
- `organization.business_key = org_code`

如果原文没有稳定编码，不要自由发挥地创造复杂编码风格；优先输出最保守、可闭合的一致键。

## 证据与保守策略

- 每个业务实体都尽量带 `supporting_chunks`
- 证据不足时宁可少抽，不要为了图谱完整性强行补事实
- 不要把纯现象直接当根因
- 不要把纯计划直接当完成措施
- 不要把组织名 / 人名 / 时间表达的推断结果写成 schema 之外的结构
- `ProductInstance` 和 `PartSerial` 有歧义时, 默认优先保守到 `PartSerial`
- `EightDReport.owner_name` 只有在原文明确出现 `负责人 / 责任人 / owner` 等信号时才填写
- `ProductEvent.severity` 只有在原文明确出现 `等级 / 级别 / 定义为` 等信号时才填写
- `Organization.org_type` 对地铁/深铁/轨道交通运营主体优先使用 `运营商`（如 `兰州地铁`、`深圳地铁`、`中建深铁`）

## ProductInstance / PartSerial 判别优先级

### `ProductInstance`

只有在文本明确指向整机 / 车辆 / 单台设备实例时, 才创建 `ProductInstance`。

强信号包括:

- 明确的车辆号、车号、设备号、资产编码
- 明确写成某台车、某套阀、某台设备、某个产品实例
- 同时伴随客户、线路、地点、投运信息

### `PartSerial`

以下情况优先创建 `PartSerial`, 不要误建成 `ProductInstance`:

- 一串零件序列号或批次号被并列列出
- 文本在描述拆解、检测、故障件、返工件、库存件、批次件
- 同一小节里连续出现多个相似编码, 例如 `2207134SMF` 这类检测样本

如果一个编码看起来更像“故障件/零件样本清单”, 且没有客户、线路、车号、设备归属信息:

- 优先输出为 `PartSerial`
- 不要因为它长得像唯一编号就直接输出 `ProductInstance`

## 单次整篇抽取的注意点

- 你可以在内部按 D2 / D4 / D5 / D7 分段思考
- 但最终只输出一个完整闭合的 `ExtractionResult` JSON
- 多段信息冲突时，以**结论段 / 审批段 / 已验证描述**优先于早期假设段
- 如果输入只有一个 `full_document` chunk，不要因为 chunk 只有一块就放弃章节语义
- 应主动根据正文中的 D1-D8 标题、目录、段落标题和动作句，把 D2 / D4 / D5 / D7 信息重新分段理解后再抽取
