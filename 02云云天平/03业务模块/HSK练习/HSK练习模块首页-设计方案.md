# HSK 练习模块首页 · 设计方案

> 服务：`practice-service`（网关 `/api/practice`）· 关联文档：`docs/HSK练习接口-新增字段-前端对接.md`
> 依据：2026-10-27 新版练习页截图 + 当前代码基线
> 文档版本：v1.0 · 2026-10-27
> 状态：**待评审**（§9 有 6 个待拍板项）

---

## 0. 三句话结论

1. **截图里是 5 张卡，后端只有 4 个模块。** 第 5 张「翻译」在当前实现里**不是独立模块**，而是写作卷里的 `SEC_TRANSLATION` 部分（笔译并入写作、口译归口语，见 `PracticeSections`）。**这是整份方案的第一分叉点**，决定后端要不要动结构。
2. ~~建议翻译卡做成「视图层入口」~~ → **2026-10-27 决策更新：翻译改为独立模块**，新建 `/translation/**` 目录接口；详见 `docs/HSK翻译练习-独立模块接口方案.md`。其余 4 张卡仍全部复用现有接口、零改动。
3. **版本下拉是全局态，切换必须重置等级。** 且 HSK2.0 下「翻译」应置灰（HSK2.0 无翻译题），口语在 HSK2.0 / HSK3.0 是**两套完全不同的 `levelCode`**，不能沿用。

---

## 1. 界面结构拆解

截图自上而下 5 个区块，对应 4 层信息架构：

| 层 | 区块 | 内容 | 数据来源 |
|---|---|---|---|
| L0 | 状态栏 + 标题区 | `HSK 练习` / `专项突破 · 听力/阅读/写作/口语/翻译` / 右侧 2 个功能图标 | 纯前端（标题文案，副标题**应由模块配置生成**） |
| L1 | 三段 Tab | `HSK 练习` / `HSK 考试` / `HSKK 考试` | 前端路由，不请求接口 |
| L2 | 列表头 | `真题练习` + 右侧版本下拉 `HSK 3.0` | 版本 = 全局 `version` 参数 |
| L3 | 模块卡 ×5 | 听力 / 阅读 / 写作 / 翻译 / 口语 | **5 个模块各自的 `/levels`**（见 §3） |
| L4 | 底部 TabBar | 首页 / HSK / CSCA / 课程 / 我的 | 前端路由（CSCA 走 exam-service） |

点击卡片后的下钻层级（四跳）：

```
模块卡 → ① 等级选择 → ② 试卷列表 → ③ 板块(Parts)列表 → ④ 答题页
         /levels      /papers        /papers/{id}/parts
```

> ⚠️ **听力是例外**：没有 `/papers` 接口，`GET /listening/levels` **返回单对象**且内嵌 `papers[]`，即「等级选择」和「试卷列表」在同一个响应里。前端下钻只有三跳，卡片进度也直接从这一个接口算。

---

## 2. 卡片视觉与状态规范

### 2.1 设计 Token（按截图反推）

| 项 | 值 |
|---|---|
| 卡片圆角 | 16px；图标底 16px（56×56） |
| 卡片内边距 | 左右 16px，上下 16px；卡片间距 12px |
| 页面左右留白 | 16px |
| 主标题 | 17px / Semibold / `#1A1A1A` |
| 副标题 | 12px / Regular / `#9A9AA0`（**英文名，来自后端 `contentName` 的 en 分支**） |
| 右侧箭头 | chevron-right 16px / `#C7C7CC` |
| 模块主色 | 听力 `#5B6CF9` / 阅读 `#34C759` / 写作 `#FFB020` / 翻译 `#8B5CF6` / 口语 `#FF4D8D`（图标底色 = 主色 10% 透明度） |
| 角标 | `HOT` 红底 `#FF3B30` 白字 9px；`NEW` 橙底 `#FF9500` 白字 9px；圆角 6px，贴在标题右侧 |

### 2.2 卡片状态矩阵

| 状态 | 触发 | 表现 |
|---|---|---|
| 默认 | — | 白底、图标彩色、箭头灰 |
| 按下 | 触摸 | 卡片整体 `scale 0.98` + 浅灰底（`#F7F7FA`） |
| 未开放 | 该 `version` 下模块无数据（如 HSK2.0 的翻译） | 图标去色（灰度 100%）+ 标题 `#B0B0B5` + 无箭头 + **点击弹 Toast「HSK 2.0 暂无翻译练习」**，不跳转 |
| 加载中 | 首屏拉模块配置 | 骨架屏：5 个等高灰块（**不要转圈**，避免高度跳动） |
| 加载失败 | 接口异常 | 整块替换为「加载失败，点击重试」，其余区块不阻塞 |

