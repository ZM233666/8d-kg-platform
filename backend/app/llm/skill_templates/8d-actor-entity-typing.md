# 8d-actor-entity-typing

这个模块帮助你减少“人名 / 公司名 / 部门名”混淆，但**最终输出必须适配当前 runtime**。

## 总原则

- 原始 actor 文本优先保留在现有字段里：
  - `ProductEvent.reporter_name`
  - `EightDReport.owner_name`
  - `ActionItem.owner_name`
- 内部判断时，先识别强组织信号，再识别个人信号。
- 当前 runtime **不支持 `Person` 实体**，所以你不能在最终 JSON 中输出 `Person`。

## 判别顺序

1. 先判断是否为明显组织 / 部门 / 客户单位 / 供应商单位
2. 如果不是，再判断是否为明显个人
3. 如果仍不确定，只保留原始字符串，不额外建结构

## 强组织信号

下列表达优先按组织理解：

- 带公司/厂/部/科/组/中心/供应商/客户等后缀
- 明显是企业、部门、项目组、客户单位、供应商单位

典型例子：

- `克诺尔苏州`
- `克诺尔制动系统（苏州）有限公司`
- `质量部`
- `制造部`
- `客户QA`
- `苏州某密封件供应商`

## 强个人信号

下列表达优先按个人理解：

- 典型中文姓名
- 姓名 + 称谓
- 人名后带联系方式
- 上下文明确是责任人 / 联系人 / 报告人 / 操作人

典型例子：

- `吴重人`
- `张工`
- `王经理`
- `责任人：张工`

## 当前 runtime 的落地方式

### `reporter_name`

- 如果明显是个人：直接保留该字符串到 `reporter_name`
- 如果明显是组织：也保留原始字符串到 `reporter_name`
- 当前 runtime 没有 `REPORTED_BY_PERSON` / `REPORTED_BY_ORG` 关系，所以不要为了补关系而创造额外结构

### `owner_name`

- 如果明显是个人：保留到 `owner_name`
- 如果明显是组织 / 部门：保留到 `owner_name`
- 只有当文本明确指向报告责任组织时，才额外输出：
  - `Organization`
  - `EightDReport -> RESPONSIBLE_ORG -> Organization`

### `ActionItem.owner_name`

- 同样优先保留原始字符串
- 若组织责任归属非常明确，可复用已有 `Organization`
- 不要创造当前 runtime 不支持的 `OWNED_BY_PERSON`

## 组织实体何时值得输出

当前 runtime 中，只有在组织能参与**已支持的关系**时，才建议输出 `Organization`：

- `EightDReport -> RESPONSIBLE_ORG -> Organization`
- `PartSerial -> SUPPLIED_BY -> Organization`

如果一个组织只出现在 `reporter_name` 这类位置，当前阶段通常：

- 保留原始字符串
- 不额外创建悬空的 `Organization`

## 公司抬头 / 联系地址的特殊规则

- 出现在封面、联系地址、电话、网址附近的公司抬头，默认视为文档元信息，不自动等价于 `owner_name`
- 只有文本明确出现责任归属、执行主体、整改主体时，才把该公司作为 `RESPONSIBLE_ORG`
- `内部部门` 只用于真正的部门名称，例如 `质量部`、`制造部`
- 如果名称明显是完整公司法定名，例如带 `有限公司`、`Co., Ltd.`，不要标成 `内部部门`
- 同一组织如果同时出现英文法定名和中文短名，优先采用责任语境里出现的较稳定名称，不要重复创建两个组织

## 不确定时的默认策略

- 只保留原始字段
- 不输出额外组织实体
- 不发明 schema 之外的关系

这条保守策略优先于“多建一些节点”。
