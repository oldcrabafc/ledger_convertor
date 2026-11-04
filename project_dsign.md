# 序时账清洗程序说明

## 1. 目标

这个程序的作用是把不同公司的 Excel 序时账清洗成统一的 Parquet 输出。  
核心思路不是直接依赖 Excel 原始字段，而是先把每家公司的源列映射到统一输出字段，再执行清洗和标准化。

## 2. 配置思路

程序使用 `config.toml` 作为主配置；`config.json` 文件可以保留，但程序不再读取它。  
推荐把人工维护的主配置放在 `config.toml`。

### 2.1 统一字段名做 `required_columns` 的 key

`required_columns` 现在以统一输出字段名作为 key，例如：

```toml
[required_columns.voucher_id]
source = "凭证编号"
dtype = "Utf8"
prefix = "v_"
```

含义是：

- `voucher_id` 是最终输出字段
- `source` 是 Excel 原始列名
- `dtype` 是输入列的目标类型
- `prefix` 是可选的值前缀规则

这样做的好处是，后续处理逻辑始终围绕统一字段展开，不会被不同公司的源列名绑死。

### 2.2 支持的字段类型

当前支持两种字段定义方式：

| kind | 场景 | 说明 |
|---|---|---|
| `single` | 单列字段 | 一列源字段直接映射到一个统一字段 |
| `right_neighbor` | 匿名相邻列 | 以某个已知列为锚点，取它右侧紧邻列作为匿名字段（当前仅用于 `vendor_name` / `customer_name`） |

### 2.3 借贷符号规则

`drcr` 配置用于描述借贷标识如何影响金额符号：

```toml
[drcr]
column = "drcr"
debit = "S"
credit = "H"
amount_columns = ["rc_amount", "lc_amount"]
```

含义：

- 借方行：金额保持正数
- 贷方行：金额转成负数
- `amount_columns` 中列出的金额列都会执行这个规则

## 3. 程序逻辑

### 3.1 读取和标准化

1. 读取 Excel
2. 把所有字符串列去首尾空格
3. 把空字符串转成 `null`

### 3.2 解析配置

程序会先读取配置，再把配置解析成内部字段定义：

- 统一输出字段
- 对应源列
- 类型
- 字段类型 `kind`
- 前缀规则

同时兼容旧配置：

- 旧版用 `columns`
- 新版用 `required_columns`
- 配置文件使用 `.toml`

### 3.3 解析源列

对每个字段：

- `single`：确认源列存在
- `right_neighbor`：确认锚点列存在，然后取右侧一列

### 3.4 类型转换

程序会先按配置把源列 cast 成目标类型，再生成统一输出列。

### 3.5 生成统一输出

将解析好的源列投影成最终字段集合，只保留配置中定义的字段。

### 3.6 应用前缀

如果某个字段配置了 `prefix`，会在非空值前面加前缀，例如：

- `A001` -> `ac_A001`

### 3.7 借贷处理

如果配置了 `drcr`：

1. 按借贷标识调整金额正负号
2. 删除金额全为 0 的行

## 4. 新公司接入方式

接入新公司的序时账时，一般只需要改配置，不需要改代码：

1. 写出统一字段名
2. 把 Excel 原始列名填到 `source`
3. 如果有匿名列，写 `right_neighbor`
4. 配好 `drcr`

## 5. 设计原则

- 配置描述“数据长什么样”
- 代码负责“怎么清洗”
- 最终输出字段必须统一
- 规则尽量显式，不靠猜测

## 6. 结果

当前程序已经可以支持：

- 不同公司不同列名
- 匿名相邻列
- 单金额列序时账
- 统一导出 Parquet

## 7. 最小重构蓝图（保持当前业务逻辑不变）

目标：在不改变现有业务行为的前提下，进一步简化配置解析与数据结构，降低后续维护成本。

### 7.1 数据结构收紧

建议将 `FieldSpec` 收紧为“窄类型”：

- `target: str`
- `source: str`
- `dtype: str`
- `kind: Literal["single", "right_neighbor"] = "single"`
- `prefix: str | None = None`

`PipelineConfig` 保持最小运行时集合：

- `field_specs: tuple[FieldSpec, ...]`
- `drcr: DrcrConfig | None`

说明：`prefix` 不再额外维护独立映射，继续由 `FieldSpec` 派生，减少重复状态。

### 7.2 配置处理流程固定为三步

1. `load_raw_config(path)`：读取 TOML 原始配置。  
2. `normalize_config(raw)`：补默认值（例如 `kind="single"`）、做轻量字符串规整（strip）。  
3. `validate_and_build(raw)`：严格校验后构建 `PipelineConfig`。  

这样每个阶段职责单一，报错定位和调试都更直接。

### 7.3 字段校验规则声明式化

将校验集中到统一入口（如 `validate_field_entry(target, entry)`），避免散落在多个分支里：

- `source` 必须是字符串
- `kind` 仅允许 `single` / `right_neighbor`
- `right_neighbor` 仅允许目标字段 `vendor_name` / `customer_name`

### 7.4 运行期解析逻辑最小化

`resolve_field_specs` 只保留两类行为：

- `single`：直接源列映射
- `right_neighbor`：基于锚点列取右邻列

不再保留 split 相关分支、校验与表达式生成逻辑。

### 7.5 错误模型统一（推荐）

建议统一为带路径的配置错误（例如 `ConfigError(path, message)`），错误路径精确到：

- `required_columns.vendor_name.kind`
- `required_columns.customer_name.source`

可显著降低排查时间。

### 7.6 低风险迁移顺序

1. 先收紧 `FieldSpec` 类型与 parser 输入约束。  
2. 将 `right_neighbor` 目标限制前置到配置校验阶段。  
3. 清理运行期残余的防御性分支。  

以上步骤按顺序实施，可在每一步保持可运行状态并降低回归风险。
