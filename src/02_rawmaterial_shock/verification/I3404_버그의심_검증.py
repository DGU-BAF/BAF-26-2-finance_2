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
"""두번째 리뷰(off-by-one 버그 의심) 검증 - W직접조회 vs M경유조회 차이 확인"""
import csv
import numpy as np
import openpyxl
from pathlib import Path

BASE = ROOT
IO_XLSX = RAW / "원자재" / "투입산출표_생산자가격_기본부문_2019년연장표.xlsx"
IO_CODES_CSV = SHOCK_INTERIM / "IO코드_행목록.csv"
W_CSV = INTERIM / "가중치행렬_W_2019_계산용.csv"
XWALK_CSV = SHOCK_INTERIM / "최종_크로스워크표.csv"

io_codes = []
with open(IO_CODES_CSV, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["code"] != "9590":
            io_codes.append(r["code"])
n = len(io_codes)
idx = {c:i for i,c in enumerate(io_codes)}
idx_1111 = idx["1111"]; idx_1119 = idx["1119"]

# I3404가 실제로 어느 상품코드(들)에 매핑되는지 확인
i3404_products = []
i3403_products = []
with open(XWALK_CSV, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["istans_industry_code"] == "I3404":
            i3404_products.append((r["code"], r["name"]))
        if r["istans_industry_code"] == "I3403":
            i3403_products.append((r["code"], r["name"]))
print("I3404(의류)가 매핑된 실제 상품코드들:", i3404_products)
print("I3403(섬유)가 매핑된 실제 상품코드들(일부):", i3403_products[:5], "... 총", len(i3403_products), "개")

with open(W_CSV, encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    w_header = next(reader)
    w_rows = list(reader)
industry_codes = [r[0] for r in w_rows]
W = np.array([[float(x) for x in r[1:]] for r in w_rows])
i3404_row = industry_codes.index("I3404")
i3403_row = industry_codes.index("I3403")

print("\n=== 1) 리뷰가 확인한 것: W에서 '1111/1119 열'의 값 ===")
print("W[I3404, 1111열] =", W[i3404_row, idx_1111], " / W[I3404, 1119열] =", W[i3404_row, idx_1119])
print("W[I3403, 1111열] =", W[i3403_row, idx_1111], " / W[I3403, 1119열] =", W[i3403_row, idx_1119])
print("-> 이건 '실(1111/1119)이라는 상품을 I3404/I3403이 얼마나 직접 생산하는지' 비중이라 I3404=0은 당연함(의류업은 실을 안 만드니까)")

# I3404의 실제 상품코드(예: 1151 봉제의류)에 대한 W값 확인
print("\n=== 2) I3404 자신의 상품코드 열에 대한 W값 (정상적으로 0이 아니어야 함) ===")
for code, name in i3404_products[:3]:
    j = idx[code]
    print(f"W[I3404, {code}({name})열] =", W[i3404_row, j])

print("\n=== 3) 진짜 노출 경로: M[1111행/1119행, I3404 자신의 상품코드 열] ===")
wb = openpyxl.load_workbook(IO_XLSX, read_only=True, data_only=True)
ws = wb["수입유발계수"]
M = np.zeros((n, n))
for i, row in enumerate(ws.iter_rows(min_row=7, max_row=387, min_col=3, max_col=383, values_only=True)):
    M[i, :] = [x if x is not None else 0.0 for x in row]

for code, name in i3404_products[:5]:
    j = idx[code]
    print(f"M[1111행, {code}({name})열] = {M[idx_1111, j]:.6f}  |  M[1119행, {code}열] = {M[idx_1119, j]:.6f}")

# (W @ M.T) 로 실제 diff 비율 재현
col_1111 = (W @ M.T)[:, idx_1111]
col_1119 = (W @ M.T)[:, idx_1119]
print("\n=== 4) (W·M')[:,1119] 값으로 diff 비율 직접 재현 ===")
print("I3404 (WM')[:,1119] =", col_1119[i3404_row])
print("I3403 (WM')[:,1119] =", col_1119[i3403_row])
print("비율(I3404/I3403) =", col_1119[i3404_row]/col_1119[i3403_row])
print("-> 이 비율이 실제 패널의 diff 비율(10.3배)과 일치해야 '버그 아님'이 확정됨")
