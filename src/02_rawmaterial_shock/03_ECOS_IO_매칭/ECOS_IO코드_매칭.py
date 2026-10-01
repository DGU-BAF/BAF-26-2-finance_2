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
"""
ECOS 수입물가지수(기본분류) 세부품목 <-> IO 기본부문 코드 매칭 초안.
이름을 정규화(공백/쉼표 제거)해서 정확히 일치하는 것부터 자동 매칭한다.
"""
import csv
import re
from pathlib import Path

ecos_path = RAW / "원자재" / "수입물가지수(기본분류)_26233649.csv"
io_codes_path = SHOCK_INTERIM / "IO코드_행목록.csv"
out_path = SHOCK_INTERIM / "ECOS_IO코드_매칭표.csv"

def norm(s):
    return re.sub(r"[\s,()0-9a-zA-Z]", "", s or "")

# IO 코드 목록 로드
io_items = []
with open(io_codes_path, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        io_items.append((r["code"], r["name"]))
io_norm_map = {}
for code, name in io_items:
    io_norm_map.setdefault(norm(name), []).append((code, name))

# ECOS 원화기준 항목 로드 (leaf 여부 상관없이 전부, 트리 구조 보존 위해 부모경로도 기록)
with open(ecos_path, encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = [r for r in reader if r[2] == "원화기준"]

results = []
stack = []  # (indent, name)
for r in rows:
    raw_name = r[1]
    weight = r[4]
    indent = len(raw_name) - len(raw_name.lstrip())
    name = raw_name.strip()
    stack = [s for s in stack if s[0] < indent]
    parent_path = " > ".join(s[1] for s in stack)
    stack.append((indent, name))

    key = norm(name)
    matches = io_norm_map.get(key, [])
    results.append({
        "ecos_indent": indent,
        "ecos_name": name,
        "ecos_parent_path": parent_path,
        "ecos_weight": weight,
        "io_match_count": len(matches),
        "io_matched_codes": "; ".join(f"{c}({n})" for c, n in matches),
    })

with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
    w.writeheader()
    w.writerows(results)

# 요약 통계
total = len(results)
matched = sum(1 for r in results if r["io_match_count"] > 0)
print(f"ECOS 항목 총 {total}개, 그중 IO코드와 정확히 이름 일치 {matched}개")

# 우리 8개 카테고리 관련 핵심 품목만 추려서 콘솔에 출력
targets = ["원유", "천연가스(LNG)", "철광석", "기타비철금속광석", "기타비금속광물",
           "동제련,정련및합금제품", "알루미늄제련,정련및합금제품", "연및아연제련,정련및합금제품",
           "금은괴", "기타비철금속제련,정련및합금제품", "동1차제품", "알루미늄1차제품", "기타비철금속1차제품",
           "선철", "합금철", "조강", "철근및봉강", "형강", "중후판(두께3mm이상)", "열연강판", "철강관",
           "냉간압연강재", "표면처리강재",
           "제재목", "합판", "강화및재생목재", "펄프", "인쇄용지", "기타원지및판지",
           "천연및화학섬유사", "천연및화학섬유직물",
           "곡류", "맥류및잡곡", "콩류", "과일", "잎담배", "천연고무", "기타식용작물", "기타비식용작물"]

print("\n--- 타겟 품목별 매칭 결과 ---")
for r in results:
    if r["ecos_name"] in targets:
        print(f"{r['ecos_name']:20s} (가중치{r['ecos_weight']:>6s}) -> {r['io_matched_codes'] or '매칭 없음'}")
