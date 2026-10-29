# CSCA 邀请与考试次数 · 接口变更文档

> 版本：v1.0 ｜ 2026-10-25
> 影响服务：**auth-service（改造）**、exam-service（**不改代码**，仅行为随数据变化）
> 相关文档：《CSCA 考试 · 接口设计文档》（§0.4 错误码 8101–8199）

---

## 0. 决策记录

| # | 决策 | 取值 |
|---|---|---|
| 1 | 注册赠送 | 新用户 CSCA **5 个科目各 1 次**（`total=1 / used=0 / remain=1`） |
| 2 | 邀请奖励 | 每成功邀请 1 人，邀请人 CSCA **5 个科目各 +1 次** |
| 3 | 邀请上限 | 每人最多 **2 次**有效邀请（沿用 `user_invitation_code.reward_limit` 默认值 2，不改列） |
| 4 | 单科上限 | `1 + 2 = 3` 次 |
| 5 | 生效范围 | **只改 CSCA**；HSK / HSKK 注册仍 2 次、邀请仍只 +1 行 `remain`，一行不动 |
| 6 | 存量数据 | 上线前需一次性补 CSCA 五行（见 §8，**P0 阻断项**） |

**次数公式（CSCA 单科）**

```
remain = 1（注册赠送） + min(有效邀请人数, 2) − 该科已考次数
上限   = 3
```

> 🔴 `remain` 是唯一判定依据：`GET /record/csca/quota` 的 `hasQuota`、`POST /answer/start/csca` 的 `8105`
> 都只看 `remain_quota > 0`。`total_quota / used_quota` 仅作展示。

---

## 1. 背景：为什么必须改

| # | 现状问题 | 后果 |
|---|---|---|
| 1 | `AppUserService#initNewUserExamQuota` 只建 **HSK + HSKK 两行**，不建 CSCA 行 | 新用户一进 CSCA → `GET /record/csca/quota` 全 0 → 开考恒 `8105` |
| 2 | 邀请发奖 SQL 的 `version` **硬编码 `HSK2.0`**（`InvitationCodeService:218`），而 CSCA 配额行 `version='CSCA'` | 发奖 update 影响 **0 行**，只打 warn；但 `rewarded_count` 已 +1、绑定已标「已发放」→ **假成功**，2 次后 `isMax=true`，额度被永久吃掉 |
| 3 | `handleInvitationOnRegister` 注释声明「由调用方统一事务管理」，但 `register` / `smsRegister` **都没有 `@Transactional`** | 绑定、发次数、累加计数是 3 次独立提交，中途失败会留下半截数据 |
| 4 | `GET /app/invitation/getCode` 的 `examType` 是裸 `@RequestParam`，**无白名单** | 任意字符串都能建码（TEST 里 `examType='CSCA'` 的码就是这么来的，属于「凑巧能用」） |

---

## 2. 数据模型

### 2.1 CSCA 配额行（`user_exam_quota`）

一人 5 行，`exam_type / version / level` 三者共同定位一行：

| user_id | exam_type | version | level | total_quota | used_quota | remain_quota | status | deleted |
|---|---|---|---|---|---|---|---|---|
| 2113… | `CSCA` | `CSCA` | `arts_chinese` | 1 | 0 | 1 | 1 | 0 |
| 2113… | `CSCA` | `CSCA` | `science_chinese` | 1 | 0 | 1 | 1 | 0 |
| 2113… | `CSCA` | `CSCA` | `math` | 1 | 0 | 1 | 1 | 0 |
| 2113… | `CSCA` | `CSCA` | `physics` | 1 | 0 | 1 | 1 | 0 |
| 2113… | `CSCA` | `CSCA` | `chemistry` | 1 | 0 | 1 | 1 | 0 |

- 科目码唯一真源：`common/.../enums/CSCASubjectType`（5 值，**别用它的 `values()` 顺序**，声明顺序是化学打头的；`GET /record/csca/quota` 的顺序是 arts→science→math→physics→chemistry）
- 🔴 唯一键 `uk_user_exam_type_level = (user_id, exam_type, version, level, deleted)`。**`deleted` 在唯一键里** → 软删过的行不会与新建行冲突，会另插一行，属预期

