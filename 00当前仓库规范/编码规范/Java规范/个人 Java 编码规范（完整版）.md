# 个人 Java 编码规范（完整版）

**说明：**融合基础层格式规范与进阶层业务规约，适合日常项目直接对照。

---

# 一、命名规范（最常用）

## 通用原则

- 见名知意，**拒绝缩写**（除公认缩写：id、url、dao、dto），不要拼音、不要无意义 a/b/c/tmp1

- 禁止纯拼音、中英文混合命名，必须使用完整英文单词

## 命名风格（强制）

1. 命名不能以下划线、$ 开头或结尾，禁止 \_name、$obj、name\_。

2. 类名：大驼峰 UpperCamelCase；DO/BO/DTO/VO 统一大写缩写，例：UserDO、HtmlDTO。

3. 方法、变量：小驼峰 lowerCamelCase；包名全小写，单数形式。

4. 常量：全大写，下划线分隔，语义完整，例：MAX\_STOCK\_COUNT。

5. POJO 布尔属性**禁止加 is 前缀**：用 deleted，不要 isDeleted，避免序列化丢失字段。

6. 异常类必须以 Exception 结尾；测试类以 Test 结尾。

## 命名示例

```java
// good
private Integer maxContinuousDay;
public List<User> queryUserList(){}

// bad
private Integer mcd;
public List<User> qUser(){}
```

```java
public class ContinuousRecordDTO {}
interface UserRepository {}

public static final Integer DEFAULT_PAGE_SIZE = 10;
package com.xxx.service;
```

## 禁止项

- 一个名字同时干两件事

- 名字加类型后缀冗余：userInfoDTO 没问题，但 userDtoObj 多余

- 布尔变量：推荐用 isSuccess / hasPermission / enableFlag，一眼看懂是真假

---

# 二、常量与魔法值（强制）

1. 禁止魔法值，数值、字符串全部抽为常量或枚举。

2. long 常量必须使用大写 L，防止误判：1000L，不要 1000l。

3. 多个常量归类到同一个常量类，不要零散定义。

固定业务码、状态码统一放常量类 / 枚举（优先枚举，有描述）。

```java
// bad
if (type == 3) {}

// good
public static final Integer TYPE_SLEEP = 3;
if (type == TYPE_SLEEP) {}
```

---

# 三、代码格式（强制）

1. 单个方法代码行数（不含注释）≤80行；超长逻辑拆分为子方法。

2. 大括号左括号紧跟语句，右括号单独起一行；IDEA 统一格式化。

3. 缩进统一 4 空格，禁止 Tab；import 按顺序分组，清理无用导入。

4. 方法入参过多时，换行对齐，保证排版整齐。

5. 一行只写一条语句；一行代码不要太长，建议不超 120 字符（阿里是 80，现在很多项目放宽到 120）。

6. 空行规则：

    - 方法和方法之间空一行

    - 成员变量、常量块之间空一行

    - 逻辑块之间（一段查询、一段组装数据）空一行分隔

    - 不要连续空 2 行以上

```java
// good
if (status == 1) {
    doSomething();
}

// bad
if (status ==1)
{
    doSomething();
}
```

> ✅ 关键：不要手动调空格换行！开启 IDE 保存自动格式化（IDEA：Reformat code on save；VSCode：formatOnSave），从根源避免排版混乱。
> 
> 

---

# 四、OOP 面向对象规约（强制）

1. 重写 equals 必须同时重写 hashCode；自定义对象作为 Map 键、Set 元素必须重写这两个方法。

2. POJO 实体属性全部使用**包装类型（Integer/Long/Boolean）**，禁止基本类型，防止 NPE；不要给 POJO 字段设置默认值。

3. 严格控制访问权限：成员变量一律 private；仅子类使用的成员设为 protected；工具类必须私有化构造器，禁止无参 public 构造。

4. 禁止使用已废弃（@Deprecated）的类与方法。

5. 接口方法不加 public 修饰，保持简洁；接口只定义契约，不写业务逻辑。

---

# 五、集合处理（强制）

1. 判断集合空：使用 isEmpty\(\)，不要 size\(\)==0。

2. 集合转数组必须用 toArray\(T\[\] array\)，指定对应类型数组，避免类型转换异常。

3. 遍历集合时，禁止在循环内新增/删除元素；如需修改，使用迭代器。

4. HashMap 初始化尽量指定初始容量，避免频繁扩容。

5. 不要在 foreach 循环里进行元素 remove 操作。

---

# 六、控制语句（强制）

1. 优先使用**提前 return**，减少嵌套 if，代码扁平化。

