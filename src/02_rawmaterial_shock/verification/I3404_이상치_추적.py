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
"""I3404(의류)의 diff_1119_effect가 왜 유독 큰지 원인 진단"""
import csv
import numpy as np
import openpyxl
from pathlib import Path

BASE = ROOT
IO_XLSX = RAW / "원자재" / "투입산출표_생산자가격_기본부문_2019년연장표.xlsx"
IO_CODES_CSV = SHOCK_INTERIM / "IO코드_행목록.csv"
W_CSV = INTERIM / "가중치행렬_W_2019_계산용.csv"

io_codes = []
with open(IO_CODES_CSV, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["code"] != "9590":
            io_codes.append(r["code"])
n = len(io_codes)
idx_1111 = io_codes.index("1111")
idx_1119 = io_codes.index("1119")

wb = openpyxl.load_workbook(IO_XLSX, read_only=True, data_only=True)
ws = wb["수입유발계수"]
M = np.zeros((n, n))
for i, row in enumerate(ws.iter_rows(min_row=7, max_row=387, min_col=3, max_col=383, values_only=True)):
    M[i, :] = [x if x is not None else 0.0 for x in row]

with open(W_CSV, encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    w_header = next(reader)
    w_rows = list(reader)
industry_codes = [r[0] for r in w_rows]
W = np.array([[float(x) for x in r[1:]] for r in w_rows])

# (W @ M.T) 의 컬럼: 1111, 1119 각각에 대해 각 업종이 받는 가중치(간접노출계수)
col_1111 = (W @ M.T)[:, idx_1111]
col_1119 = (W @ M.T)[:, idx_1119]

print("업종별 (WM')[:,1111]과 (WM')[:,1119] 비교, I3404 순위 확인")
pairs = list(zip(industry_codes, col_1111, col_1119))
i3404 = [p for p in pairs if p[0] == "I3404"][0]
print("I3404:", i3404)

rank_1119 = sorted(pairs, key=lambda p: -abs(p[2]))
print("\n1119에 대한 간접노출계수 절대값 상위 10개 업종:")
for p in rank_1119[:10]:
    print(p)

rank_1111 = sorted(pairs, key=lambda p: -abs(p[1]))
print("\n1111에 대한 간접노출계수 절대값 상위 10개 업종:")
for p in rank_1111[:10]:
    print(p)

# I3403(섬유) 도 비교
i3403 = [p for p in pairs if p[0] == "I3403"][0]
print("\nI3403(섬유) 비교:", i3403)

# 비율: 1119계수/1111계수 (I3404가 유독 1119 비중이 큰지)
print("\nI3404: 1119/1111 비율 =", i3404[2]/i3404[1] if i3404[1]!=0 else None)
print("I3403: 1119/1111 비율 =", i3403[2]/i3403[1] if i3403[1]!=0 else None)

# 전체 업종 평균 비율
ratios = [(p[0], p[2]/p[1]) for p in pairs if abs(p[1]) > 1e-9]
ratios_sorted = sorted(ratios, key=lambda x: -abs(x[1]))
print("\n1119/1111 비율 절대값 상위 10개 업종:")
for r in ratios_sorted[:10]:
    print(r)