### 2.2 邀请相关表（结构不变）

| 表 | 本次改动 |
|---|---|
| `user_invitation_code` | 无。`reward_limit` 默认 2 已满足「最多邀请两人」 |
| `user_invitation_binding` | 无。`reward_status` 列注释已含 `3-发放失败` |

**`reward_status` 枚举（本次正式启用 3）**

| 值 | 含义 |
|---|---|
| 0 | 待发放（绑定成功但未处理完，正常事务内不会停留） |
| 1 | 已发放 |
| 2 | 已达上限不发放（仅记录邀请数据） |
| **3** | **发放失败（配额行异常，需重试/人工补）** |

---

## 3. 接口清单

| # | 方法 | 路径 | 类型 | 改动要点 |
|---|---|---|---|---|
| 1 | GET | `/api/auth/app/invitation/getCode` | 🔧 改造 | 返回新增 3 个字段；`examType` 加白名单 |
| 2 | GET | `/api/auth/app/invitation/records` | ✅ 不变 | 仅口径补注（`rewardQuota` 语义） |
| 3 | POST | `/api/auth/app/register` | 🔧 行为改造 | 注册后补建 CSCA 5 行；邀请发奖修正 |
| 4 | POST | `/api/auth/app/smsRegister` | 🔧 行为改造 | 同上 |
| 5 | GET | `/api/exam/record/csca/quota` | ✅ 不改 | 返回值随数据自动变化（0 → 1） |
| 6 | POST | `/api/exam/answer/start/csca` | ✅ 不改 | `8105` 判定不变，只是不再全员命中 |
| 7 | GET | `/api/auth/app/profile/check` | ✅ 不改 | `8104`（资料）与 `8105`（次数）互不影响 |

> 入参/出参**没有任何破坏性变更**：只新增字段、只改服务端落库行为。老版本 App 不需强制升级。

---

## 4. 接口详述

### 4.1 GET /api/auth/app/invitation/getCode 🔧

**用途**：邀请人进入「邀请好友」页，取自己的专属邀请码与奖励进度。

**入参**

| 位置 | 参数 | 必填 | 说明 |
|---|---|---|---|
| query | `examType` | 是 | `HSK` / `HSKK` / `CSCA`。🆕 **白名单校验**，其它值 → `400` |
| header | `X-Client-Type` | 否 | 缺省时取默认用户 |

**返回**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "invitationCode": "BDDSC",
    "examType": "CSCA",
    "rewardedCount": 0,
    "rewardLimit": 2,
    "remainRewardCount": 2,
    "rewardPerInvite": 1,
    "rewardSubjectCount": 5,
    "isMax": false
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `invitationCode` | String | 5 位 `A-Z0-9`，全局唯一，长期有效 |
| `examType` | String | 回显，归一为大写 |
| `rewardedCount` | Integer | 已发放奖励次数（0..`rewardLimit`） |
| `rewardLimit` | Integer | 上限，默认 2 |
| `remainRewardCount` | Integer | 🆕 `rewardLimit − rewardedCount`，前端直接展示「还可邀请 N 人」 |
| `rewardPerInvite` | Integer | 🆕 每次邀请给「每个科目」加几次，恒 `1` |
| `rewardSubjectCount` | Integer | 🆕 本次奖励覆盖几个科目：`CSCA=5`、`HSK/HSKK=1`。前端文案：`每邀请 1 人，5 个科目各 +1 次` |
| `isMax` | Boolean | `rewardedCount >= rewardLimit` |

**约束**

- 每个用户 × 每个 `examType` 只有一个码（`uk_user_exam_type`），不存在才生成；生成后不变、不过期
- 达到上限后仍可继续邀请，只是奖励落 `reward_status=2`，`isMax=true`
- 新增字段全部可空兼容，老前端忽略即可

