"""ICR 분모 후보(이자비용 / 금융비용 / 현금흐름표 이자지급)가 서로 얼마나 다른지 측정 타당성만 본다.

이 스크립트가 하는 일
  - 사전기간 연간 보고서(2019·2020 사업보고서, 상태 000)에서 세 후보 금액을 읽어, 후보끼리의 비율 분포를 센다.
  - 영업이익·노출도 E는 읽지 않는다. ICR을 계산하지 않는다. 즉 결과(ICR 변화)와 무관한 '측정' 점검이다.
  - 계정 이름 규칙은 config.ACCOUNT_PATTERNS 그대로(결과를 보고 고치지 않는다).
  - 한 응답에서 같은 후보가 여러 줄 매칭되는 경우는 합치지 않고 '여러 줄'로만 세고 비율 계산에서는 뺀다.
저장: outputs/05_계정확보/이자분모_후보_비교_연간.csv  (기업·연도별 세 후보 금액)
실행: python -X utf8 03_이자분모_후보_비교.py (저장된 파일만 읽음, 키 필요 없음)
"""
import csv
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
RESULT = config.BASE / "outputs" / "04_본수집" / "본수집_결과_기업별.csv"
OUTDIR = config.BASE / "outputs" / "05_계정확보"
FS_DIR = config.RAW / "fs"
KEYS = {"interest_exp": "이자비용", "fin_cost": "금융비용", "interest_paid_cf": "이자지급_CF"}
PATS = {k: (set(config.ACCOUNT_PATTERNS[k][0].split("|")), re.compile(config.ACCOUNT_PATTERNS[k][1])) for k in KEYS}


def to_num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def pick(rows, key):
    sjs, pat = PATS[key]
    hits = [r for r in rows if r.get("sj_div") in sjs and pat.search(re.sub(r"\s+", "", r.get("account_nm", "")))
            and to_num(r.get("thstrm_amount")) is not None]
    return hits


def q(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))]


def describe(name, ratios):
    if not ratios:
        print(f"  {name}: 해당 없음")
        return
    print(f"  {name}: n={len(ratios):,} | 10%={q(ratios,.1):.2f} 25%={q(ratios,.25):.2f} 중앙값={statistics.median(ratios):.2f} 75%={q(ratios,.75):.2f} 90%={q(ratios,.9):.2f}")


def main():
    firms = {r["corp_code"]: r for r in csv.DictReader(open(RESULT, encoding="utf-8-sig"))}
    chosen = {}
    for r in csv.DictReader(open(LOG, encoding="utf-8-sig")):
        if r["status"] == "000" and r["report"] == "FY" and int(r["year"]) in (2019, 2020):
            k = (r["corp_code"], int(r["year"]))
            if k not in chosen or r["fs_div"] == "CFS":
                chosen[k] = r["fs_div"]
    rows = []
    multi = Counter()
    for (c, y), fs in sorted(chosen.items()):
        d = json.loads((FS_DIR / f"{c}_{y}_11011_{fs}.json").read_text(encoding="utf-8"))["list"]
        rec = {"corp_code": c, "회사명": firms[c]["회사명"], "현재_법인구분": firms[c]["현재_법인구분"], "year": y, "fs_div": fs}
        for k, nm in KEYS.items():
            h = pick(d, k)
            if len(h) > 1:
                multi[k] += 1
                rec[nm] = "여러줄"
            elif len(h) == 1:
                rec[nm] = to_num(h[0]["thstrm_amount"])
            else:
                rec[nm] = ""
        rows.append(rec)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    with open(OUTDIR / "이자분모_후보_비교_연간.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def num(r, nm):
        v = r[nm]
        return v if isinstance(v, float) else None

    print(f"연간 보고서 {len(rows):,}건(2019·2020 사업보고서, 기업 {len({r['corp_code'] for r in rows}):,}곳)")
    print("후보가 한 응답에서 여러 줄 매칭된 건수:", dict(multi))
    have = {nm: sum(1 for r in rows if num(r, nm) is not None) for nm in KEYS.values()}
    print("후보별로 값이 하나로 잡힌 건수:", have)

    print("\n[A] 이자비용과 금융비용이 둘 다 잡힌 건: 이자비용 ÷ 금융비용 (1이면 같은 값, 작을수록 금융비용에 이자 아닌 항목이 많음)")
    both = [(num(r, "이자비용"), num(r, "금융비용")) for r in rows if num(r, "이자비용") and num(r, "금융비용") and num(r, "금융비용") > 0]
    describe("이자비용/금융비용", [a / b for a, b in both])
    print("[B] 이자비용과 CF 이자지급이 둘 다 잡힌 건: CF 이자지급 ÷ 이자비용")
    both2 = [(num(r, "이자지급_CF"), num(r, "이자비용")) for r in rows if num(r, "이자지급_CF") and num(r, "이자비용") and num(r, "이자비용") > 0]
    describe("이자지급/이자비용", [a / b for a, b in both2])
    print("[C] 금융비용과 CF 이자지급이 둘 다 잡힌 건(전체 표본): CF 이자지급 ÷ 금융비용")
    both3 = [(num(r, "이자지급_CF"), num(r, "금융비용")) for r in rows if num(r, "이자지급_CF") and num(r, "금융비용") and num(r, "금융비용") > 0]
    ratios = [a / b for a, b in both3]
    describe("이자지급/금융비용", ratios)
    n = len(ratios)
    for lo, hi in ((0, .25), (.25, .5), (.5, .75), (.75, 1.25), (1.25, 99)):
        k = sum(1 for x in ratios if lo <= x < hi)
        print(f"     {lo:.2f}~{hi:.2f}: {k:,}건 ({k/n:.1%})")
    print("\n이자비용이 값으로 잡힌 기업:", len({r['corp_code'] for r in rows if num(r, '이자비용') is not None}), "곳")
    print("저장:", OUTDIR / "이자분모_후보_비교_연간.csv")


if __name__ == "__main__":
    main()
