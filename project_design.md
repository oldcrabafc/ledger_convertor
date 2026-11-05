# 序时账转换项目设计文档

## 1. 项目目标

本项目用于将不同客户、不同集团的 Excel 序时账转换为 Parquet 文件，供后续审计分析和数据处理使用。

项目需要解决以下问题：

- 同一集团内不同公司的账套字段设置基本一致。
- 不同集团之间的字段名称、金额字段和业务规则可能不同。
- 每个集团需要保留自己的账套字段结构，不强制合并为一套跨集团业务模型。
- 转换逻辑应尽可能配置化，减少新增客户时的代码修改。
- 转换结果需要保留原始来源信息，方便审计追溯。

项目暂不包含 DuckDB 查询层，Parquet 文件是当前阶段的最终输出格式。

## 2. 设计原则

### 2.1 集团内统一，集团间独立

每个集团维护自己的字段配置和转换规则：

```text
集团 A 输入 -> 集团 A Parquet
集团 B 输入 -> 集团 B Parquet
集团 C 输入 -> 集团 C Parquet
```

集团 A 的 `account_code` 不需要和集团 B 的 `科目编码` 对齐。项目只保证同一集团内的字段结构和处理逻辑稳定。

### 2.2 配置描述差异，代码实现通用动作

以下内容优先放入配置文件：

- 源列名
- 输出列名
- 数据类型
- 日期格式
- 金额列
- 借贷标识
- 借贷金额处理规则
- 前向填充字段
- 作废、结转记录过滤规则
- 必填字段

以下内容可以通过 Python Adapter 实现：

- 多行表头
- 合并单元格结构
- 跨行拼接
- 非常规金额结构
- 复杂科目拆分
- 配置无法表达的特殊业务规则

### 2.3 保留审计追溯信息

除集团自己的业务字段外，建议统一增加以下元数据字段：

```text
_source_file
_source_sheet
_source_row
_group
_company
_conversion_time
_config_version
```

这些字段用于定位原始 Excel 文件和原始行，不参与集团业务字段统一。

## 3. 总体流程

```text
Excel 原始文件
    |
    v
首次读取 Excel 并缓存 Pickle
    |
    v
后续运行直接读取 Pickle
    |
    v
加载集团配置
    |
    v
集团专属字段清洗
    |
    v
类型转换与金额处理
    |
    v
记录过滤和质量检查
    |
    v
增加来源元数据
    |
    v
输出 Parquet
```

推荐由一个统一入口执行：

```bash
python -m ledger.cli \
  --config configs/group_a.toml \
  --input input.xlsx \
  --output output/group_a/company_001/ledger_2025.parquet
```

## 4. 项目目录建议

```text
ledger_convertor/
  ledger/
    __init__.py
    cache.py              # Excel -> Pickle，以及 Pickle 输入读取
    config.py             # TOML 配置读取和校验
    transforms.py         # Pandas 通用转换函数
    validation.py         # 数据质量检查和报告
    pipeline.py           # Pipeline 编排
    cli.py                # 命令行入口

  configs/
    group_a.toml
    group_b.toml

  ref/                    # 历史代码，仅供参考，不参与运行

  output/
  reports/
```

如果某个集团只需要普通字段映射，不需要单独 Adapter，直接使用配置驱动的通用流程即可。

## 5. 集团配置设计

每个集团一份配置文件，配置版本随字段变化递增。

示例：

```toml
[group]
name = "集团A"
version = "v1"

[input]
sheet_name = "序时账"
header_row = 0

[fields]

[fields.voucher_id]
source = "凭证编号"
dtype = "string"
required = true

[fields.posting_date]
source = "过账日期"
dtype = "datetime"
required = true

[fields.account_code]
source = "总账科目"
dtype = "string"
required = true

[fields.account_name]
source = "总账科目名称"
dtype = "string"

[fields.description]
source = "摘要"
dtype = "string"

[fields.amount]
source = "本位币金额"
dtype = "decimal"
required = true

[processing]
fill_forward = ["日期", "凭证编号", "摘要"]
remove_voided = true
remove_closing = true

[drcr]
column = "借贷标识"
debit_values = ["借", "S"]
credit_values = ["贷", "H"]
amount_columns = ["本位币金额"]

[validation]
required_columns = ["凭证编号", "过账日期", "本位币金额"]
allow_unknown_drcr = false
```

另一个集团可以使用完全不同的字段：

```toml
[fields.voucher_no]
source = "Voucher No"
dtype = "string"

[fields.account]
source = "G/L Account"
dtype = "string"

[fields.local_amount]
source = "Local Amount"
dtype = "decimal"
```

两份配置不需要使用相同的逻辑字段名称。

## 6. Pandas 转换层

项目统一使用 Pandas `DataFrame`，不使用 Polars。

建议提取以下公共函数：

```python
normalize_column_names()
trim_string_columns()
convert_date_columns()
convert_amount_columns()
fill_forward_columns()
apply_drcr_sign()
remove_zero_amount_rows()
remove_voided_records()
remove_closing_records()
validate_required_columns()
add_source_metadata()
```

函数不应写死某个集团的列名，而应通过参数接收列名：