**错误码**

| 码 | 场景 |
|---|---|
| 400 | `examType` 缺失 / 不在 `HSK`、`HSKK`、`CSCA` |
| 401 | 未登录 |

---

### 4.2 GET /api/auth/app/invitation/records ✅

入参出参**不变**。仅补口径：

- `rewardQuota`：本次邀请发放的次数。CSCA 下这是「每个科目各 1 次」的单科数，实际入账 5 行
- `rewardStatus`：见 §2.2 枚举（`3` 为本期开始可能出现的新值，前端需能展示「发放失败」）
- `createTime`：绑定时间（毫秒）

---

### 4.3 POST /api/auth/app/register（邮箱注册）🔧

**入参不变**（`RegisterRequest`，`invitationCode` 仍为可选）。

**服务端行为变化**

| 顺序 | 现在 | 改后 |
|---|---|---|
| 1 | 校验 → 插 `user` | 不变 |
| 2 | `initOrInheritExamQuota`：新用户只建 HSK + HSKK 各 1 行（各 2 次） | 🆕 额外建 **CSCA 5 行**（各 1 次）；HSK/HSKK 保持 2 次 |
| 3 | `handleInvitationOnRegister`（无事务） | 🆕 加 `@Transactional`；发奖前先发次数、成功后才累加 `rewardedCount` |

**CSCA 5 行的初始值**

```sql
INSERT INTO user_exam_quota
  (user_id, exam_type, version, level, total_quota, used_quota, remain_quota,
   status, deleted, created_time, updated_time)
VALUES
  (?, 'CSCA', 'CSCA', 'arts_chinese',    1, 0, 1, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'science_chinese', 1, 0, 1, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'math',            1, 0, 1, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'physics',         1, 0, 1, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'chemistry',       1, 0, 1, 1, 0, ?, ?);
```

**约束**

- 注销重注册走 `userCancelHistory` 的配额快照继承，**不补 CSCA 行**（继承什么就是什么）
- 注册接口**永不因为邀请码失败而失败**：码无效 / 已绑 / 已达上限 / 发奖异常，一律只记日志 + `reward_status`，正常返回「注册成功」

**错误码**：不新增（沿用现有 500/400 体系）

---

### 4.4 POST /api/auth/app/smsRegister 🔧

行为与 §4.3 完全一致（同一 `register` 链路），此处不重复。

> ⚠️ 注意：`Facebook` / `Zalo` 注册**不支持邀请码**（没有该入参），本次保持不变。

---

### 4.5 GET /api/exam/record/csca/quota ✅（不改代码）

新用户（注册完、未考、未邀请）：

```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "quotas": [
      { "subjectType": "arts_chinese",    "subjectTypeText": "文科中文", "totalQuota": 1, "usedQuota": 0, "remainQuota": 1, "hasQuota": true },
      { "subjectType": "science_chinese", "subjectTypeText": "理科中文", "totalQuota": 1, "usedQuota": 0, "remainQuota": 1, "hasQuota": true },
      { "subjectType": "math",            "subjectTypeText": "数学",     "totalQuota": 1, "usedQuota": 0, "remainQuota": 1, "hasQuota": true },
      { "subjectType": "physics",         "subjectTypeText": "物理",     "totalQuota": 1, "usedQuota": 0, "remainQuota": 1, "hasQuota": true },
      { "subjectType": "chemistry",       "subjectTypeText": "化学",     "totalQuota": 1, "usedQuota": 0, "remainQuota": 1, "hasQuota": true }
    ],
    "totalRemainQuota": 5
  }
}
```

邀请满 2 人后：每科 `totalQuota=3 / remainQuota=3`，`totalRemainQuota=15`。

**约束**

- 接口本身零改动；`totalQuota` 语义从「不可信」变为可信（只有 CSCA 新数据自洽；HSK 老数据仍存在 `remain ≠ total-used`）
- 缺行的科目补 0、`hasQuota=false`（存量未补数时即为全 0）

