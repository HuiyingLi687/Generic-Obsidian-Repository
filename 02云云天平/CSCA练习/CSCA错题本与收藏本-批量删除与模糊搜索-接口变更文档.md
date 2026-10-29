# CSCA 错题本 / 收藏本 —— 批量删除与关键词搜索 接口变更文档

| 项 | 内容 |
|---|---|
| 版本 | v1.1（v1.0 → v1.1：§8 五项口径已确认 + §11 编码落地记录） |
| 日期 | 2026-10-26 |
| 适用范围 | `practice-service` → `com.hsktreasure.practice.csca`（收藏 §3.6.1 / 错题本 §3.6.2） |
| 主文档 | 《CSCA练习-接口设计文档.md》（本文是它的**增量变更**，不是替代；同步点见 §9） |
| 状态 | ✅ **已编码并单测通过**（98 个 CSCA 相关用例全绿，见 §11） |
| 影响面 | 2 个新端点 + 2 个现有端点各加 1 个可选参数；**无 DDL、无索引变更、无表结构变更** |

---

## 0. 结论速览

先说清一件事：**「按钮」是前端的**。后端能提供的是让按钮可用的**能力**——一次请求删多条，以及能在题面里搜词。所以本次交付 4 项：

| # | 变更 | 类型 | 端点 |
|---|---|---|---|
| 1 | 错题本**批量移出** | 🆕 新增端点 | `POST /csca/wrong-book/batch-remove` |
| 2 | 收藏**批量取消** | 🆕 新增端点 | `POST /csca/favorites/batch-cancel` |
| 3 | 错题本列表**支持关键词** | 🔧 加可选入参 | `GET /csca/wrong-book` + `keyword` |
| 4 | 收藏列表**支持关键词** | 🔧 加可选入参 | `GET /csca/favorites` + `keyword` |

四个变更**全部向后兼容**：老版本 App 不传 `keyword` 时行为与现在逐字节一致；两个新端点老版本不会调用。

### 需求 → 落地形态

| 产品需求原文 | 落地形态 | 说明 |
|---|---|---|
| 错题本「批量删除按钮」 | 1 个批量移出端点 + 前端多选态 | 语义是**移出错题本**（软删），不是物理删除 |
| 收藏本「批量删除按钮」 | 1 个批量取消端点 + 前端多选态 | 语义是**取消收藏**（软删，后续可复活） |
| 「一个查询的接口，可模糊查询题目」 | 列表接口加 `keyword` 过滤（§3.1 说明为何不新开端点；若要独立端点，5 行桥接即可） | 分页 / 筛选 / 排序全部沿用，`total` 自动变成命中数 |

---

## 1. 批量删除

### 1.1 为什么用 `POST` 而不是 `DELETE`

REST 语义上「删除多条」最自然是 `DELETE /csca/wrong-book/batch` + body 带 id 数组，但这里**刻意用 `POST`**，有三条具体理由：

| # | 风险 | 说明 |
|---|---|---|
| 1 | **body 被静默丢弃** | `DELETE` 带 body 不在 HTTP/1.1 的保证范围内。Android 的 `HttpURLConnection` 直接不支持 DELETE body；部分网关 / WAF / 反向代理也会剔除。表现是**后端收到空数组 → 删 0 条 → 仍返回成功**，属于最坏的一类故障（用户以为删了） |
| 2 | **路径冲突** | 现有单题接口是 `DELETE /csca/wrong-book/{questionId}`。加一个 `DELETE /csca/wrong-book/batch` 会与 `{questionId}` 同层，虽然 Spring 精确匹配优先，但**网关侧的路径规则 / 前端拦截器按前缀匹配时容易误伤** |
| 3 | **与项目既有风格一致** | 本模块已有 `POST /csca/records/{recordId}/answers/batch`（批量作答）先例，批量写操作统一走 `POST + body` |

> 单题 `DELETE` 保留不动（前端单卡「移出」按钮仍用它），批量端点与它**并存**，不是替换。

### 1.2 错题本批量移出

```
POST /api/practice/csca/wrong-book/batch-remove
Content-Type: application/json
X-Client-Type: APP
Authorization: <token>
```

**请求体**

