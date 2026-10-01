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
import csv
from pathlib import Path

w_csv = INTERIM / "가중치행렬_W_2019_계산용.csv"
io_codes_path = SHOCK_INTERIM / "IO코드_행목록.csv"

with open(w_csv, encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

print("행 수(업종):", len(rows), "열 수(상품, 헤더 제외):", len(header)-1)

with open(io_codes_path, encoding="utf-8-sig") as f:
    io_codes = [r["code"] for r in csv.DictReader(f) if r["code"] != "9590"]

w_product_codes = header[1:]
print("길이 비교: W열수=", len(w_product_codes), "IO원본(9590제외)=", len(io_codes))
print("컬럼 순서가 IO 원본 순서와 동일한가(9590 제외 후):", w_product_codes == io_codes)
if w_product_codes != io_codes:
    for i, (a, b) in enumerate(zip(w_product_codes, io_codes)):
        if a != b:
            print(f"첫 불일치 위치 {i}: W={a}, IO원본={b}")
            break
    print("set 동일 여부(순서 무시):", set(w_product_codes) == set(io_codes))

bad = 0
for r in rows:
    ind = r[0]
    vals = [float(x) for x in r[1:]]
    s = sum(vals)
    if abs(s-1) > 1e-6:
        bad += 1
        print(ind, "행합:", s)
print("행합이 1이 아닌 행 수:", bad)