---

### 4.6 POST /api/exam/answer/start/csca ✅（不改代码）

- 次数判断仍是 4 参重载（带 `level`）+ `decrementQuota(id)`，`remain>0` 守卫
- 单科 `remain=0` → `8105`
- 变化只在于：**以前每个用户都是 0（全员 8105），改后新用户每科 1 次起**

---

## 5. 发奖算法（`handleInvitationOnRegister`）

```
① 空码 → 跳过
② 手机号/邮箱命中 user_cancel_history → 跳过（注销重注册不算新用户）
③ 码不存在 / status≠1 → 跳过
④ 邀请人 == 被邀请人 → 跳过
⑤ 被邀请人已有绑定（uk_invitee_user_id）→ 跳过
⑥ 插 binding（reward_status=0）
⑦ 发次数（先做，且必须在累加计数之前）
     CSCA  → 五行 UPSERT（见下）
     HSK/HSKK → 单行 UPDATE remain_quota = remain_quota + 1（保持现状，不动 total）
   影响行数 = 0 → binding.reward_status = 3，记 ERROR 日志，返回
⑧ 累加 rewardedCount（条件更新 rewarded_count < reward_limit）
   影响行数 = 0 → binding.reward_status = 2（并发已到上限）
   影响行数 = 1 → binding.reward_status = 1 + rewarded_time
```

**CSCA 五行 UPSERT**

```sql
INSERT INTO user_exam_quota
  (user_id, exam_type, version, level, total_quota, used_quota, remain_quota,
   status, deleted, created_time, updated_time)
VALUES
  (?, 'CSCA', 'CSCA', 'arts_chinese',    2, 0, 2, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'science_chinese', 2, 0, 2, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'math',            2, 0, 2, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'physics',         2, 0, 2, 1, 0, ?, ?),
  (?, 'CSCA', 'CSCA', 'chemistry',       2, 0, 2, 1, 0, ?, ?)
ON DUPLICATE KEY UPDATE
  total_quota  = total_quota  + 1,
  remain_quota = remain_quota + 1,
  updated_time = VALUES(updated_time);
```

> 新行给 `2/2` 而不是 `1/1`：**「行不存在」等价于「这个用户的注册赠送还没发过」**，本次一并补上（注册赠送 1 + 邀请 1）。
> 已有行命中 `ON DUPLICATE` → `+1/+1`。
> 🔴 由此，存量用户即使漏跑补数脚本，被邀请时也能拿到正确次数，不会出现「奖励发不出去」。

**🔴 三条硬约束**

1. **先次数、后计数**。顺序反了就是现在这个 bug 的形状：计数 +1 了、次数没到账
2. `handleInvitationOnRegister` 必须加 `@Transactional(rollbackFor = Exception.class)`（独立 Bean，代理生效）；异常在方法内 `catch` 后写 `reward_status=3` 并**正常返回**，保证「绑定了但没发到」这条记录能留存、可人工补
3. `version` 按 `examType` 映射，**禁止再硬编码**：

| `examType` | `user_exam_quota.exam_type` | `version` | 命中行数 |
|---|---|---|---|
| `HSK` | `HSK` | `HSK2.0` | 1 |
| `HSKK` | `HSKK` | `HSK2.0` | 1 |
| `CSCA` | `CSCA` | `CSCA` | **5** |

---

## 6. 错误码 / 状态码

| 码 | 归属 | 场景 |
|---|---|---|
| 400 | auth | `examType` 不在白名单（本次新增） |
| 401 | auth | 未登录 |
| 200 | auth | 邀请码无效 / 已绑定 / 已达上限，注册仍成功（**不报错**） |
| `reward_status=3` | 数据 | 发次数失败，需人工补（本期新增实际使用） |
| 8105 | exam | 该科 `remain=0`，开考被拒（不变） |
| 8104 | exam | 资料不全（与次数无关，不变） |

---

## 7. 前端需要跟进的点