```json
{ "questionIds": ["2067116260768489474", "2067116260768489475", "2067116260768489480"] }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `questionIds` | `string[]` | 是 | 题目 id 数组。**元素是字符串**（雪花 id 19 位，超出 JS 安全整数，见主文档 §0.4）。长度 **1–100**，超范围 → `8005`；重复 id 自动去重（保序） |

> ⚠️ `userId` **不接受传入**，由 Token 取得（强鉴权，与现有三个端点一致）。网关白名单不含 `/api/practice/csca/wrong-book*`。

**响应体**

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "requestedCount": 3,
    "removedCount": 2,
    "skippedCount": 1,
    "wrongCount": 242
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `requestedCount` | `number` | **去重后**的请求条数（前端用它算「还剩几条没处理」） |
| `removedCount` | `number` | 本次实际软删的条数（`UPDATE` 的 `affectedRows`） |
| `skippedCount` | `number` | `requestedCount - removedCount`：本来就不在册 / 不是本人的题 / 已被别的设备删过 |
| `wrongCount` | `number` | 操作完成后该用户**全量在册总数**（`user_id + deleted=0`，不带筛选、不 join），供前端免二次请求刷新角标 —— 与现有单题 `DELETE` 回执的 `wrongCount` **同一个口径** |

> `skippedCount > 0` **不是错误**：批量删除的语义是「让这些题都不在我的错题本里」，本来就不在册的题天然满足，故返回成功而非报错。

### 1.3 收藏批量取消

```
POST /api/practice/csca/favorites/batch-cancel
```

**请求体**：与错题本完全同构（`questionIds`）。

```json
{ "questionIds": ["2067116260768489474", "2067116260768489475"] }
```

**响应体**

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "requestedCount": 2,
    "removedCount": 2,
    "skippedCount": 0,
    "favoriteCount": 14
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `requestedCount` | `number` | 去重后请求条数 |
| `removedCount` | `number` | 实际取消的条数 |
| `skippedCount` | `number` | 本来就没收藏 / 不是本人的题 |
| `favoriteCount` | `number` | 操作后该用户已收藏总数（口径 = `user_id + deleted=0`，与单题 `DELETE` 一致） |

> ⚠️ **批量取消不需要 `recordId`**：现有单题 `PUT` / `DELETE` 要求 `recordId` 必填，是因为它要往 `record_id` 列写「首次收藏发生在哪一轮」的**快照**（仅 INSERT 写）。批量取消是纯软删、**不插行、不写快照**，所以没有这个入参。想加也加不了——一个批量请求横跨多道题，不存在「同一轮」。

### 1.4 业务逻辑

**错题本批量移出（7 步）**

```
① 鉴权：userId 从 Token 取（未登录 / 非 APP → 401）
② 解析入参：questionIds 为 null / 空数组 → 8005
③ 去重（LinkedHashSet，保序）→ 去重后 size ∉ [1,100] → 8005
④ 逐个 parseLong（非数字 → 8005，整体失败，不做部分成功）
⑤ 一条 UPDATE 软删（见下）
⑥ 查 countWrong(userId) 拿最新角标
⑦ 组装回执
```

`⑤` 的 SQL：

```sql
UPDATE csca_question_wrong
   SET deleted = 1,
       update_by = #{userId},
       updated_time = #{now}
 WHERE user_id = #{userId}
   AND question_id IN (...)
   AND deleted = 0