```python
df = apply_drcr_sign(
    df,
    drcr_column="借贷标识",
    debit_values=["借"],
    credit_values=["贷"],
    amount_columns=["本币金额"],
)
```

不同集团只需要传入不同配置。

## 7. Pipeline 接口

推荐统一入口如下：

```python
def run_pipeline(
    input_file: str,
    output_file: str,
    config_file: str,
) -> None:
    config = load_config(config_file)
    df = read_input(input_file, config)
    df = apply_group_transforms(df, config)
    validate_dataframe(df, config)
    df = add_source_metadata(df, input_file, config)
    df.to_parquet(output_file, index=False)
```

## 7.1 缓存优先输入策略

Excel 文件只在以下情况被读取：

- 对应 Pickle 缓存不存在。
- Excel 文件更新时间晚于 Pickle 缓存。
- 使用 `--refresh-cache` 显式要求刷新缓存。

如果输入本身是 `.pkl` 或 `.pickle`，Pipeline 直接读取，不再访问 Excel。

默认缓存文件与 Excel 同目录同名：

```text
ledger_2025.xlsx -> ledger_2025.pkl
```

也可以通过命令行指定缓存位置。

## 7.2 命令行示例

```bash
python -m ledger.cli \
  --config configs/group_a.toml \
  --input D:/data/ledger_2025.xlsx \
  --output output/group_a/company_001/ledger_2025.parquet \
  --report reports/group_a_2025.json
```

强制从 Excel 重新生成 Pickle：

```bash
python -m ledger.cli \
  --config configs/group_a.toml \
  --input D:/data/ledger_2025.xlsx \
  --output output/group_a/company_001/ledger_2025.parquet \
  --refresh-cache
```

处理失败时应明确区分：

- 配置错误：缺少配置字段、配置格式错误。
- 输入错误：文件不存在、Sheet 不存在、缺少必要源列。
- 数据错误：日期或金额无法转换、借贷标识未知。
- 输出错误：目标目录不可写、Parquet 依赖缺失。

## 8. 特殊集团 Adapter

当配置无法表达某集团的复杂结构时，使用独立 Adapter：

```python
class GroupBAdapter:
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.expand_merged_headers(df)
        df = self.combine_voucher_rows(df)
        df = self.convert_special_amounts(df)
        return df
```

Adapter 仍然应输出该集团定义的字段结构，不能将特殊逻辑散落到通用 Pipeline 中。

## 9. Parquet 输出

建议按集团、公司和期间组织输出目录：

```text
output/
  group_a/
    company_001/
      ledger_2025.parquet
    company_002/
      ledger_2025.parquet
  group_b/
    company_101/
      ledger_2025.parquet
```

同一集团内的文件应保持：

- 字段名称一致
- 字段顺序一致
- 字段类型一致
- 金额单位一致
- 日期类型一致

不同集团之间允许存在字段名称和字段集合差异。

金额字段应尽量使用明确精度的数值类型。若使用浮点数，应在配置和文档中明确精度规则，并在转换时统一小数位。

## 10. 数据质量检查

每次转换都应生成一份质量报告，例如：

```text
集团：集团A
配置版本：v1
输入文件：ledger_2025.xlsx

输入行数：1,245,890
输出行数：1,245,770
删除结转记录：80
删除作废记录：20
金额转换失败：12
日期转换失败：5
未知借贷标识：0
必填字段为空：3
```

无法正常转换的记录建议保存到单独文件：

```text
reports/
  group_a_ledger_2025_quality.json
  group_a_ledger_2025_errors.csv
```

错误记录至少包含：

- 原始行号
- 原始字段值
- 错误类型
- 错误描述

## 11. 配置版本和可追溯性

当集团字段发生变化时，不直接覆盖旧配置，新增配置版本：

```text
configs/group_a_v1.toml
configs/group_a_v2.toml
```

每个 Parquet 输出都应记录 `config_version`。这样可以回答：

- 文件由哪份配置生成。
- 使用了哪个转换版本。
- 输入文件是什么。
- 哪些记录被过滤。
- 哪些记录转换失败。

## 12. 实施步骤

1. 盘点每个集团的输入文件、字段、金额列和借贷规则。
2. 为每个集团建立独立配置文件。
3. 把当前脚本中的公共 Pandas 逻辑提取到转换模块。
4. 将 `ledger_pipeline.py` 改造成配置驱动的 Pandas Pipeline。
5. 为复杂集团实现独立 Adapter。
6. 统一 Parquet 输出路径和文件命名规则。
7. 增加每个集团的最小样本和转换检查。
8. 增加质量报告和错误记录输出。
9. 验证同一集团内不同公司的结果结构一致。
10. 删除或停用 Polars 和 DuckDB 查询层相关代码。

## 13. 推荐的最终形态

```text
一个 Pandas Pipeline
    + 每个集团一份配置
    + 复杂集团独立 Adapter
    + 集团内字段结构稳定
    + 集团间保留字段差异
    + Parquet 作为最终输出
    + 质量报告和来源追溯信息
```

