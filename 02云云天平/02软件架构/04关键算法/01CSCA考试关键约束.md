---
tags: [算法, CSCA, 考试]
project: 汉考宝
updated: 2026-11-03
---

# CSCA 考试关键约束

> CSCA 与 HSK 在 exam-service 里是**两套完全不同的实现**：CSCA 后端判分、三段事务、按 `recordId` 定位场次。
> 把 HSK 的做法套过来一定会错。本文只列「不知道就会写错」的约束。

## 一、能改不建

🔴 **不另起 `/csca/**` 端点**。19 个端点 = 改造 12 / 复用 6 / 停用 1，新增只有 2 个。

理由：CSCA 与 HSK 共用 `exam_record` / `exam_answer` / `exam_paper`，另起一套等于把双写和维护成本翻倍。

## 二、`start/csca` 必须三段事务

```
外层：无事务
 ├─ T1  REQUIRES_NEW：超时闭卷（把上一场 status=0 的按超时结算）
 └─ T2  REQUIRES_NEW：开新场（取卷 + 建 record + 建答题卡）
```

用 `TransactionTemplate` 手工划事务。🔴 **锁只能在 T2 加** —— 在 T1 之前加锁会与外层事务叠成死锁（报 `1205`）。

## 三、`/answer/submit/csca` 不加事务

单条答题落库，加事务只会拉长持锁时间。对照：HSK 的 `/answer/submit` 是 `@Transactional`（因为它还要更新分节计时）。

## 四、判分

- 归一化唯一实现 **`CscaAnswerGrader`** —— 不要在任何地方再写第二份比对逻辑，否则两处口径必然分叉；
- **续考落点唯一来源** `exam_record.current_question_number`；🔴 禁止整对象 `updateById`（会把其它字段覆盖成 null）。

## 五、接口访问控制（两派别混）

| 端点 | 是否校验归属 | 表现 |
|---|---|---|
| `/csca/{id}/report` | ✅ 校验 | 不属于本人 → 403 / 404 |
| `/csca/{id}/pdf` | ✅ 校验 | 同上 |
| `/csca/{id}/result` | ❌ 不校验 | — |
| 单题解析 | ❌ 不校验 | — |
| 🔴 `/answer/paper/tag` | ❌ **仍无归属校验** | **别当已修**，改这块时不要假设安全 |

## 六、`/result` 的状态闸门

🔴 未交卷（`status=0`）调 `/result` → 返回 **8111**。原因：`/result` 的题卡带答案，交卷前不该给。

答题行必须用 `selectByExamRecordId`（**不带 `user_id`**）—— 同一卷可以有多场会话，带 `user_id` 会跨场次串数据。

## 七、时长对外一律封顶

库里 `exam_record.duration` 含**超时懒闭卷**的时长（用户关掉 App 后时间还在跑）。
对外展示一律走 `capCscaDuration`。🔴 不要为了"数据好看"去改历史 `duration`，那是审计依据。

## 八、值域（调用/写库前必看）

| 参数 | 只认 | 传错 |
|---|---|---|
| `languageVersion` | `chinese` / `english` | 卷是 chinese 却传 english → 0 题 → **8004**（PROD 31 张卷全是 chinese） |
| 科目 | 5 个原始码 | 拿 `chinese` 当科目码 → **8001** |

## 九、与 HSK 的差异速查

| 维度 | HSK | CSCA |
|---|---|---|
| 定位场次 | `paperId + userId + status=0` | `recordId`（必传） |
| 判分 | **前端判**，后端存 `isCorrect` | **后端判** `CscaAnswerGrader` |
| 下发 `answer` | 下发（判分要用） | **恒 null**（只在报告接口出现） |
| 开考事务 | 单事务 | 三段（T1 闭卷 / T2 开考） |
| 次数 | 免费次数（1~2 级）+ 点数 | 免费次数（不走点数） |
| 题目来源 | `question` | **必须用 `CscaQuestionMapper`**（`subject_type_mapping` 1,904 行全 NULL） |

## 十、相关文档

- [[00HSK取卷与判分]] —— 对照看
- [[00字段红线索引]] —— `duration` / `current_question_number` 等字段
- [[CSCA-考试]] —— 需求层（做什么）