> 🔴 **不要用「隐藏」代替「置灰」**：5 张卡高度固定，隐藏会让 5 卡变 4 卡、图标色块位置跳变，用户会以为功能丢了。置灰 + Toast 更稳。

---

## 3. 数据来源映射（核心）

### 3.1 现有接口盘点

| 模块 | 等级 | 试卷列表 | 板块 | 备注 |
|---|---|---|---|---|
| 听力 | `GET /listening/levels?levelCode&version` | **内嵌在 `/levels` 的 `papers[]`** | `GET /listening/papers/{paperId}/parts` | `/levels` 返**单对象**，非数组 |
| 阅读 | `GET /reading/levels?version` | `GET /reading/papers?levelCode&version` | `GET /reading/papers/{paperId}/parts` | `/levels` 返**数组**，`sections` 恒空 |
| 写作 | `GET /writing/levels?version` | `GET /writing/papers?levelCode&version` | `GET /writing/papers/{paperId}/parts` | 每 part 带 `sectionMapping` |
| 翻译 | ❌ 无 | ❌ 无 | ❌ 无 | 现为写作卷内 `SEC_TRANSLATION` 部分 |
| 口语 | `GET /speaking/levels?version` | `GET /speaking/papers?levelCode&version` | `GET /speaking/papers/{paperId}/parts` | 口语 HSK3.0 改造未完成 |

### 3.2 逐卡映射

**① 听力 / ② 阅读 / ③ 写作 / ⑤ 口语** —— 零后端改动，直接复用上表。卡片本身不需要请求（除非要做进度，见 §4.7）。

**④ 翻译（必须决策）**

> ⚠️ **2026-10-27 决策：走 T3 独立模块**（产品确认「翻译和其他部分分开写」）。下表保留作为决策依据；落地细节见 `docs/HSK翻译练习-独立模块接口方案.md`。T3 的真实代价不在接口，而在**数据只有 1 套卷 4 题、口译无目录行、口译无音频**。

| 方案 | 做法 | 后端改动 | 评价 |
|---|---|---|---|
| **T1 前端过滤**（P0 兜底） | 翻译卡 → 固定 `levelCode=HSK7-9` + `version=HSK3.0` → 调 `/writing/papers` → 进卷后调 `/parts`，前端只渲染 `sectionMapping === 'SEC_TRANSLATION'` 的 part | **0** | 能上线，但会出现「点进去某些卷没有翻译部分」的空卷，且 `/parts` 多传无用数据 |
| **T2 后端过滤**（✅ 推荐） | 上述链路 + 两个接口各加可选参数 `sectionMapping`（不传 = 原行为） | 2 个 `@RequestParam` + 2 条 XML `AND` 片段，HSK 全链路零影响 | 卷列表干净、空卷不露出；语义清晰 |
| **T3 独立模块**（不推荐） | 新建 `SEC_TRANSLATION` 独立模块、独立目录/进度/统计 | 目录派生、进度、报告、错题 5 条链路全改 | 题库重复、进度双份、统计口径分裂，且口译本来归口语 |

> **推荐 T2**。翻译不是「另一种题」，而是「同一张 HSK3.0 7-9 卷里的一个板块」，独立成模块会把「同一份试卷练了两次」算成两条进度。
>
> 附带约束：翻译题**复用写作答题/评分链路**（`WritingAnswer/Submission`），因此翻译卡进去的答题页与写作卡**是同一个页面**，只是板块过滤不同。若翻译评分尚未接入，答题页需显示「待评分」而不是「0 分」。

### 3.3 版本 × 模块 可用矩阵（设计必须落到这一张表）

| 模块 | HSK2.0（默认） | HSK3.0 | 卡片可用性规则 |
|---|---|---|---|
| 听力 | HSK1–6 | HSK1–6 + `HSK7-9` | 恒可用 |
| 阅读 | HSK1–6 | HSK1–6 + `HSK7-9` | 恒可用 |
| 写作 | HSK3–6（1/2 级 `enabled=0`） | HSK2–7 | 恒可用，等级列表由 `/levels` 决定 |
| 翻译 | — | **仅 `HSK7-9`** | `version=HSK2.0` 置灰；`HSK3.0` 直接跳过等级选择 |
| 口语 | HSKK 初/中/高（`HSKK_PRIMARY`/`INTERMEDIATE`/`ADVANCED`） | HSK3 / HSK4 / HSK5 / HSK6 / `HSK7-9` | 恒可用，**切版本必须重拉 `/levels`** |

---

## 4. 关键业务规则（8 条）

