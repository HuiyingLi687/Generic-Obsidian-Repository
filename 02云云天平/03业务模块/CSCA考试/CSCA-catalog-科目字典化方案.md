# `/csca/catalog` 科目清单改由 `sys_dict_item` 驱动 — 方案

> 状态：**待拍板，未改代码**
> 范围：practice-service `com.hsktreasure.practice.csca`
> 关联：`GET /api/system/dict/code/csca_subject`（system-service，数据源 `sys_dict_item` / `dict_id=1001`）
> 日期：2026-10-19

---

## 一、结论

**能做，而且不用跨服务调用。**

所有服务在 `docker-compose` 里共用同一个 `mysql` 容器、同一个 `xuexitest` 库（`practice-service` 与 `system-service` 的数据源指向同一实例），
所以 practice-service **直接查 `sys_dict_item` 表**即可拿到科目清单，不需要 Feign 调 system-service，也不引入新的网络故障点。

但有三件事必须先说清楚，否则改完会「看起来对、用起来错」：

1. **字典的 `sort_order` 与当前产品顺序不一致** —— 照字典序排，理科中文会掉到最后一位（见 §五 D1）。
2. **字典只管"有哪些科目、叫什么名、什么顺序"**，题数/卷数仍要从题库聚合，两边可能对不上（见 §五 D3/D4）。
3. **`CscaSubjects` 不只是目录用**，它还承担 4 处入参校验和 `practice_name` 拼接（见 §二），只改 catalog 会留下"卡片能选、取题被拒"的裂缝。

---

## 二、现状拆解

### 2.1 代码事实

| 位置 | 作用 | 是否受影响 |
|---|---|---|
| `csca/support/CscaSubjects.java` | 硬编码 5 项 `Subject(mapping, name)`，固定顺序：文科中文 → 理科中文 → 数学 → 物理 → 化学 | 是 |
| `csca/service/impl/CscaCatalogServiceImpl.java:72` | 用 `CscaSubjects.mappings()` 当科目骨架，库里多出的码追加末尾 | 是 |
| `csca/service/impl/CscaCatalogServiceImpl.java:123` | `subjectType` 由 `CscaSubjects.nameOf()` 反查 | 是 |
| `csca/support/CscaListParams.java:68` | 收藏 / 错题本列表的科目筛选校验 | 是 |
| `csca/service/impl/CscaQuestionQueryServiceImpl.java:81` | 取题入参校验 | 是 |
| `csca/service/impl/CscaRecordServiceImpl.java:76` | 建轮入参校验 | 是 |
| `csca/service/impl/CscaRecordServiceImpl.java:133` | `practice_name = "CSCA · " + nameOf(...)`，**写入时快照** | 半是（历史记录名不变） |

### 2.2 数据事实（PROD 实测）

| 科目码 | 字典名 | 字典 sort_order | 卷数 | 题数 |
|---|---|---|---|---|
| `arts_chinese` | 文科中文 | 1 | 8 | 640 |
| `math` | 数学 | 2 | 9 | 432 |
| `physics` | 物理 | 3 | 5 | 240 |
| `chemistry` | 化学 | 4 | 4 | 192 |
| `science_chinese` | 理科中文 | **5** | 5 | 400 |

> 🔴 **顺序冲突**：字典序 = 文 / 数 / 物 / 化 / 理；产品序 = 文 / 理 / 数 / 物 / 化。

### 2.3 现有契约（文档 §3.1.1）

- `subjects[]` 科目维度 = 库中 5 个原始科目，**不做文理归并**，服务端按 5 张卡返回。
- `subjectCount` = `subjects.size()`（代码现状），文档写的是"聚合结果行数（实测 5）、不写死枚举大小"。
- 服务端**不做多语言**，只回中文原名 `subjectType`。

---

## 三、候选方案

| 维度 | **A. 直查 `sys_dict_item`（推荐）** | B. 调 system-service HTTP | C. 只用字典覆盖显示名 |
|---|---|---|---|
| 依赖 | 同库表查询 | 新增 Feign / 超时 / 鉴权 | 无 |
| 生效速度 | 改库即生效（或受缓存 TTL 影响） | 受 system-service 可用性影响 | 即生效 |
| 一致性 | 单库，强一致 | 网络抖动会出现「卡片有、取题无」 | 名字与清单可能矛盾 |
| 改动量 | 中（1 Mapper + 1 支持类 + 4 处调用点） | 大 | 小 |
| 新增故障点 | 无 | 有 | 无 |
| 能否解决顺序 / 启停 | ✅ | ✅ | ❌ |