2. 禁止多层嵌套（if 嵌套不超过 3 层）；复杂分支拆成独立方法。

3. 三目运算符只用于简单赋值，不要嵌套多层三目运算。

4. switch 语句必须写 default 分支；case 结尾必须 break。

---

# 七、日期时间（强制）

1. SimpleDateFormat 不能定义为 static 静态变量，线程不安全；改用 DateTimeFormatter。

2. 时间存储统一用 datetime，不要用 timestamp；时区统一为东八区。

---

# 八、注释规范

## 三类注释，各司其职

### 1\. 类/接口/枚举注释（Javadoc）

说明这个类是干嘛的，适用场景，核心职责。

```java
/**
 * 打卡记录DTO
 * 用于前端展示打卡项目、连续天数、打卡人信息
 */
@Data
public class CheckRecordDTO {}
```

### 2\. 方法注释

复杂方法写；简单 get/set 不用写！写明入参含义、返回值、异常、业务约束。

### 3\. 行内注释 //

**只写【为什么这么写】，不要写代码在干什么。**

```java
// good：为什么
// 这里不能直接删除记录，需要保留历史用于连续天数统计
recordMapper.updateDelFlag(id);

// bad：描述代码（代码本身已经能看懂）
// 更新delFlag字段
recordMapper.updateDelFlag(id);
```

## 注释规约（强制）

1. 类、公共方法必须写 Javadoc 注释，写明业务用途、入参、出参、异常。

2. 枚举每个枚举值必须加注释。

3. 注释只写业务意图，不要重复翻译代码；不要大量行内注释。

4. 代码修改后同步更新注释，杜绝注释与代码不一致。

> 原则：好代码优先做到自解释，注释是补充，不是翻译代码。
> 
> 

---

# 九、代码结构规范（解决代码臃肿、冗余的痛点）

## 1\. 方法要短，单一职责

一个方法**只做一件事**，长度尽量控制在 50 行以内。

- 如果里面出现两段完全独立逻辑 → 抽成私有方法

- 超长 if 嵌套、if\-else 瀑布 → 重构：策略模式、枚举、提前 return

```java
if (record == null) {
    return null;
}
if (!record.getEnable()) {
    return Collections.emptyList();
}
// 业务逻辑...
```

## 2\. 分层职责严格分开（后端最常用）

- **Controller：**接收参数、参数校验、组装返回、捕获异常

- **Service：**业务逻辑、事务、规则判断

- **Mapper/DAO：**只做数据库读写

> 禁止：Controller 写 SQL、Service 里面直接拼装返回给前端的 VO、Mapper 里写复杂业务判断。
> 
> 

## 3\. 变量作用域最小化

不要在类顶部一次性定义一堆变量；变量在哪里用，就在哪里声明。

```java
public void calcContinuous() {
    LocalDate lastDate = record.getCheckDate();
    ...
}
```

## 4\. 命名之外的「坏味道」约束

1. 不要重复复制粘贴相同逻辑 → 抽公共工具方法/组件

2. 参数不要太多：方法参数超过 4 个，优先封装成 DTO

3. 避免深嵌套：if 套 if 套 if，超过 3 层就要警惕重构

4. 不要一个大类几千行，大类拆分，按领域拆分

5. 集合返回：接口返回集合，不要返回 null，优先 Collections\.emptyList\(\)，减少前端判空

---

# 十、异常规约（强制）

## 异常处理

1. 禁止裸捕获 catch\(Exception\)，不要吞掉异常不打印日志；捕获具体异常。

2. 禁止用异常做正常业务判断，异常只处理意外场景。

3. 自定义业务异常，区分业务异常与系统异常；统一抛出异常，不要层层 try\-catch。

4. 资源（流、连接、锁）必须自动释放，优先使用 try\-with\-resources。

5. 异常日志打印：要带上业务标识（id、单号），方便排查。

---

# 十一、日志规范（强制）

1. 禁止使用 System\.out 打印，统一使用 SLF4J 日志。

2. 严格区分日志级别：debug 调试、info 正常业务、warn 告警、error 系统错误。

3. 打印日志必须携带业务 ID（订单 ID、用户 ID），方便排查问题。

4. 手机号、身份证、银行卡等敏感信息必须脱敏输出。

5. 错误码统一枚举，正常返回固定值 00000，错误码可快速定位问题。

6. 日志上下文埋点、MDC 使用规范。

---

# 十二、入参校验规范

- 参数校验位置：Controller 层校验（JSR380：@NotBlank、@NotNull 等）