**4.1 版本是全局态，切版本 = 重置一切**
版本切换后必须：清空已选 `levelCode` → 重新拉 `/levels` → 清空试卷列表 → 重置滚动位置。否则用旧 `levelCode` 打 `/papers` 会吃 404（阅读/写作/口语的 `/intro` 与 `/papers` 传错版本均报 404）。

**4.2 版本取值严格大小写敏感**
只有 `HSK2.0`、`HSK3.0` 两个合法值，`hsk3.0` 查不到数据。前端下拉的 value 直接写这两个字面量，别用 `toLowerCase()`。

**4.3 HSK2.0 下不要写偏好**
`PUT /{module}/preferences/level` **不认 `version`**，底层表也没有 `version` 列。HSK3.0 下写偏好会污染 HSK2.0 的「上次练习」；HSK3.0 独有的 `HSK7-9` 直接 404。→ **规则：只有 `version=HSK2.0` 时调用偏好写接口**，HSK3.0 用本地存储兜「上次练到哪」。

**4.4 `HSK7-9` 是一个等级**
`levelCode='HSK7-9'`、`level` 数值为 `7`。等级选择器必须能渲染它，文案建议「HSK 七至九级」。🔴 前端**禁止**对 `levelCode` 做 `parseInt` 取数字（后端 `getLevel()` 已因此踩过 500）。

**4.5 `status` 枚举跨模块大小写不一致**
听力 `/levels`：`not_started` / `in_progress` / `completed`（小写）
阅读`/papers`、写作`/papers`：`NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`（大写）
→ 卡片进度条若要做，**先归一化**再判，否则「已练完」永远为 0。

**4.6 游客态（未登录）**
听力 `/levels` 只有带 `X-Client-Type: APP` 才回用户进度，否则 `status` 恒 `not_started`。→ 游客可见全部 5 张卡，但**卡片不展示进度**，点进答题页时再引导登录（与现有链路一致，不在首页拦）。

**4.7 卡片进度（建议加，非必须）**
截图现状：5 张卡没有任何「练到哪了」的痕迹，用户关掉 App 再回来无法续练。建议在卡片标题下行加一行灰度文案：
`已练 2/8 套 · 上次 第2部分`（数据取自各模块 `/levels` / `/papers` 的 `status` 聚合，听力直接用 `/levels`，其余需 4 次请求 → **这也是 §6 聚合接口的动机**）。
P0 可先只做「继续练习」角标：存在 `in_progress` 的卷就在右上角加一个小圆点。

**4.8 角标（HOT / NEW）不是文案，是运营位**
阅读的 `HOT`、翻译的 `NEW` 在截图里是硬编码位置的。建议 **P0 前端配置化**（一个 `modules.ts` 常量表），**P1 由 §6 聚合接口下发**（对应字段 `badge: "HOT" | "NEW" | null`），否则每次运营调整都要发版。

---

## 5. 交互流程与状态

```
[练习首页]
  ├─ 点 听力  → 等级选择(HSK1-6/HSK7-9) → 试卷列表(内嵌于 /levels) → 板块 → 答题
  ├─ 点 阅读  → 等级选择 → 试卷列表 → 板块 → 答题
  ├─ 点 写作  → 等级选择 → 试卷列表 → 板块(写作+笔译混排) → 答题
  ├─ 点 翻译  → (跳过等级，固定 HSK7-9) → 卷列表(sectionMapping=SEC_TRANSLATION) → 板块 → 答题
  └─ 点 口语  → 等级选择(随 version 变) → 试卷列表 → 板块 → 录音/评分
```

| 页面级状态 | 处理 |
|---|---|
| 首屏加载 | 5 个等高骨架卡，**不阻塞**标题区与 Tab |
| 接口全失败 | 卡片区整体「加载失败 / 重试」，重试只重拉失败模块 |
| 某模块 `/levels` 返回 `[]` | 该卡置灰，副标题替换为「该版本暂未开放」 |
| 某模块 `/intro` 或 `/papers` 404 | 下钻页显示空态「该等级暂未开放」，**不要白屏、不要 Toast 报错** |
| 网络超时 | 3s 超时 + 底部轻提示，不弹全屏错误 |

---

## 6. 接口改造建议

### 6.1 方案 A：纯前端（今天就能上，0 后端改动）

- 5 张卡 + 角标 + 顺序 + 副标题全部写在前端常量表。
- 翻译卡走 T1（前端过滤 `sectionMapping`）。
- 卡片进度不做（或只做本地缓存）。
- **代价**：首屏 4–5 个并发请求；运营改角标要发版；翻译卡会出现空卷；版本×可用性矩阵写死在客户端，后端调整等级开放范围后客户端要跟着发版。

### 6.2 方案 B：加一个聚合入口接口（✅ 推荐，1 天工作量）

```
GET /practice/hsk/modules?version=HSK3.0
```

