# 8d-temporal-normalization

这个模块帮助你做保守的时间标准化，但**最终输出必须兼容当前 runtime**。

## 当前 runtime 能直接落的时间字段

- `EightDReport.report_date`
- `ProductEvent.occurred_at`
- `ActionItem.due_date`
- `ProductInstance.commission_date`

当前 runtime **不支持**：

- `reportDateRaw / occurredAtRaw / dueDateRaw / commissionDateRaw`
- `timePrecision`
- 关系级 temporal 属性

因此这些信息只能作为你内部判断的依据，不能直接出现在最终 JSON 里。

## 标准化原则

### 高置信才写规范时间

只有在原文明确给出完整时间或明确日期时，才写到规范字段：

- `2026-05-18`
- `2026年5月18日`
- `2026/05/18 10:30`

### 月份 / 年份不足以写规范字段

如果原文只有：

- `2026年5月`
- `2026年`

则当前阶段建议：

- 不强行补成 `2026-05-01`
- 规范时间字段留空
- 如该时间对原因/结论重要，可保留在 `summary` 或 `evidence` 文本中

### 相对时间默认不强猜

如果原文是：

- `当日`
- `次日`
- `一周后`
- `整改完成后`

只有在同一局部上下文中存在明确锚点，且推导几乎无歧义时，才允许转成规范时间。

否则：

- 时间字段留空
- 如有必要，把原始表达留在 `evidence` / `summary` 文本里

## 字段级提示

### `report_date`

- 优先来自封面、标题、审批区、报告头
- 可以作为相对时间推导的参考锚点
- 但不要反过来用 `report_date` 替代 `occurred_at`

### `occurred_at`

- 只表示事件发生时间
- 不要把检测时间、报告编写时间误写成 `occurred_at`

### `due_date`

- 只表示措施承诺完成时间 / 截止时间
- “计划完成后”“尽快完成”这类描述不应写为具体日期

### `commission_date`

- 只在文本明确是设备启用/投运日期时填写
- 不把发货日期、生产日期混为启用日期

## 当前 runtime 的保守降级

当时间信息重要但无法规范化时：

- 不输出 schema 之外的 raw 字段
- 可以在以下文本字段中保留关键原始时间描述：
  - `EightDReport.d2_problem_statement`
  - `EightDReport.d4_root_cause_summary`
  - `CauseItem.evidence`
  - `ActionItem.title`

## 最终提醒

- 当前阶段优先保证“时间字段不乱填”
- 不要为了让字段更完整而强行标准化模糊时间
- 模糊时间宁可留在文本证据里，也不要写成错误的 ISO 时间