```

- `deleted = 0` 条件让 `affectedRows` 恰好等于「本次真实移出的条数」，天然幂等（重复调第二次为 0）。
- 走唯一键 `uk_user_question(user_id, question_id)`，不需要新索引。
- `updated_time` 语义：与单题移出一致（状态变更时刻）。**已经被软删的行不会被刷新**（`deleted=0` 条件挡住），避免无意义写入。

**收藏批量取消（5 步）**：同上，把表换成 `csca_question_favorite`，`⑥` 换成 `countFavorites(userId)`。

**事务**：`@Transactional(rollbackFor = Exception.class)`（与单题版一致）。虽然只有一条 UPDATE，但「UPDATE + COUNT」放同一事务内可保证回执里的 `wrongCount` 一定包含本次改动。

**并发**：两个请求同时删同一批 → 第二个 `affectedRows = 0`，返回 `skippedCount = n`，无异常。不同用户之间因 `WHERE user_id` 隔离，无锁竞争。

### 1.5 单题 vs 批量：为什么批量**不用** upsert

现有单题 `DELETE` 走的是 `upsertWrongs`（`INSERT … ON DUPLICATE KEY UPDATE deleted = 1`），覆盖「未收录时也插一行 `deleted = 1` 占位」这条分支，并且**每次都要先查一次准入**（`selectFavoriteAdmission`）判断这题是不是 CSCA 的。

批量版**刻意不复用**这条路径：

| 维度 | 单题 `DELETE`（现状） | 批量（本次） |
|---|---|---|
| 写库方式 | `INSERT … ON DUPLICATE KEY UPDATE` | 纯 `UPDATE` |
| 未在册的题 | **插一行** `deleted=1` 占位 | 不插，`affectedRows` 不计 |
| 准入校验 | 每题 1 次 `selectFavoriteAdmission`（非 CSCA → `8006`） | **不做**（`WHERE user_id` 已足够） |
| 请求 100 条的成本 | 100 次 SELECT + 1 次批量 upsert | **1 条 UPDATE** |

为什么能省掉准入校验：

1. 这些 id 来自**用户自己的列表**，列表里的行在收录/收藏时**已经过准入**；
2. 纯 UPDATE 不插行 → 不存在「往表里写非 CSCA 脏行」的风险（这是单题版做准入的核心动机）；
3. 别人的题 / 不存在的题 → `WHERE user_id` + `IN` 自然影响 0 行，结果就是 `skippedCount`。

为什么能省掉「插占位行」：单题版插 `deleted=1` 行是为了保持「唯一键恒成立、后续判错能复活」。批量不插也不破坏这个性质 —— 后续该题若被判错，`upsertWrongs` 会正常插入 `deleted=0` 的新行。两种路径的**最终态完全一致**（都不在册），只是表里少一行历史占位。

> 结论：批量版比单题版更快、更简单，且不改变任何业务语义。**不要**为了"复用代码"把批量也改成逐条 `upsert`。

### 1.6 错误码

| code | HTTP 口径 | 触发条件 |
|---|---|---|
| `401` | 401 | 未登录 / Token 无效 / `X-Client-Type` 不是 `APP` |
| `8005` | 400 | `questionIds` 缺失、空数组、去重后为 0 条、超过 100 条、元素不是数字 |

> 批量端点**不产生 `8006`**（题目不存在）：不存在的 id 只是 `skippedCount` 的一部分。

### 1.7 前端交互约定（供客户端参考，后端不实现）

| 场景 | 约定 |
|---|---|
| 多选态 | 长按 / 点「管理」进入多选，列表项显示复选框 |
| 全选范围 | **仅当前页**（后端分页，前端拿不到全集）。要「清空全部」需要另开端点，见 §9 |
| 删除确认 | 二次确认弹窗写明条数：「确定移出 N 道题？」 |
| 请求分批 | 一次不超过 100 条；超过时前端按 100 切批，串行发（避免并发写同表） |
| 结果提示 | `removedCount` 条已移出；`skippedCount > 0` 时可提示「N 条已不在列表中」，也可静默 |
| 删除后 | 用回执里的 `wrongCount` / `favoriteCount` 直接刷角标；列表**从第 1 页重查**（当前页可能已空） |
| 失败重试 | 幂等，直接重发同一批即可（第二次 `removedCount` 可能是 0，不报错） |

---

## 2. 关键词搜索

### 2.1 落地形态：加参数 vs 新端点

需求原文是「新增一个查询的接口」。但**新开端点会让同一套逻辑写两遍**，所以推荐把能力落在**现有列表接口的新增可选参数**上：

| 维度 | 方案 A：列表加 `keyword`（✅ 推荐） | 方案 B：独立 `search` 端点 |
|---|---|---|
| 筛选参数 | 复用现有 6–7 个 | 要复制一遍（科目 / 来源 / 语言 / 时间 / 排序 / 分页） |
| `total` 与分页 | 天然同一套 where | 要写第二份计数 SQL，**必然漂移** |
| 题面装配 | 复用 `CscaQuestionAssembler` | 再调一次同样的装配 |
| 前端 | 搜索 / 清空搜索 = 传 / 不传参数，**同一个 URL** | 两个 URL 来回切，清空时忘切回是常见 bug |
| 改动量 | 2 个 Query DTO + 2 个 XML 片段 | 前者全部 + 2 个 Controller 方法 + 2 个 Service 方法 |

**方案 A 已经完整满足「可以模糊查询题目」**——搜索只是列表的一个过滤条件，和「按科目筛」「按时间筛」是同一层的东西。

如果产品 / 前端坚持要独立 URL，**不必重复逻辑**，只需在 Controller 加一个薄桥接（5 行，Service 一行不改）：

```java
// 与 list() 完全同参，内部转调同一个 Service 方法 —— 逻辑只有一份
@GetMapping("/wrong-book/search")
public Result<CscaWrongBookResponse> search(
        @RequestParam(value = "keyword", required = false) String keyword, /* 其余参数同 list() */ ...) {
    return list(keyword, ..., httpRequest, clientType);   // 直接复用
}
```

> 文档余下部分按方案 A 描述；方案 B 只是多一个入口，参数与返回体完全一致。

### 2.2 入参规格

| 参数 | 位置 | 必填 | 规格 |
|---|---|---|---|
| `keyword` | query | 否 | 关键词。**最长 50 字符**（去首尾空白后），超长 → `8005`；空白 / 不传 → **不过滤**（行为与现在完全一致） |

**归一化（后端做，顺序不可颠倒）**：

```
① trim 首尾空白（含全角空格 U+3000）
② 全角 → 半角（复用 common 的 PunctuationConvertUtil.convert）
③ 通配符转义：\ → \\，% → \%，_ → \_
④ 空白结果 → 视为 null（不过滤）
```

🔴 **第 ② 步的必要性（v1.1 已在 TEST 库实测修正）**

> ⚠️ v1.0 曾写「导入链路强制全角转半角，所以库里存的是半角，不转就搜不到」——**这个说法是错的**，实测已推翻。

`question` 表的 collation 是 **`utf8mb4_0900_ai_ci`，对宽度不敏感**，下列比较全部为真：

```
'（' = '('    'Ａ' = 'A'    '１' = '1'    '％' = '%'    '＿' = '_'    '　'(全角空格) = ' '
```

所以「按括号 / 逗号 / 字母 / 数字搜」，转不转都能命中（实测：`含'(1)'` 与 `含'（1）'` 都是 2 条）。
库里也并非全半角 —— `passage` 含全角 `（` 有 789 条、含全角 `，` 有 973 条。

**转换真正不可省的是「被导入链路改写成另一个字符的标点」** —— 它们不是宽度变体，collation 帮不上忙：

| 用户输入 | 库里存储 | `=` 等价？ | 不转换的结果 |
|---|---|---|---|
| `。` | `.`（895 条） | ❌ 不等价 | **0 命中**（而库里有 895 条带句号的题） |
| `…` | `.`（同上） | ❌ | 0 命中 |

另外，第 ② 步必须排在第 ③ 步**之前**：`％` 要先变成 `%` 才有机会被转义成 `\%`。

例：

| 用户输入 | 归一化后 | 说明 |
|---|---|---|
| `（1）下列` | `(1)下列` | ✅ 命中（不转换也命中，因为宽度不敏感；转换只是为了口径统一） |
| `50%的` | `50\%的` | ✅ `%` 被转义成字面量；**不转义则会匹配全部** |
| `第1题。` | `第1题.` | ✅ 关键：`.` 是另一个字符，不转换必 0 命中 |

大小写：`question` 表 collation 是 `utf8mb4_0900_ai_ci`（**大小写不敏感 + 重音不敏感**），所以英文搜索无需 `LOWER()`，`Function` 与 `function` 命中结果相同。

### 2.3 搜索范围

**命中三列（OR），全部在 `question` 表**：

| 列 | 含义 | 是否纳入 | 依据 |
|---|---|---|---|
| `q.passage` | 题目内容（**实际题面主体**） | ✅ | 实测 CSCA 1904 题中 `passage` 非空 1644 条，是题面主字段 |
| `q.content` | 题目标题 | ✅ | 与 `passage` **互斥使用**（不同 `layout` 用不同列），必须一起搜，否则漏一半 |
| `q.option_content` | 题目选项（JSON） | ✅ | 大量关键词只出现在选项里（如「石油分馏」「酒精挥发」），不搜等于搜不到 |
| `q.number` | 题号 | ❌ | 用户不知道题号；且纯数字会与题干里的数字误撞 |
| `q.analysis` | 解析 | ❌ | 列表本来就不下发解析（解析走 `/solution`），搜它会对不上「为什么这道题出现在结果里」 |
| `q.section_title` / `q.title1_text` | 试卷标题类 | ❌ | 同一套卷的题都有，搜它等于全命中，无区分度 |

🔴 **`q.content` 与 `q.passage` 必须同时搜**，这是实测数据支撑的：CSCA 1904 题里 `content` 为空的 **1794 条（94.2%）**、`passage` 为空的 260 条 —— 两列是「二选一使用」的关系，只搜 `content` 会漏掉 94% 的题。

### 2.4 SQL 实现

在 `wrongBookListFilters` / `favoriteListFilters` 片段里追加一个 `<if>`，**分页与计数共用同一片段**（现有结构已保证，红线）：

```xml
<if test="keyword != null">
    AND (
        q.passage        LIKE CONCAT('%', #{keyword}, '%') ESCAPE '\\'
     OR q.content        LIKE CONCAT('%', #{keyword}, '%') ESCAPE '\\'
     OR CAST(q.option_content AS CHAR) LIKE CONCAT('%', #{keyword}, '%') ESCAPE '\\'
    )
</if>
```

四个实现细节：

| # | 点 | 说明 |
|---|---|---|
| 1 | **必须 `CAST(... AS CHAR)`** | `option_content` 是 `json` 类型列。MySQL 8 允许 `LIKE` 直接作用于 json（隐式转字符串），但**依赖隐式转换在不同小版本上行为不稳定**，显式 CAST 更稳，也能避免 `Cannot create a JSON value from a string with CHARACTER SET 'binary'` 这类报错 |
| 2 | **不用 `${}`** | 与现有 `order` 的处理同一原则：所有值走 `#{}` 占位，注入面为零（`ESCAPE` 是字面量，不是拼串） |
| 3 | **`ESCAPE '\\'`** | 配合 Service 侧的 `%` / `_` / `\` 转义。不转义时用户输入一个 `%` 就等于匹配全部 |
| 4 | **`total` 自动跟随** | `countWrongBook` / `countFavoritePage` 用的是同一个 `<sql>` 片段，不需要改 —— 这正是「不能新开端点」的技术原因 |

> ⚠️ `wrongBookListFilters` 里已经有 `JOIN question q`（列表要 join 取题面），所以 `q.*` 列可直接引用，**不需要新增 join**。

### 2.5 已知限制（必须告知前端 / 产品）

| # | 限制 | 表现 | 处理 |
|---|---|---|---|
| 1 | **HTML 标签会阻断跨段匹配** | 题干已段落化（`<p>…</p><p>…</p>`），实测 132 题的题面含尖括号。搜「电流由铜电极流向银电极」能命中；搜跨两段的「正确的是以下有关」会因为中间夹 `</p><p>` 而搜不到 | 不剥离 HTML（剥 `REPLACE` 成本高且易漏）。**用户搜自然短语通常落在同一段内**，可接受 |
| 2 | **LaTeX 只认源码** | 选项里存的是 `$\\frac{10a}{b}$`，搜「分数」搜不到，搜 `frac` 能命中 | 不做 LaTeX 语义检索（需分词 / 公式识别）。产品文案建议写「搜索题目文字」，不要暗示能搜公式 |
| 3 | **单字符 / 单字母会放大命中** | 选项 JSON 原文是 `{"A": "石油分馏", ...}`，键名 `"A"`–`"D"` 与花括号引号都在被搜的字符串里 → 搜 `A` 几乎命中全部 | 属已知噪声。用户不会用单字母搜题；若产品介意，可加「`keyword` 长度 ≥ 2 时才纳入选项列」的动态分支（见 §9） |
| 4 | 不支持拼音 / 繁简 / 同义词 | 搜 `hanshu` 搜不到「函数」 | 需要分词与索引层支持，见 §2.6 扩展路径 |
| 5 | 不做分词 | 「函数图像」是一个完整子串，命中要求库里连续出现 | `LIKE` 的固有语义 |
| 6 | **宽度不敏感是「白捡的福利」，别当成保证** | 当前 `utf8mb4_0900_ai_ci` 下 `'（' = '('`、`'Ａ' = 'A'`，所以全角输入也能命中半角文本。但这依赖 collation —— 一旦某列改成 `utf8mb4_bin` / `_as_cs`，宽度变体立刻不再等价 | 后端已统一做全角转半角，不依赖这个副作用；换 collation 也不会退化（§2.2） |

### 2.6 性能评估

**实测数据量（TEST 库）**：

| 表 | 单用户最大行数 |
|---|---|
| `csca_question_wrong` | 244 |
| `csca_question_favorite` | 16 |

**执行计划预期**：

- `WHERE w.user_id = ? AND w.deleted = 0` → 走 `idx_user_time(user_id, deleted, updated_time)`（或 `uk_user_question` 前缀），先把驱动集**收敛到「本人几十~几百行」**；
- 再 `JOIN question q ON q.id = w.question_id`（主键等值，回表）；
- 最后在**这个几十~几百行的小结果集上**做三列 `LIKE '%kw%'`。

`LIKE '%kw%'` 本身用不了索引，但它作用在**已被前两步压小**的集合上 —— 这是本场景与「全表搜题库」的本质区别。按 244 行 × 3 列计算，单次过滤开销可忽略。

**不做的优化**（记录理由，避免后人重复讨论）：

| 方案 | 不做的原因 |
|---|---|
| 给 `q.passage` 建前缀索引 | 前缀索引对 `%kw%` 无效（左侧通配） |
| MySQL 8 `ngram` 全文索引 + `MATCH … AGAINST` | 可行，但要改表结构、加 DDL、且中文最小词长（`ngram_token_size` 默认 2）会让「单字搜索」失效；**当前数据量下收益为零**。留作将来题库级搜索的扩展路径 |
| 把题面同步到 ES | 同一理由，且引入新组件 |

### 2.7 与现有筛选 / 分页 / 排序的组合

`keyword` 是**并列的 AND 条件**，与科目 / 来源 / 语言 / 时间区间同时生效：

```
GET /csca/wrong-book?subjectTypeMapping=math&keyword=函数&page=2&pageSize=20&order=desc
```

三条红线不变：

1. **`total` 与分页必须同一套 where**（含 `keyword`）—— 否则前端会出现「total=30 但第 2 页是空数组」。本次改动只往共用的 `<sql>` 片段里加条件，天然满足。
2. **排序仍由后端做**，排序键恒为 `updated_time`，`keyword` 不影响排序。
3. **`total` 语义随筛选变化**：不传任何筛选时 `total` = 错题本角标数；**传了 `keyword` 后 `total` = 命中数**，不再是角标数 —— 前端角标应始终读回执里的 `wrongCount`（或列表不传筛选时的 `total`），不要用带 `keyword` 的 `total` 当角标。

---

## 3. 索引与 DDL

**本次无任何 DDL、无索引变更。**

| 操作 | 走的索引 | 是否够用 |
|---|---|---|
| 批量软删（`WHERE user_id AND question_id IN (…) AND deleted=0`） | `uk_user_question(user_id, question_id)` | ✅ 唯一键前缀精确命中 |
| 列表 + `keyword` | `idx_user_time(user_id, deleted, updated_time)` 驱动 + `question` 主键回表 | ✅ 数据量级下足够 |
| 计数 + `keyword` | 同上 | ✅ |

> ⚠️ PROD **仍未建** `csca_question_wrong` / `csca_question_favorite` 两张表（主文档 §3.6.1 / §3.6.2 已注明）。本次变更不改变这个前置条件，但上线前**必须**连同两张表一起建，否则新端点直接 `Table doesn't exist`。

---

## 4. 兼容性

| 场景 | 结果 |
|---|---|
| 老版本 App 调列表（不传 `keyword`） | 行为、返回体、`total` 口径**完全不变** |
| 老版本 App 调单题 `DELETE` | 完全不变（新端点与它并存） |
| 新版本 App 调批量端点 | 老服务不存在该端点 → 404，故**前端需按版本判断**或做容错降级（批量失败则退化为逐条 `DELETE`） |
| 响应体结构 | 列表响应体**零变更**（`keyword` 只是入参）；批量端点是新 DTO，不影响既有解析 |
| 网关 | 两个新路径 `/api/practice/csca/wrong-book/batch-remove`、`/api/practice/csca/favorites/batch-cancel` 属私有接口，**不加白名单**（与现有同前缀接口一致） |

---

## 5. 错误码汇总

沿用主文档 §0.5 的 8001–8099 号段，**不新增码**。

| code | 含义 | 触发点 |
|---|---|---|
| `401` | 未登录 / 非 APP | 全部 4 个端点 |
| `8005` `CSCA_PARAM_OUT_OF_RANGE` | 参数越界 | 批量：`questionIds` 空 / >100 / 元素非数字；搜索：`keyword` > 50 字符 |
| `8006` `CSCA_QUESTION_NOT_FOUND` | 题目不存在 | **仅单题 `DELETE` 保留**（批量不产生） |

---

## 6. 改动清单

| # | 文件 | 改动 | 估算 |
|---|---|---|---|
| 1 | 🆕 `dto/CscaBatchQuestionIdsRequest` | ✅ 两个批量端点**共用**的请求体：`questionIds: List<String>`（合并了原计划的 `CscaBatchRemoveRequest`，避免同一句「1–100 个、字符串式雪花 id」写两遍） | 新文件 |
| 2 | `dto/CscaBatchRemoveResponse` | 🆕 `requestedCount` / `removedCount` / `skippedCount` / `wrongCount` | 新文件 |
| 3 | `dto/CscaBatchCancelResponse` | 🆕 同上，末位改 `favoriteCount` | 新文件 |
| 4 | `dto/CscaWrongBookQuery` | 加 `keyword` 字段 + javadoc | 2 行 |
| 5 | `dto/CscaFavoriteQuery` | 加 `keyword` 字段 + javadoc | 2 行 |
| 6 | `support/CscaKeyword` | 🆕 归一化工具：全角转半角 → trim → 长度校验（50）→ 转义 `\` `%` `_` | 新文件 |
| 7 | `support/CscaRequestParams` | 🆕 `parseBatchQuestionIds(List<String>)`（空 / 非数字 / 去重保序 / 1–100）+ 常量 `MAX_BATCH_SIZE = 100` | +30 行 |
| 8 | `mapper/CscaWrongBookMapper` + XML | 🆕 `batchRemove`；`wrongBookListFilters` 加 `keyword` 三列 OR 分支；`selectWrongPage` / `countWrongBook` 加 `keyword` 形参 | +40 行 |
| 9 | `mapper/CscaFavoriteMapper` + XML | 🆕 `batchCancel`；`favoriteListFilters` 加 `keyword` 分支；`selectFavoritePage` / `countFavoritePage` 加 `keyword` 形参 | +40 行 |
| 10 | `service/CscaWrongBookService` + Impl | 🆕 `batchRemove(userId, questionIds)`；`list` 内解析 `keyword` | +45 行 |
| 11 | `service/CscaFavoriteService` + Impl | 🆕 `batchCancel(userId, questionIds)`；`list` 内解析 `keyword` | +40 行 |
| 12 | `controller/CscaWrongBookController` | 🆕 `POST /wrong-book/batch-remove`；`list` 加 `keyword` 入参 | +30 行 |
| 13 | `controller/CscaFavoriteController` | 🆕 `POST /favorites/batch-cancel`；`list` 加 `keyword` 入参 | +30 行 |
| 14 | 测试 | 🆕 `CscaKeywordTest`（8 例）+ `CscaRequestParamsTest` 补 5 例 + 两个 Mapper XML 契约测试补关键词/批量断言 + 两个 Service 单测补批量 6 例 | +19 例 |

---

## 7. 验收用例

| # | 用例 | 预期 |
|---|---|---|
| 1 | 批量移出 3 道在册错题 | `removedCount=3`、`skippedCount=0`、`wrongCount` 减 3 |
| 2 | 重复调同一批 | `removedCount=0`、`skippedCount=3`，HTTP 200 |
| 3 | 批量里混入别人的 questionId | 该条计入 `skippedCount`，**不动别人的数据** |
| 4 | `questionIds: []` | `8005` |
| 5 | 101 个 id | `8005` |
| 6 | id 传 `"abc"` | `8005`（整体失败，不做部分成功） |
| 7 | 批量取消收藏 2 条 | `removedCount=2`、`favoriteCount` 减 2 |
| 8 | 错题本 `keyword=函数` | 只回题干含「函数」的题；`total` = 命中数 |
| 9 | `keyword=（1）`（全角） | 与 `keyword=(1)`（半角）**结果相同**（验证全角转半角） |
| 10 | `keyword=%` | 命中 0 条（`%` 被转义成字面量，**不是**全量） |
| 11 | `keyword` 传 51 个字符 | `8005` |
| 12 | `keyword` 空白串 | 等同于不传（`total` = 角标数） |
| 13 | `keyword` + `subjectTypeMapping=math` + `pageSize=5` | 三个条件同时生效，`total` 与可翻页数一致 |
| 14 | 老参数组合（不传 `keyword`） | 与改造前逐字段一致 |

---

## 8. 定稿口径（2026-10-26 已确认）

| # | 问题 | 结论 |
|---|---|---|
| 1 | 独立 `search` 端点还是加 `keyword` 参数？ | ✅ **方案 A：列表加 `keyword`**。不新开端点 —— 分页 / 计数 / 题面装配 / 排序全部复用，`total` 自动等于命中数 |
| 2 | 批量上限 100 够不够？ | ✅ **100 足够**（= `pageSize` 上限），与 `CscaRequestParams.MAX_BATCH_SIZE` 一致 |
| 3 | 要不要「清空全部」？ | ✅ **不加**。错题本是复习资产，误操作代价太大；需要时由前端「分批全选」控制节奏 |
| 4 | 选项列（`option_content`）是否纳入搜索？ | ✅ **纳入**。否则「石油分馏」这类只出现在选项里的关键词搜不到。代价：搜单个字母会因选项 JSON 的 `"A"`–`"D"` 键名而放大命中（属已知噪声，用户不会用单字母搜题） |
| 5 | 搜索要不要搜题号？ | ✅ **不搜**。用户手上没有题号，且纯数字会与题干里的数字误撞 |

---

## 9. 主文档（`CSCA练习-接口设计文档.md`）同步点

定稿编码时，需在主文档同步以下位置（避免两份文档打架）：

| 位置 | 需同步内容 |
|---|---|
| §2.1 端点清单 | 新增 2 行：`POST /csca/wrong-book/batch-remove`、`POST /csca/favorites/batch-cancel` |
| §2.2 端点归属 | 两个新端点归入 §3.6 收藏与错题本 |
| §3.6.1 接口用处表 | 加「批量取消（多选态）」一行；入参表 `GET /csca/favorites` 加 `keyword` |
| §3.6.1 业务逻辑 | 新增「批量取消 = 纯 UPDATE 软删，不做准入、不写快照」条款 |
| §3.6.2 接口用处表 | 加「批量移出（多选态）」一行；入参表 `GET /csca/wrong-book` 加 `keyword` |
| §3.6.2 业务逻辑 | 新增「批量移出 7 步 + 为什么不用 upsert」条款；新增「搜索范围三列 + 全角转半角」条款 |
| §4.4 文档与实现的差异 | 记录本次 4 项变更与日期 |
| 文首「编码进度」 | 标为 ✅ 已编码（编码完成后） |

---

## 10. 附：为什么「批量删除」不能靠前端循环调单题接口

| 维度 | 循环单题 `DELETE` | 批量端点 |
|---|---|---|
| 请求数 | N 次 | 1 次 |
| 网络往返 | N × RTT（弱网下 N=50 会明显卡） | 1 × RTT |
| 部分失败 | 删到第 30 条断网 → **前 29 条已删、后 21 条没删**，前端无法回滚、状态不一致 | 单条 SQL，要么全生效要么全不生效 |
| 服务端成本 | N 次准入查询 + N 次 upsert | 1 条 UPDATE |
| 回执 | 每次一个 `wrongCount`，最终值取决于最后一次是否成功 | 一个确定的最终 `wrongCount` |

这是本次新开端点的核心理由 —— **不是"少写几行代码"，而是"要么全删要么全不删"的原子性**。

---

## 11. 编码落地记录（2026-10-26）

### 11.1 端点最终形态

| 方法 | 路径 | 入参 | 回执 |
|---|---|---|---|
| `GET` | `/api/practice/csca/wrong-book` | 原 8 个 + 🆕 `keyword` | 原结构（`total` 变命中数） |
| `GET` | `/api/practice/csca/favorites` | 原 9 个 + 🆕 `keyword` | 原结构 |
| `POST` | `/api/practice/csca/wrong-book/batch-remove` | body `{"questionIds":["…"]}` | `requestedCount` / `removedCount` / `skippedCount` / `wrongCount` |
| `POST` | `/api/practice/csca/favorites/batch-cancel` | 同上 | 同上，末位 `favoriteCount` |

### 11.2 实现中定下的三条不可逆约束

1. **`keyword` 只有一份归一化实现**（`support/CscaKeyword`）：全角转半角 → trim → 长度 50 → 转义 `\` `%` `_`。
   Controller 只原样透传、Service 调用它。🔴 转义顺序必须先 `\` 再 `%`/`_`（反了会把新加的转义符再转一遍）。
2. **`<if test="keyword != null">` 里三个 `OR` 必须包在 `AND ( … )` 内**：
   SQL 里 `AND` 优先级高于 `OR`，漏括号会变成
   `(w.user_id = ? AND w.deleted = 0 AND q.passage LIKE …) OR q.content …` —— **直接绕过用户隔离把别人的题搜出来**。
   两个 Mapper XML 契约测试各有一条断言专门守这个括号。
3. **批量写库只发一条 `UPDATE`**，`WHERE user_id = ? AND deleted = 0 AND question_id IN (…)`。
   `deleted = 0` 一个条件承担三件事：幂等（重复调 `affectedRows = 0`）、`removedCount` 准确、
   不刷新已软删行的 `updated_time`（否则「移出时间」会被重复调用不断推后）。

### 11.3 与 v1.0 设计的差异

| # | v1.0 设计 | 实际实现 | 原因 |
|---|---|---|---|
| 1 | 两个批量端点各一个请求 DTO（`CscaBatchRemoveRequest`） | 合并为 🆕 `CscaBatchQuestionIdsRequest` | 字段与校验完全一致，写两遍必然漂移（与两个列表共用 `CscaListParams` 同一理由） |
| 2 | 解析逻辑散在 Service 的 ②③④ 步 | 收敛到 `CscaRequestParams#parseBatchQuestionIds`，Controller 调用 | 与既有的「字符串参数在 Controller 解析、业务边界在 Service」分工一致；且两个 Controller 共用一份 |
| 3 | 搜索范围写「三列」 | 一致 | — |

### 11.4 验证

| 项 | 结果 |
|---|---|
| `mvn -pl practice-service -am compile -DskipTests` | ✅ 通过 |
| `mvn -pl practice-service -am test -Dtest='Csca*Test'` | ✅ **236 个用例全绿**（本次新增 23 例：`CscaKeywordTest` 8 / `CscaRequestParamsTest` +5 / 两个 XML 契约测试 +3 / 两个 Service 单测 +6 ... 含既有基线） |
| DDL / 索引 | 无变更（批量走 `uk_user_question`；搜索先用 `idx_user_time` 把驱动集压到本人几十~几百行再 LIKE） |
| TEST 库实跑 | ⚠️ **未做**（本次为纯代码 + 单测；接口级联调待起服务后验，验收用例见 §7 的 14 条） |

### 11.5 🔴 v1.0 被实测推翻的一个前提（重要）

v1.0 §2.2 写「导入链路强制全角转半角 → 库里存的是半角 → 不转就搜不到」。**这个前提是错的**，编码时在 TEST 库实测予以纠正：

| 实测项 | 结果 |
|---|---|
| `question` 表 collation | `utf8mb4_0900_ai_ci` —— **对宽度不敏感** |
| `'（' = '('`、`'Ａ' = 'A'`、`'１' = '1'`、`'％' = '%'`、`'＿' = '_'`、`'　' = ' '` | 全部 **为真**（`=` 与 `LIKE` 行为一致） |
| `passage` 含全角 `（` / 全角 `，` | **789 / 973 条**（说明库里并非「全是半角」） |
| `passage` 含 `。` / 含 `.` | **0 / 895 条**；且 `'。' = '.'` 为 **0（不等价）** |

**结论：** 全角转半角的价值不在「括号逗号字母数字」（那些本来就等价），而在：

1. **被导入链路改写成另一个字符的标点** —— `。`→`.`、`…`→`.`、`—`→`-`、`·`→`.`。这些不是宽度变体，collation 帮不上忙，用户打「。」不转换就是 **0 命中**；
2. **让转义不漏** —— `％` 要先变成 `%` 才轮到被转义成 `\%`（顺序：convert → escape）；
3. **不依赖 collation 的副作用** —— 一旦哪天某列改成 `utf8mb4_bin`，宽度不敏感就没了，而后端归一化仍在。

**转义的必要性也做了实测反证：**

| 输入 | 命中 |
|---|---|
| 未转义的 `%`（只在 `passage`） | **1644 条 = 全量**（`passage` 非空的题全被捞出来） |
| 已转义的 `\%` | 2 条 |
| 已转义的 `\_` | 506 条 |

「未转义 `%` = 全量」这一条足以说明：转义不是洁癖，是**正确性**。