- 校验失败返回统一错误码，不要直接抛原生异常给前端

- 入参、出参边界校验：长度、范围、枚举值

---

# 十三、MySQL 数据库规约（后端重中之重，强制）

## 1\. 建表规范

1. 每张表必须包含三字段：id（bigint 无符号自增主键）、create\_time、update\_time，类型为 datetime。

2. 小数金额类型统一使用 decimal，禁止 float、double，避免精度丢失。

3. 禁止使用外键、级联更新，所有关联逻辑在代码层处理。

4. 表名、字段名小写，下划线分隔，禁止驼峰；字段名不要保留关键字。

5. 布尔字段用 tinyint\(1\)；不要用 bit。

## 2\. SQL 编写规范

1. 禁止 select \*，只查询需要的字段。

2. 禁止在 where 条件上对字段做函数运算，避免索引失效（隐式转换）。

3. 分页必须用 limit，禁止一次性查出全量数据；大分页用游标分页。

4. 禁止在 for 循环内执行 SQL 查询，杜绝 N\+1 问题。

5. 事务尽量短小，禁止大事务；不要在事务里执行网络请求。

6. 索引优先建立在 where、order by、group by 字段；单表索引不超过 6 个。

---

# 十四、并发、线程、资源规范

- 线程池不要直接 new Thread，统一使用自定义线程池，禁止 Executors 直接创建线程池

- 流、连接、锁资源必须释放（try\-with\-resources）

- 共享可变变量的线程安全

- 不要随便用 static 存业务数据，多线程环境会出现数据错乱

---

# 十五、返回值与错误码统一规范

- 统一返回包装体 Result\<T\>

- 错误码全局枚举，含义固定，不重复

- 集合返回约定：优先空集合而不是 null

---

# 十六、单元测试规约（强制）

1. 单元测试必须覆盖正常场景、边界值、异常场景。

2. 测试用例不能依赖数据库、外部接口；做好数据隔离，执行后自动回滚。

3. 单元测试方法命名规范：test\_方法名\_场景。

---

# 十七、安全编码规约（强制）

1. 禁止直接拼接 SQL 字符串，必须使用参数绑定，防止 SQL 注入。

2. 所有前端传入参数必须做校验：长度、范围、枚举值、特殊字符过滤。

3. 禁止信任前端传来的权限、ID 等参数，后端二次校验。

4. 防 XSS：前端输入内容做转义；禁止直接把用户输入渲染到页面。

5. 反序列化禁止接收不可控对象，防止反序列化漏洞。

---

# 十八、工程规约（强制）

1. 分层严格：Controller 只做参数接收、转发；Service 处理业务；Mapper 只做数据库操作。

2. 分层对象严格区分：DO（数据库实体）、DTO（入参）、VO（出参）、BO（业务对象），不要混用。

3. 统一返回包装体 Result\<T\>；集合返回优先返回空集合，不要返回 null。

4. 禁止在静态变量里存放业务数据，多线程环境会出现数据错乱。

5. 线程池不要直接 new Thread，统一使用自定义线程池，禁止 Executors 直接创建线程池。

---

# 十九、设计规约（强制）

1. 接口入参必须做边界校验，防止超大分页、恶意参数导致 OOM。

2. 接口幂等性设计，防止重复请求造成数据重复。

3. 分布式场景禁止依赖本地事务，使用可靠消息、TCC 等分布式事务方案。

---

# 二十、校验工具与落地流程

## 校验工具（自动化检查，比肉眼靠谱）

- **Java：**IDEA 自带 Inspection \+ **Alibaba Java Coding Guidelines（P3C）插件**，实时扫描强制规范

- **格式化配置：**阿里规范 xml，一键统一空格、换行、缩进

- **代码质量扫描：**SonarLint，修复空指针、资源未关闭等代码坏味道

> 流程：写代码 → 保存自动格式化 → SonarLint 实时标红不规范地方 → 修复。
> 
> 

## 极简落地流程（个人开发直接照这个来）

1. 导入规范插件（Alibaba \+ SonarLint）

2. 配置 IDE 保存自动格式化

3. 新建类、方法，先想名字，保证见名知意

4. 写的时候控制方法长度，复杂逻辑抽小方法、提前 return

5. 魔法值抽常量/枚举

6. 注释只写业务意图，不翻译代码

7. 写完扫一遍 SonarLint，处理警告

---

# 参考资料

阿里 Java 开发手册（官方）：[https://alibaba\.github\.io/Alibaba\-Java\-Coding\-Guidelines/](https://alibaba.github.io/Alibaba-Java-Coding-Guidelines/)