**推荐 A。** 理由：同库同实例，直查最省事；不做服务间调用，避免 C 端目录页被 system-service 拖挂。

---

## 四、推荐方案 A 的改造点

### 4.1 新增数据访问（2 个文件）

`practice-service/src/main/java/com/hsktreasure/practice/csca/mapper/CscaSubjectDictMapper.java`
`practice-service/src/main/resources/mapper/CscaSubjectDictMapper.xml`

```sql
SELECT i.item_value AS mapping, i.item_text AS name, i.sort_order AS sortOrder
  FROM sys_dict_item i
  JOIN sys_dict d ON d.id = i.dict_id
 WHERE d.dict_code = 'csca_subject'
   AND d.deleted = 0
   AND i.deleted = 0
   AND i.status  = 0          -- 0=正常，1=禁用
 ORDER BY i.sort_order, i.id
```

> 只读 5 行小表，走 `idx_dict_id`；`ORDER BY` 有 `i.id` 兜底，避免同序值不稳定。

### 4.2 新增支持类（1 个文件）

`csca/support/CscaSubjectDict.java`

职责：**加载 + 兜底**。

- `List<Subject> enabled()`：查库；**结果为空或抛异常 → 回退 `CscaSubjects.all()`**（保证 C 端永远不白屏）。
- `String nameOf(String mapping)`：先查字典 map，未命中回退 `mapping` 本身（保持"卡片能自动长出"）。
- `Set<String> enabledMappings()`：给校验用。

`CscaSubjects` **不删**，退化为「内置兜底常量 + 语言排序」，注释同步说明。

### 4.3 改 `CscaCatalogServiceImpl`（3 处）

1. 第 72 行：骨架改为 `CscaSubjectDict.enabled()`（字典顺序），库里多出的码仍追加末尾（保留现状行为）。
2. 第 123 行：`subjectType` 改为 `CscaSubjectDict.nameOf(code)`。
3. `subjectCount` 维持 `subjects.size()`，但文档 §3.1.1 要同步口径（见 §六）。

### 4.4 改 4 处校验点

把 `CscaSubjects.resolveMapping(x)` 换成 `CscaSubjectDict.resolveMapping(x)`，语义见 D2。

### 4.5 缓存

**建议先不加。** 5 行小表、单次查询 < 1ms，而 catalog 本身已有 2 次聚合查询（题数 + 进度），多这次可忽略。
若后续压测需要：common 已有 `spring-boot-starter-data-redis`，用 60s TTL，键 `csca:subject:dict`，管理端改字典后最多 1 分钟生效。

### 4.6 放置位置的第二种选择

如果 exam-service 也要同源（它的 `CSCASubjectType` 仍是 4 值硬编码），可以把 Mapper + 支持类放进 `common`，两边共用；`mapper-locations: classpath*:/mapper/**/*.xml` 已能扫到 jar 内的 XML。**但这会把改动扩散到 common，建议二期再做**，本期只动 practice-service。

---

## 五、必须拍板的 4 个决策点

### D1 卡片顺序（影响 UI，必须先定）

| 选项 | 做法 | 结果 |
|---|---|---|
| **D1-a（推荐）** | 调字典数据：`science_chinese` 2、`math` 3、`physics` 4、`chemistry` 5 | 数据即配置，代码不再维护顺序；线上一次 UPDATE |
| D1-b | 代码里维护"优先顺序映射"，字典序作次键 | 不用改数据，但顺序仍是代码里的隐藏规则 |
| D1-c | 直接按字典 `sort_order` 排（不动数据） | 理科中文掉到最后，与产品原型不符 |

D1-a 的 SQL（单条 CASE，幂等）：

```sql
UPDATE sys_dict_item SET sort_order = CASE item_value
    WHEN 'science_chinese' THEN 2 WHEN 'math' THEN 3
    WHEN 'physics' THEN 4 WHEN 'chemistry' THEN 5 END
 WHERE dict_id = 1001 AND item_value IN ('science_chinese','math','physics','chemistry');
```

