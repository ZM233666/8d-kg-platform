# 8d-d5-action-extraction

这个模块专门约束 D3 / D5 / D6 / D7 措施抽取，但**最终输出必须兼容当前 runtime**。

## 当前 runtime 下 D5 可直接落的结构

可直接输出：

- `ActionItem`
- 条件性 `Organization`
- 条件性 `Person`
- `EightDReport -> CORRECTIVE_ACTION -> ActionItem`
- `EightDReport -> PREVENTIVE_ACTION -> ActionItem`
- `ActionItem -> VERIFIES_CAUSE -> CauseItem`
- `ActionItem -> TARGET_PRODUCT -> ProductInstance`
- `ActionItem -> TARGET_SERIAL -> PartSerial`
- `ActionItem -> RESPONSIBLE_ORG -> Organization`
- 条件性 `ActionItem -> OWNED_BY_PERSON -> Person`

当前 runtime **暂不直接支持**：

- `TARGET_PART`
- `RELATED_EVENT`
- raw 时间辅助字段
- `timePrecision`

因此这些信息如果重要，应保留在：

- `ActionItem.owner_name`
- `ActionItem.title`
- `EightDReport.d5_permanent_correction_summary`
- `EightDReport.d7_prevention_summary`

## ActionItem 创建规则

只有当文本满足以下至少一项时，才创建 `ActionItem`：

- 明确提出要执行的措施
- 明确说明已经执行/完成的措施
- 明确列出隔离、返工、更换、筛查、培训、流程修订、检验加强等动作

以下情况不要创建 `ActionItem`：

- 纯根因描述
- 纯现象描述
- 只有责任主体但没有动作
- 没形成明确动作的弱建议

## action_type 默认策略

当前 runtime 只保留三类：

- `临时D3`
- `纠正D5`
- `预防D7`

推荐映射：

- 临时遏制、隔离、加严筛查 -> `临时D3`
- 永久纠正、替换、修复、参数调整、实施动作 -> `纠正D5`
- 防再发、培训、规范修订、检验标准更新 -> `预防D7`

如果原文更接近 D6 执行阶段，当前 runtime 也先并入：

- `纠正D5`

## title 写法

`ActionItem.title` 应尽量：

- 简短
- 动作导向
- 去掉“计划 / 建议 / 拟 / 后续”等口吻噪声

例如：

- `隔离同批次阀门并加严测试`
- `更换为 Viton 材质 O 型圈`
- `来料增加 100% 硬度检验`
- `修订来料检验规范并培训质检员`

## 复合句拆分规则

默认采用“中等偏保守”的拆分：

- 不同责任对象、不同完成日期、不同目标对象时，拆成多个 `ActionItem`
- 同一动作的实施 + 验证，不要机械拆成两个动作
- 同一动作的细节补充，优先保留在 `title` 或上下文中

## VERIFIES_CAUSE 规则

只有在文本明确表达“该措施用于验证 / 消除 / 关闭某原因”时，才输出：

- `ActionItem -> VERIFIES_CAUSE -> CauseItem`

如果只能看出“和问题有关”，但不能稳定映射到某个已知 `CauseItem`：

- 不强行输出 `VERIFIES_CAUSE`

## TARGET_PRODUCT / TARGET_SERIAL 规则

只有当目标实例或序列件在当前实体集合中已经存在，且文本明确指向时，才输出：

- `ActionItem -> TARGET_PRODUCT -> ProductInstance`
- `ActionItem -> TARGET_SERIAL -> PartSerial`

如果对象表述模糊，例如：

- `该批次件`
- `相关产品`
- `此类阀门`

但无法稳定闭合到已有实体：

- 不强行输出目标关系
- 把对象语义尽量保留在 `title`

## RESPONSIBLE_ORG 规则

只有在文本明确给出责任部门 / 责任单位 / 供应商 / 客户单位时，才输出：

- `Organization`
- `ActionItem -> RESPONSIBLE_ORG -> Organization`

如果只有个人负责人或岗位表达：

- 优先保留到 `owner_name`
- 不要创造 `Person`

如果输入是单个 `full_document` chunk：

- 不要因为封面抬头、联系地址、公司名页眉页脚，就把该组织默认挂到所有 `ActionItem`
- `RESPONSIBLE_ORG` 必须来自动作句附近、责任描述附近或措施表格中的局部证据

## owner_name / due_date 规则

### `owner_name`

- 始终先保留原始字符串
- 如果明显是个人，且文本支持稳定，可同时输出：
  - `Person`
  - `ActionItem -> OWNED_BY_PERSON -> Person`
- 如果更像组织，继续优先走 `owner_name` + `RESPONSIBLE_ORG`

### `due_date`

- 只有明确完整日期或高置信日期时才写 `due_date`
- 对“次周完成”“月底前”“三个月内”这类模糊时间，不要硬写 ISO 日期

## 与 D4 的边界

如果一句话同时包含原因和措施：

- 原因部分交给 D4
- 措施部分交给 D5

例如：

- `由于来料检验未覆盖硬度项，后续增加硬度全检`
  - 原因在 D4
  - `增加硬度全检` 在 D5

## 与未来 v0.3 的兼容策略

如果你识别到：

- 作用零件型号层
- 事件级关联
- 个人负责人
- 更细的时间精度

但当前 runtime 不支持，请遵循：

1. 不输出 schema 之外结构
2. 不输出当前白名单外关系
3. 尽量把语义压缩进 `title`、`owner_name`、`summary`