响应（示意）：

```json
{
  "code": 200,
  "data": {
    "version": "HSK3.0",
    "modules": [
      {
        "code": "LISTENING",
        "sectionMapping": "SEC_LISTEN",
        "name": "听力",
        "nameEn": "Listening",
        "icon": "headphone",
        "theme": "blue",
        "badge": null,
        "available": true,
        "disabledReason": null,
        "entryLevelCode": null,
        "paper": { "totalPapers": 9, "completedPapers": 2, "inProgressPaperId": null, "lastPartName": "第2部分" }
      },
      {
        "code": "TRANSLATION",
        "sectionMapping": "SEC_TRANSLATION",
        "name": "翻译",
        "nameEn": "Translating",
        "icon": "translate",
        "theme": "purple",
        "badge": "NEW",
        "available": true,
        "disabledReason": null,
        "entryLevelCode": "HSK7-9"
      }
    ]
  }
}
```

配套改动清单：

| # | 改动 | 文件 | 风险 |
|---|---|---|---|
| 1 | 新增 `PracticeModuleCatalog` 常量（5 入口，翻译 → `SEC_TRANSLATION`） | `core/support/` | 无（纯常量） |
| 2 | 新增 `GET /practice/hsk/modules` | `core/controller/` 新 Controller | 无（新增端点） |
| 3 | `/writing/papers` 加 `sectionMapping` 可选参数 | `WritingCatalogController` + `WritingCatalogServiceImpl` + Mapper XML | 低（不传 = 原 SQL） |
| 4 | `/writing/papers/{paperId}/parts` 同参 | 同上 | 低 |
| 5 | 空翻译卷过滤（`translationCount=0` 不下发） | `WritingCatalogServiceImpl` | 低 |

> 🔴 **落地铁律**：参数必须**可为 null 且默认原行为**，不能改变现有 `/writing/papers` 的返回集合；HSK 老链路零影响。
> 🔴 新增端点 id 用 **String**（`practice-service` 无 Long→String 配置，`paperId` 是 19 位雪花，前端 `JSON.parse` 会丢末位精度，详见对接文档 §6.1）。

---

## 7. 埋点（按卡维度）

| 事件 | 参数 |
|---|---|
| `practice_module_click` | `module_code`、`version`、`available` |
| `practice_module_disabled_click` | `module_code`、`version`、`disabled_reason` |
| `practice_version_switch` | `from`、`to` |
| `practice_level_select` | `module_code`、`version`、`level_code` |

> `practice_module_disabled_click` 是用来判断「翻译该不该在 HSK2.0 露出」的唯一数据依据，别省。

---

## 8. 分期落地

| 期 | 内容 | 依赖 |
|---|---|---|
| **P0** | 5 卡 UI + 置灰规则 + 版本下拉 + 3 个 Tab；翻译走 T1 前端过滤；角标前端常量 | 无 |
| **P1** | 聚合接口 `GET /hsk/modules`；翻译走 T2 参数过滤；卡片进度 / 「继续练习」角标 | 后端 5 处改动 |
| **P2** | 角标后台可配（运营表）；口语 HSK3.0 口译接入；翻译评分接入 | 口语子系统改造 |

---

## 9. 风险与待确认（需要产品/后端拍板）

| # | 问题 | 建议 | 影响 |
|---|---|---|---|
| 1 | 翻译到底是**第 5 个模块**还是**写作下的入口**？ | 视图层入口（T2） | 决定要不要动目录派生/进度/统计 |
| 2 | HSK2.0 下翻译卡：置灰 or 隐藏？ | **置灰**（保持 5 卡布局稳定） | UI + 埋点 |
| 3 | HSK3.0 的「口语」是否包含七至九级的**口译**？ | 当前口译未接入口语子系统，先不含 | 口语卡等级范围 |
| 4 | 卡片是否展示进度？ | P1 做，P0 只做「继续」圆点 | 首屏请求数与聚合接口必要性 |
| 5 | `HOT`/`NEW` 角标是否要后台可配？ | P2 做，P0/P1 常量 | 运营发版成本 |
| 6 | 顶部三段 Tab 的「HSKK 考试」与练习页口语卡是否算同一入口？ | 明确区分：Tab 是**考试**（exam-service），口语卡是**练习** | 用户认知 |

---

## 附：与现有文档的关系

- 版本 `version` 入参、13 个接口的新增字段、ID 精度坑、偏好接口不支持 `version` → 见 `docs/HSK练习接口-新增字段-前端对接.md`（**本方案不重复，直接引用**）。
- 本方案**新增**的部分：模块入口聚合层、翻译入口的三种落地方式、卡片状态规范、版本×模块可用矩阵、埋点。
