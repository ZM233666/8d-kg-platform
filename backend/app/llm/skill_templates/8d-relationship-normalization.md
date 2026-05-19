# 8d-relationship-normalization

这个模块的首要目标是**保障图质量**，不是让图里出现尽可能多的边。

## 当前 runtime 允许的关系白名单

最终只能输出当前系统已支持的关系：

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
- `TARGET_PRODUCT`
- `TARGET_SERIAL`
- `INSTALLED_ON`
- `SUPPLIED_BY`

如果你识别到的语义更接近未来 v0.3 目标层，例如：

- `LEADS_TO`
- `RELATED_EVENT`
- `RELATED_PART`
- `TARGET_PART`

则当前阶段不要把它们直接输出成关系，改为保留在：

- `summary`
- `evidence`
- `title`

## 关系归一原则

### 显式关系优先

如果文本已经明确给出关系，就优先保留显式关系，不要再用常识覆盖它。

### 单一候选才允许保守补边

只有在候选目标足够单一时，才允许做保守补边。

例如：

- 只有 1 个 `FailureMode` 时，`CauseItem -> RELATED_FAILURE_MODE` 才比较安全
- 只有 1 个 `ProductInstance` 时，`ProductEvent -> HAPPENED_ON` 才比较安全
- 只有 1 个 `PartSerial` 时，`PartSerial -> INSTALLED_ON -> ProductInstance` 才比较安全

### 多候选禁止全连接

如果某类实体有多个候选，不要做“每个连每个”的全连接补边。

这是当前保障图质量的核心纪律。

### 端点必须闭合

不要输出指向不存在实体的关系。  
`from_key` 和 `to_key` 必须都能在当前实体集合中找到。

### 关系方向必须 canonical

只输出当前 runtime 已定义方向，不输出反向边。

## 组织关系的特殊规则

### `RESPONSIBLE_ORG`

只有当文本明确指向责任部门 / 责任公司 / 责任单位时，才输出：

- `EightDReport -> RESPONSIBLE_ORG -> Organization`
- `ActionItem -> RESPONSIBLE_ORG -> Organization`

不要把所有 `Organization` 都默认视为责任主体。
不要把封面上的公司抬头、联系地址、网址所属公司，直接当作 `RESPONSIBLE_ORG`。

### `SUPPLIED_BY`

只有当 `Organization` 明显是供应商时，才输出：

- `PartSerial -> SUPPLIED_BY -> Organization`

如果组织更像客户、内部部门、责任单位，不要误挂成 `SUPPLIED_BY`。

## `VERIFIES_CAUSE` 的特殊规则

只有在以下任一情况下才输出：

- 文本明确说该措施用于验证 / 消除 / 关闭某原因
- 当前只有 1 个已验证原因，且措施明显围绕该原因展开

如果有多个原因候选，不要把每个 `ActionItem` 都连到所有 `CauseItem`。

## 最终提醒

- 图质量优先于召回率
- 关系不明确时，宁可少一条边，不要补一条错边
- 当前阶段最危险的不是“少连了一条”，而是“错误全连接导致图谱污染”
