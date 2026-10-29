# Git 提交与分支规范

标签：\#代码规范 \#Git

更新时间：2026\.09\.23

# 一、功能/场景简述

统一 Git 提交信息格式与分支模型，保证项目提交历史清晰、可追溯，便于 Code Review、版本回溯和自动生成变更日志。所有项目统一执行，一人写也行，协作更必须。

# 二、提交信息规范（Conventional Commits）

## 提交格式

```git
<type>(<scope>): <subject>

<body>（可选，说明原因）

<footer>（可选，如 BREAKING CHANGE、关联 issue）
```

## type 类型对照

|type|含义|示例|
|---|---|---|
|**feat**|新功能|feat: 新增登录接口|
|**fix**|修复 Bug|fix: 修复分页越界问题|
|**docs**|文档变更|docs: 更新 README|
|**style**|格式（不影响逻辑）|style: 统一缩进|
|**refactor**|重构（不改功能）|refactor: 抽取公共方法|
|**test**|测试相关|test: 补充单测|
|**chore**|构建/依赖等杂项|chore: 升级依赖版本|
|**perf**|性能优化|perf: 优化查询速度|
|**build**|构建系统/外部依赖|build: 调整打包配置|
|**ci**|CI 配置|ci: 增加 lint 检查|
|**revert**|回滚|revert: 回滚上一提交|

## subject 写作要求

- 首字母小写（中英文混合团队可全中文，但要一致）

- 祈使语气、简洁，控制在 50 字符内

- 不用句号结尾

- 一次提交只做一件事，不夹杂无关改动

## 破坏性变更

```git
feat!: 重构认证逻辑

```

或：在 footer 里写 `BREAKING CHANGE: 描述`。

# 三、分支规范（分支模型）

## 常驻分支

- **main / master**：生产主分支，始终可发布，禁止直接提交，只接受合并。

- **develop**：开发集成分支，日常开发的主干（小项目可仅用 main）。

## 临时分支

|分支前缀|用途|示例|
|---|---|---|
|**feature/**|新功能|feature/user\-login|
|**fix/**|修复 Bug|fix/pagination\-bug|
|**hotfix/**|线上紧急修复（从 main 拉出）|hotfix/crash\-on\-launch|
|**release/**|发版准备|release/v1\.2\.0|
|**docs/**|文档|docs/readme\-update|

## 命名规则

- 分支名用 kebab\-case（小写 \+ 连字符），不包含中文和空格。

- 命名格式：`类型/简短描述`，描述写功能或问题，不写人名。

# 四、提交规范 \& 工作流建议

1. 开发前从 develop 拉新分支：`git checkout -b feature/xxx`

2. 完成并自测后提交，提交信息按上文格式书写。

3. 推送到远端并发起 Merge Request / Pull Request，填清楚描述。

4. 合并到 develop 后，必要时删除临时分支，保持仓库整洁。

5. 发版时从 develop 拉 release 分支，验证后合并进 main 并打 tag。

## 版本号规范

使用语义化版本 `MAJOR.MINOR.PATCH`：破坏性变更升 MAJOR，新功能升 MINOR，Bug 修复升 PATCH。发版时用 `git tag vX.Y.Z` 打标签。

# 五、关键要点 \& 易错提醒

- **禁止**直接向 main / master 提交，只能合并，避免污染生产分支。

- 提交信息类型要写对，尤其 feat / fix 别混用，影响变更日志自动生成。

- 一条提交只改一类问题，别把格式化改动和新功能混在一起，review 困难。

- 本地 commit 前先 `git status` 确认没带上无关文件（如 \.env、临时文件）。

- 临时分支用完后删除，避免长期残留。

- 合并冲突先在本地解决再推送，不要直接强推覆盖他人分支。

# 六、总结（可选）

规范的价值在长期一致性：提交信息清晰可回溯，分支模型让开发、发版、热修复各走各路互不干扰。小项目可精简为「main \+ feature/fix」，保持灵活但格式不放松。