### D2 字典停用（`status=1`）或软删（`deleted=1`）时

| 选项 | 目录卡 | 入参校验 | 风险 |
|---|---|---|---|
| **D2-a（推荐）** | 隐藏 | **仍然放行**（用内置 5 码兜底） | 管理端误停用只影响展示，历史记录能继续复习 |
| D2-b | 隐藏 | 拒绝（`8001`） | 严格一致，但停用后老用户点历史记录会取题失败 |
| D2-c | 照常显示 | 仍放行 | 字典基本没用 |

### D3 题库有、字典没有的科目码（未来导入新科目）

- **D3-a（推荐）**：追加到末尾 + `WARN` 日志（现状行为，保命）——不因为漏配字典就让科目"消失"。
- D3-b：忽略，只展示字典里的。

### D4 字典有、题库 0 题

- **D4-a（推荐）**：照常出卡，`paperCount=questionCount=0` —— 运营可以先建科目再导题。
- D4-b：隐藏 0 题科目。

> 推荐组合：**D1-a + D2-a + D3-a + D4-a**，即"字典决定长相与顺序，题库决定数字，两边打架时以不丢内容为先"。

---

## 六、契约与文档影响

| 项 | 变化 |
|---|---|
| `subjects[].subjectTypeMapping` / `subjectType` | 字段名不变 |
| 卡片顺序 | 按字典 `sort_order`（D1 决定最终顺序） |
| `subjectCount` | 仍 `subjects.size()`；文档 §3.1.1 由"聚合结果行数"改为"字典启用科目数 + 题库多出码" |
| 停用科目 | 卡片消失（D2-a），`subjectCount` 可能变 4 |
| 非法科目码 | 仍 `400` / `CSCA_SUBJECT_INVALID(8001)`，无变化 |
| `practice_name` | 建轮时快照，改字典名**不影响历史记录**，只影响新记录 |

---

## 七、风险与回滚

| 风险 | 缓解 |
|---|---|
| 字典被误删 / 误停 → C 端科目消失 | 空结果回退内置 5 项（§4.2）+ WARN 日志 |
| 字典 `item_value` 被改成别的值 → 题库对不上 | 管理端建议把 `item_value` 设为不可编辑（本期不做）；`D3-a` 保证题库侧不会消失 |
| 排序调整后前端卡片位置跳变 | 与前端确认一次，D1-a 一次改到位 |
| 回滚 | 代码回退到硬编码版本；数据回滚 = 还原 `sort_order` |

---

## 八、验收用例

1. 字典 5 项正常 → catalog 返回 5 卡，顺序 = 文 / 理 / 数 / 物 / 化，`subjectCount=5`。
2. 把 `chemistry` 置 `status=1` → catalog 返回 4 卡；用 `chemistry` 取题仍可成功（D2-a）。
3. 物理删掉一整个科目的字典项 → 该科目改从题库聚合追加到末尾，题数正确（D3-a）。
4. 字典新增一个题库里没有的码 → 出现 0 题卡片（D4-a）。
5. 字典表查询异常（模拟 mapper 抛异常）→ 回退内置 5 项，catalog 正常返回。
6. 改字典中文名 → 新记录 `practice_name` 用新名，历史记录名不变。

---

## 九、工作量

约 5 个文件、核心代码 ~150 行：

| 文件 | 类型 | 规模 |
|---|---|---|
| `CscaSubjectDictMapper.java` | 新增 | ~20 行 |
| `CscaSubjectDictMapper.xml` | 新增 | ~15 行 |
| `CscaSubjectDict.java` | 新增 | ~80 行 |
| `CscaCatalogServiceImpl.java` | 改 3 处 | ~10 行 |
| `CscaListParams` / `CscaQuestionQueryServiceImpl` / `CscaRecordServiceImpl` | 改 4 处调用 | ~5 行 |
| `CscaSubjects.java` | 注释 + 降级为兜底 | ~15 行 |
| 单测 | Mockito 测 `CscaSubjectDict` 兜底 + catalog 骨架 | ~80 行 |
