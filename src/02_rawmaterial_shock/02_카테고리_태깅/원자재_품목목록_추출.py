# --- 경로 설정: 레포 어디에서 실행해도 data/ 폴더를 찾아 루트로 지정 (절대경로 사용 금지) ---
from pathlib import Path as _P
ROOT = next(p for p in _P(__file__).resolve().parents if (p / "data" / "raw").exists())
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
SHOCK_INTERIM = INTERIM / "원자재_충격지표"
PROCESSED = ROOT / "data" / "processed"
SHOCK_INTERIM.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)
# ---------------------------------------------------------------------------------
# -*- coding: utf-8 -*-
import csv
from pathlib import Path

path = RAW / "원자재" / "수입물가지수(기본분류)_26233649.csv"
out = SHOCK_INTERIM / "원자재_품목목록_원본.txt"

with open(path, encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

lines = []
lines.append(f"총 행수: {len(rows)}")
won = [r for r in rows if r[2] == "원화기준"]
lines.append(f"원화기준 고유항목 수: {len(won)}")
for r in won:
    name, weight = r[1], r[4]
    indent = len(name) - len(name.lstrip())
    lines.append(f"{'  '*indent}{name.strip()}  (가중치:{weight})")

with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("done, lines:", len(lines))
