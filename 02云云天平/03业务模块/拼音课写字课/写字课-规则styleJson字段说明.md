# 笔顺规则 `styleJson` 字段说明（前端）

> 适用接口：`GET /writing/catalog` → `data.ruleSections[].rows[].styleJson`
> 后端实现：`course_writing_rule.style_json`（JSON 列），服务端原样透传。

## 一、这个字段是干什么的

`styleJson` 描述**某一条规则行的「块级 / 例字样式」和「例字公式结构」**，与 `tags` 分工：

| 字段 | 管什么 | 例子 |
|---|---|---|
| `tags[]` | 离散的**徽章 / 提示文字**（贴在哪、什么色） | 「高频易错」红徽章、「先写点」灰提示 |
| `styleJson` | **这一行整块怎么上色、例字块怎么上色、例字是否按「公式」排列** | 整块浅粉、例字粉底红字、「日 + 月 → 明」 |

两者正交，**互不替代**。`tags` 控制的是「贴上去的小标签」，`styleJson` 控制的是「这行本身的视觉」。

## 二、核心约定（务必先记住这 3 条）

1. **键名固定、全部可缺省**：`styleJson` 顶层只可能出现 5 个键（`blockBg` / `descFg` / `charBg` / `charFg` / `formula`），**缺哪个键 = 那个位置用默认样式**。前端不要假设「有 styleJson 就一定有某键」，逐键判空。
2. **有值才下发**：整行用默认样式时，`styleJson` 键**直接不下发**（不是下发 `null` 或 `{}`）。前端 `row.styleJson == null` → 走默认渲染。
3. **颜色直存 hex、无 `#`**：如 `"FDECEC"`、`"D32F2F"`、`"FDF6F6"`、`"FFFFFF"`、`"6C727E"`、`"9CA3AF"`。前端自己拼 `#` 前缀。

## 三、字段详解

### 顶层键（`styleJson`）

| 键 | 类型 | 含义 | 缺省（键不存在时） |
|---|---|---|---|
| `blockBg` | String | 整块底色 | 白 / 卡片默认底 |
| `descFg` | String | 描述文字颜色 | 灰 `6C727E` |
| `charBg` | String | **例字块统一**底色 | 灰 `F5F6F8` |
| `charFg` | String | **例字统一**字色 | 黑 `111827` |
| `formula` | Array | 例字公式 token 流，见下 | 无 → 平铺 `examples` |

> `charBg` / `charFg` 是「整组例字统一」的样式。若某一行所有例字同底色同字色，就只填这两个键，不用逐字写。

### `formula[]`（公式 token 流）

**`formula` 有值时，前端按公式渲染例字，并忽略 `examples` 的平铺展示**（`examples` / `exampleCharIds` 仍会照常下发，供跳例字弹窗等其他用途，只是**不用它们做平铺排版**）。

每个 token 是一个对象：

| 键 | 谁有 | 类型 | 含义 |
|---|---|---|---|
| `t` | 都有 | String | `"CHAR"`（例字块）或 `"OP"`（连接符） |
| `charId` | 仅 `CHAR` | Long | 指向 `course_writing_char.id`，前端拿它查字格 / `guide_svg` / 跳例字弹窗 |
| `text` | 仅 `OP` | String | 连接符文字，如 `"+"`、`"→"` |
| `bg` | 都有 | String | **本 token 自己的**底色（可缺省） |
| `fg` | 都有 | String | **本 token 自己的**字色（可缺省） |

- `CHAR` 与 `OP` 互斥：`CHAR` 有 `charId` 无 `text`；`OP` 有 `text` 无 `charId`。
- `bg` / `fg` 缺省时：**继承该行的 `charBg` / `charFg`**，再缺才落到默认。
- `OP` 是纯符号，**不可点击、不可跳转**。

## 四、实际数据（当前库里三处）

### ① 点的位置区分·「先写点」（id 404）

```json
{ "charBg": "FDECEC", "charFg": "D32F2F" }
```

渲染：这一行**整组例字**（义/斗/头/为）粉底红字。无 `formula` → 平铺展示。

### ② 半包围·「左下包围」（id 407）

```json
{
  "blockBg": "FDF6F6",
  "descFg": "D32F2F",
  "charBg": "FFFFFF",
  "charFg": "D32F2F"
}
```

渲染：整块浅粉底、描述文字红色、例字白底红字（强调块）。

### ③ 多部件叠加（id 417）

```json
{
  "formula": [
    { "t": "CHAR", "charId": 119 },
    { "t": "OP", "text": "+" },
    { "t": "CHAR", "charId": 158 },
    { "t": "OP", "text": "→" },
    { "t": "CHAR", "charId": 318, "bg": "FDECEC", "fg": "D32F2F" }
  ]
}
```

渲染：`日 + 月 → 明`，其中「日」「月」用默认（灰底黑字）、「明」粉底红字高亮、`+`/`→` 灰色连接符。**不要**再按 `examples="日,月,明"` 平铺。

## 五、渲染决策树（前端伪代码）

```js
function renderRuleRow(row) {
  const s = row.styleJson;

  // 1. 无 styleJson → 全默认，平铺 examples
  if (!s) return renderDefault(row);

  // 2. 有 formula → 按公式渲染，忽略 examples 平铺
  if (s.formula && s.formula.length) {
    return renderFormula(s.formula, row.exampleCharIds);
  }

  // 3. 无 formula → 平铺 examples，应用 charBg/charFg 统一样式
  return renderExamples(row, {
    charBg: s.charBg,   // 缺省 undefined → 前端默认灰
    charFg: s.charFg,   // 缺省 undefined → 前端默认黑
  });
}
```

其中「默认样式」由前端视觉规范定义（灰底 `F5F6F8` / 黑字 `111827` / 描述灰 `6C727E` 等），后端只在「与默认不同」时下发覆盖值。

## 六、与 `tags` 的边界（别搞混）

- 想让一行**整块变强调色 / 例字变色 / 例字排成公式** → 用 `styleJson`。
- 想在一行上**贴一个「高频易错」「先写点」这类小徽章 / 灰字提示** → 用 `tags`（`style` / `position` / `bgColor` / `fgColor`）。

两者可以同时存在、互不影响（如 407 既在 `tags` 里有「极易错」琥珀徽章，又在 `styleJson` 里有整块浅粉底）。

## 七、兼容性承诺

- **旧前端**：`styleJson` 是新增键，旧代码不读它完全无影响（`examples` / `exampleCharIds` 照常下发、照常平铺）。
- **字段扩增**：以后若加新样式键（如某种新配色），只会**新增键名**，不会改现有 5 个键的语义。前端按「逐键判空 + 缺省兜底」写即可向前兼容。