| # | 场景 | 说明 |
|---|---|---|
| 1 | 邀请页文案 | `每邀请 1 人，5 个科目各 +1 次，最多 2 人`；用 `rewardPerInvite` × `rewardSubjectCount` 拼，别硬编码 |
| 2 | 邀请进度 | 优先用 `remainRewardCount`，或 `rewardedCount / rewardLimit` |
| 3 | 邀请记录 | `rewardStatus=3` 要有兜底展示（「发放失败，已记录」），别当未知值渲染成空白 |
| 4 | 次数角标 | `GET /record/csca/quota`，每科 1 起步；`hasQuota=false` 时置灰 |
| 5 | 兼容 | 老 App 不读新字段即可，无强制升级 |

---

## 8. 存量数据（🚨 上线前置，P0）

PROD 现状：`user_exam_quota` 中 `exam_type='CSCA'` **0 行** → 修完代码后**所有存量用户仍然无法开考**（`8105`）。

**一次性补数（幂等，可重复执行）**

```sql
-- G1/G2 先验：SELECT DATABASE(), @@hostname;
INSERT INTO user_exam_quota
  (user_id, exam_type, version, level, total_quota, used_quota, remain_quota,
   status, deleted, created_time, updated_time)
SELECT u.id, 'CSCA', 'CSCA', s.level, 1, 0, 1, 1, 0,
       UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000
FROM `user` u
JOIN (
  SELECT 'arts_chinese' AS level UNION ALL
  SELECT 'science_chinese'     UNION ALL
  SELECT 'math'                UNION ALL
  SELECT 'physics'             UNION ALL
  SELECT 'chemistry'
) s
WHERE u.deleted = 0
ON DUPLICATE KEY UPDATE user_exam_quota.id = user_exam_quota.id;   -- 已有行原样保留（不给已用完的老用户补发）
```

> 🔴 **`id = id` 必须带表名**：`INSERT ... SELECT` 的 SELECT 侧 `FROM user u` 也有 `id` 列，
> 裸写 `ON DUPLICATE KEY UPDATE id = id` 会直接报 **1052 Column 'id' in field list is ambiguous**。
> （TEST 已实测，见 `tmp/_backfill_csca_quota.py`。）

**执行要求（按项目五闸门）**

| 闸门 | 要求 |
|---|---|
| G1 / G2 | 打印 `DATABASE()` / `@@hostname` 确认环境（TEST `787e3b0c860c` / PROD `4a4fc6ac22b0`） |
| G3 | 先 `mysqldump` 备份 `user_exam_quota` + 准备回滚 SQL（按本次 `created_time` 删除） |
| G4 | 事务内回读：`SELECT level, COUNT(*) FROM user_exam_quota WHERE exam_type='CSCA' AND deleted=0 GROUP BY level` 应为 5 行且行数 = 用户数 |
| G5 | 幂等：`ON DUPLICATE KEY UPDATE user_exam_quota.id = user_exam_quota.id`（🔴 必须带表名，见上）；重跑行数不变 |
| 默认 | 先 `DRY-RUN` 只 `SELECT` 统计目标行数，人工确认后再 `--apply` |

> 若产品决定**不给存量用户补**（只让新注册用户有次数），也必须让运营明确知晓：现有用户进 CSCA 一律 `8105`，
> 且没有「后台发次数」的功能（全仓无此代码），只能跑上述 SQL。

**执行状态**

| 环境 | 状态 | 说明 |
|---|---|---|
| TEST | ✅ 已完成（2026-10-25） | 27 个有效用户，补 131 行；CSCA 共 135 行 = 27×5，每用户恰好 5 行，幂等复跑 0 行。脚本 `tmp/_backfill_csca_quota.py` |
| PROD | ⛔ 未执行 | 仍是 0 行；执行前把脚本 `DB` 换成 PROD 配置（无 ssl）、`EXPECT_HOSTNAME` 换 `4a4fc6ac22b0` |