该方案适合当前的审计数据转换场景：新增同集团公司时主要复用现有配置；集团字段发生变化时新增配置版本；只有复杂业务规则才需要增加代码。

## 14. 后续 Pipeline 应包含的处理模块

根据当前三个集团转换程序中的已有逻辑，后续 Pipeline 可以拆分为以下处理模块：

```text
1. 输入读取
2. 字段名清洗
3. 字段映射和重命名
4. 合并单元格前向填充
5. 字符串清洗
6. 日期转换
7. 金额转换
8. 借贷方向处理
9. 凭证编号生成
10. 科目层级提取
11. 作废凭证过滤
12. 结转记录过滤
13. 零金额记录过滤
14. 数据质量检查
15. 增加来源信息
16. 输出 Parquet
```

### 14.1 输入读取

负责读取 Excel、Pickle 等来源文件，并根据集团配置选择：

- 文件类型
- Excel 工作表
- 表头行
- 数据起始行
- 输入编码

### 14.2 字段名清洗

对原始字段名执行统一的基础清洗，例如：

- 去除前后空格
- 统一大小写（仅适用于英文列名）
- 替换空格或特殊分隔符
- 处理重复列名

字段名清洗规则应由集团配置决定，避免破坏中文字段名称。

### 14.3 字段映射和重命名

将集团源字段映射到该集团自己的输出字段。不同集团允许使用不同的输出字段名称和字段集合。

支持的映射方式包括：

- 单字段映射
- 字段重命名
- 右侧相邻匿名列映射
- 多个源字段合并
- 根据条件选择源字段

### 14.4 合并单元格前向填充

对因 Excel 合并单元格产生的空值进行前向填充，例如：

- 日期
- 凭证编号
- 凭证字
- 摘要
- 科目编码

填充字段必须由集团配置明确指定，不能默认对所有字段执行前向填充。

### 14.5 字符串清洗

对字符串字段执行：

- 去除前后空格
- 空字符串转为空值
- 统一特殊空白字符
- 按配置增加字段值前缀

原始值和清洗后的值在需要时应保留在错误记录或审计日志中。

### 14.6 日期转换

负责将日期字段转换为 Pandas 日期类型，包括：

- 凭证日期
- 过账日期
- 业务日期
- 期间字段

无法转换的日期应记录错误行和原始值，并根据配置决定是转为空值、进入错误文件，还是终止本次转换。

### 14.7 金额转换

负责将金额字段转换为数值类型，包括：

- 删除千分位逗号
- 清理货币符号
- 处理括号负数
- 处理空字符串
- 保留指定小数位
- 记录无法转换的金额

每个集团应单独配置金额字段，例如：

```text
集团 A：本币金额
集团 B：原币金额、借方金额、贷方金额
集团 C：总帐金额
```

### 14.8 借贷方向处理

根据集团的借贷标识调整金额正负号：

- 借方金额保持正数
- 贷方金额转为负数
- 未知标识按配置处理

借贷标识、借方值、贷方值和金额字段都必须在集团配置中定义。

### 14.9 凭证编号生成

根据集团字段生成或补充凭证编号，例如使用：

```text
期间 + 凭证字 + 凭证号
```

该模块还可以负责：

- 凭证号格式化
- 凭证号补零
- 检查凭证号重复
- 检查凭证号跨期间使用

### 14.10 科目层级提取

根据集团的科目编码或科目全名生成科目层级字段，例如：

- 一级科目编码
- 一级科目名称
- 科目级次
- 科目全路径

科目层级规则应按集团配置，不能假设所有集团都使用前四位或下划线分隔。

### 14.11 作废凭证过滤

根据凭证状态字段删除或标记作废凭证，例如：

```text
已作废
作废
Voided
```

建议默认保留过滤统计信息，并允许配置为“删除”或“增加状态标识”。

### 14.12 结转记录过滤

根据摘要或业务类型过滤结转记录，例如：

```text
结转本年利润
结转损益
期末结转
```

具体匹配规则应支持前缀、包含、正则表达式等方式，并记录被过滤的行数。

### 14.13 零金额记录过滤

当集团指定的全部金额字段为空或为零时，可以删除该记录。

是否删除、检查哪些金额列，应由集团配置决定。对于审计场景，也可以只标记而不删除。

### 14.14 数据质量检查

建议检查：

- 必填字段是否存在
- 日期转换失败数量
- 金额转换失败数量
- 借贷标识是否在允许值范围内
- 凭证编号是否为空
- 凭证号是否重复或跨期间重复
- 金额是否全部为空或为零
- 输出行数与输入行数变化

检查结果应输出质量报告，并保留错误记录。

### 14.15 增加来源信息

在输出结果中增加：

```text
_source_file
_source_sheet
_source_row
_group
_company
_conversion_time
_config_version
```

这些字段用于定位原始数据和复核转换过程。

### 14.16 输出 Parquet

最后将清洗后的 Pandas DataFrame 输出为 Parquet：

```python
df.to_parquet(output_file, index=False)
```

输出前应确认：

- 字段名称符合该集团配置
- 字段顺序稳定
- 日期和金额类型正确
- 文件目录已创建
- 输出文件未被意外覆盖
- 质量报告已经生成
