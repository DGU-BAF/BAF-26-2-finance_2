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
"""전체 파이프라인에서 조용히 넘어간 오류/이상치가 있는지 점검"""
import csv
import numpy as np
import openpyxl
from pathlib import Path

BASE = ROOT
IO_XLSX = RAW / "원자재" / "투입산출표_생산자가격_기본부문_2019년연장표.xlsx"
IO_CODES_CSV = SHOCK_INTERIM / "IO코드_행목록.csv"
PANEL_CSV = PROCESSED / "원자재_가격충격_패널.csv"
ECOS_CSV = RAW / "원자재" / "수입물가지수(기본분류)_26233649.csv"

io_codes = []
with open(IO_CODES_CSV, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["code"] != "9590":
            io_codes.append(r["code"])
n = len(io_codes)

# 1) 결과 패널에 NaN/inf 있는지
print("=== 1) 결과 패널 NaN/inf 점검 ===")
with open(PANEL_CSV, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
bad = 0
for r in rows:
    for k in ["shock_baseline_1111only","shock_extended_1111_1119","diff_1119_effect"]:
        v = float(r[k])
        if not np.isfinite(v):
            bad += 1
            print("이상치:", r)
print(f"총 {len(rows)}행 중 NaN/inf: {bad}개")

# 2) M(수입유발계수) 행렬에 음수 얼마나 있는지, 극단값 있는지
print("\n=== 2) 수입유발계수(M) 행렬 음수·이상치 점검 ===")
wb = openpyxl.load_workbook(IO_XLSX, read_only=True, data_only=True)
ws = wb["수입유발계수"]
M = np.zeros((n, n))
none_count = 0
for i, row in enumerate(ws.iter_rows(min_row=7, max_row=387, min_col=3, max_col=383, values_only=True)):
    for j, v in enumerate(row):
        if v is None:
            none_count += 1
            M[i, j] = 0.0
        else:
            M[i, j] = v
print("None(빈 셀) 개수:", none_count, "/", n*n)
neg = M[M < 0]
print("음수 개수:", neg.size, "/", n*n, f"({neg.size/(n*n)*100:.3f}%)")
if neg.size:
    print("음수 최소값:", neg.min(), "음수 최대값:", neg.max())
    # 음수가 어디에 몰려있는지 상위 5개 (절대값 큰 순)
    neg_idx = np.argwhere(M < 0)
    neg_vals = [(M[i,j], io_codes[i], io_codes[j]) for i,j in neg_idx]
    neg_vals.sort(key=lambda x: x[0])
    print("가장 큰(음의 방향) 음수 5개 (행코드=수입원자재, 열코드=국내상품):")
    for v in neg_vals[:5]:
        print(v)
print("양수 최대값(가장 큰 노출계수):", M.max())

# 3) 우리가 확정한 코드들의 ECOS 가격시계열에 결측(연도 누락) 있는지
print("\n=== 3) 확정 코드별 ECOS 가격 시계열 결측 점검 (2015~2025) ===")
IO_TO_ECOS_NAME = {
    "0621": "원유", "0302": "원목", "1311": "제재목", "1312": "합판", "1313": "강화및재생목재",
    "2711": "선철", "2712": "합금철", "2713": "조강",
    "2721": "철근및봉강", "2722": "형강", "2724": "중후판(두께3mm이상)",
    "2725": "열연강판", "2727": "철강관", "2730": "냉간압연강재", "2791": "표면처리강재",
    "2811": "동제련,정련및합금제품", "2812": "알루미늄제련,정련및합금제품",
    "2813": "연및아연제련,정련및합금제품", "2814": "금은괴",
    "2819": "기타비철금속제련,정련및합금제품",
    "2821": "동1차제품", "2822": "알루미늄1차제품", "2829": "기타비철금속1차제품",
    "1410": "펄프", "0729": "기타비금속광물", "1111": "천연및화학섬유사",
    "0112": "맥류및잡곡", "0113": "콩류", "0193": "잎담배", "0194": "천연고무",
    "0196": "기타식용작물", "0199": "기타비식용작물",
}
with open(ECOS_CSV, encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    years = [int(y) for y in header[6:]]
    ecos_rows = [r for r in reader if r[2] == "원화기준"]
ecos_series = {}
for r in ecos_rows:
    name = r[1].strip()
    vals = {}
    for y, v in zip(years, r[6:]):
        try:
            vals[y] = float(v)
        except ValueError:
            vals[y] = None
    if name not in ecos_series:
        ecos_series[name] = vals

target_years = list(range(2014, 2026))
missing_report = []
for code, name in IO_TO_ECOS_NAME.items():
    s = ecos_series.get(name, {})
    missing = [y for y in target_years if s.get(y) is None]
    zero_years = [y for y in target_years if s.get(y) == 0]
    if missing or zero_years:
        missing_report.append((code, name, missing, zero_years))
if missing_report:
    print("결측/0값 있는 코드:")
    for m in missing_report:
        print(m)
else:
    print("2014~2025년 구간, 확정 코드 전부 결측 없음")
