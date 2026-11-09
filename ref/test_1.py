from pathlib import Path
import pandas as pd


input_dir = Path("D:/Temp/test_data/ledgers/温州工厂")



df = pd.read_pickle(
    "D:/Temp/test_data/ledgers/温州工厂/26年1-2月.pkl",

)

print(df.columns)