> ✅ **邀请码本身不需要补数**：码是**懒生成**（`getOrCreateInvitationCode` 查不到就建），用户进「邀请好友」页时自动创建，
> `rewarded_count=0 / reward_limit=2` 即为正确初值。且「没有码」等价于「从来没被邀请成功过」
> （`user_invitation_binding` 一定挂在某个码上），不存在历史奖励丢失。
> 因此本次上线**只有配额行需要补**，本文档 §9 的变更清单里也不含邀请码补数。

---

## 9. 变更清单（文件级）

| 文件 | 改动 |
|---|---|
| `auth-service/service/AppUserService.java` | `initNewUserExamQuota` 追加 CSCA 5 行（用 `CSCASubjectType` 取科目码，不硬编码字符串） |
| `auth-service/service/InvitationCodeService.java` | `getOrCreateInvitationCode`：examType 白名单 + 3 个新字段；`handleInvitationOnRegister`：加 `@Transactional`、`version` 按类型映射、先次数后计数、异常写 3；🆕 `rewardInviterQuota(code)`、`resolveQuotaVersion(examType)` |
| `auth-service/dto/InvitationCodeVO.java` | 🆕 `remainRewardCount` / `rewardPerInvite` / `rewardSubjectCount` |
| `auth-service/mapper/UserExamQuotaMapper.java`(+`.xml`) | 🆕 `initCscaQuota(userId)`（5 行批量插入）、🆕 `rewardCscaQuota(userId)`（5 行 UPSERT） |
| `auth-service/constant/…` | 🆕 `CSCA_EXAM_TYPE = "CSCA"`、`CSCA_QUOTA_VERSION = "CSCA"`（与 exam-service 的 `CSCA_QUOTA_VERSION` 同名同值） |
| `exam-service/**` | **不改代码** |
| `common/.../enums/CSCASubjectType.java` | 不改（5 值齐全）；🔴 只是**不要依赖 `values()` 顺序** |

---

## 10. 验收用例

| # | 场景 | 预期 |
|---|---|---|
| 1 | 新用户邮箱注册（不带邀请码） | 建 5 行 CSCA，`total=1/remain=1`；`quota` 接口 5 科各 1，`totalRemainQuota=5` |
| 2 | 新用户短信注册 | 同上 |
| 3 | 新用户带有效邀请码注册 | 被邀请人 5 行不变；**邀请人 5 行各 +1**（`total=2/remain=2`）；`binding.reward_status=1`；`rewarded_count=1` |
| 4 | 邀请第 2 人 | 邀请人 5 行 `=3/3`；`rewarded_count=2`；`isMax=true` |
| 5 | 邀请第 3 人 | 绑定照建、`reward_status=2`；次数不再增加；`rewarded_count` 仍 2 |
| 6 | 同一被邀请人换码重复注册 | 第二次注册失败（手机号/邮箱已存在），不产生绑定 |
| 7 | 被邀请人注销后重新注册并填码 | 命中 `user_cancel_history` → 不绑定、不发奖 |
| 8 | 填自己手机号对应的码 | 跳过绑定 |
| 9 | 某科考完 3 次后再开 | `8105`（该科 `remain=0`，其它科不受影响） |
| 10 | 存量用户（未跑补数）被邀请 | UPSERT 建 5 行 `2/2` → 能开考 2 次 |
| 11 | 邀请接口传 `examType=ABC` | `400` |
| 12 | 邀请接口传 `examType=CSCA`（老用户已有 `BDDSC`） | `200`，返回原码，不新建 |

---

## 11. 待确认

| # | 事项 | 当前方案 |
|---|---|---|
| 1 | 存量用户是否补 5 行 | 建议补（§8），否则上线后存量用户全 `8105` |
| 2 | 被邀请人是否要「先注册后填码」的绑定入口 | 不做（现状只有注册时填），后续如需要另开接口 |
| 3 | 邀请记录是否需要展示「+5 科」明细 | 不做，`rewardQuota=1` + 前端文案说明 |
| 4 | HSK/HSKK 是否也统一成「每科 1 次」 | 本期不改 |
