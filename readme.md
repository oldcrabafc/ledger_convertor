# Excel 转 Pickle 缓存

这个目录下的脚本用于把 Excel `.xlsx` 文件转换为 pickle 文件，方便后续读取和缓存。

## 文件说明

- `cache_ledger.py`: 主脚本，负责读取 Excel 并保存为 pickle
- `.env`: 配置文件，存放输入文件、输出文件名和缓存根目录

## 使用方式

1. 编辑 `convert_ledger/.env`，填写你的配置：

```env
SOURCE=D:/Datasets/audit_projects/raw/KH/ledger.xlsx
OUTPUT=ledger_FY24
ROOT_DIR=D:/Temp/test_data/ledger_cache
```

说明：
- `SOURCE`：输入的 Excel 文件路径
- `OUTPUT`：输出文件名，不需要写 `.pkl` 扩展名
- `ROOT_DIR`：pickle 文件保存的根目录

2. 在项目根目录执行：

```bash
cd /d/Projects/audit_projects
uv run python convert_ledger/cache_ledger.py
```

3. 脚本会自动把文件保存到：

```text
D:/Temp/test_data/ledger_cache/ledger_FY24.pkl
```

## 命令行临时覆盖配置

如果不想修改 `.env`，也可以直接在命令行传入参数：

```bash
uv run python convert_ledger/cache_ledger.py --source "D:/Data/my_ledger.xlsx" --output-name "ledger_FY24" --root-dir "D:/Temp/test_data/ledger_cache"
```

## Python 直接调用

也可以在代码中直接调用：

```python
from convert_ledger.cache_ledger import main

main(
    source=r"D:/Datasets/audit_projects/raw/KH/ledger.xlsx",
    output="ledger_FY24",
    root_dir=r"D:/Temp/test_data/ledger_cache",
)
```

## 说明

- `OUTPUT` 中请不要写 `.pkl` 后缀，脚本会自动补上
- 脚本会自动清理非法文件名字符，避免路径中的特殊符号导致报错
- 如果 `SOURCE` 或 `OUTPUT` 缺失，会直接报错，避免误跑错误文件

## 常见示例

```env
SOURCE=D:/Data/ledger_2024.xlsx
OUTPUT=ledger_2024
ROOT_DIR=D:/Temp/cache
```

生成结果：

```text
D:/Temp/cache/ledger_2024.pkl
```
