"""본 수집 응답 안에 필요한 계정이 '있는지'만 센다 (A8 판단 목록의 1·2·3번 재료).

이 스크립트가 하는 일
  1. outputs/04_본수집/본수집_로그.csv에서 상태 000인 응답(기업·연도·보고서·연결/별도)을 읽는다.
     (같은 기업·연도·보고서에 연결이 000이면 연결, 아니면 별도: 본 수집이 연결을 먼저 물었기 때문)
  2. 각 응답 파일에서 config.ACCOUNT_PATTERNS의 계정이 있는지, 값 칸이 비어 있지 않은지만 기록한다.
     금액 자체는 읽거나 계산하지 않는다. ICR·노출도 E는 계산하지 않는다.
  3. 보고서별 표, 기업별 표, 법인구분·업종별 요약을 outputs/05_계정확보/에 저장한다.

계정 이름 규칙은 파일럿에서 쓴 config.ACCOUNT_PATTERNS를 그대로 쓴다(이번 결과를 보고 고치지 않는다.
고치게 되면 이유와 함께 사전 고정 문서 변경 기록에 적는다).

실행: python -X utf8 01_계정_확보현황.py            (저장된 파일만 읽음, 키 필요 없음)
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
RESULT = config.BASE / "outputs" / "04_본수집" / "본수집_결과_기업별.csv"
OUTDIR = config.BASE / "outputs" / "05_계정확보"
FS_DIR = config.RAW / "fs"

REP_ORDER = {"Q1": 0, "H1": 1, "Q3": 2, "FY": 3}
PATS = {k: (set(v[0].split("|")), re.compile(v[1])) for k, v in config.ACCOUNT_PATTERNS.items()}
KEYS = list(PATS)
# 누적 칸(thstrm_add_amount)이 필요한 손익 계정
ADD_KEYS = ["op_income", "interest_exp", "fin_cost"]


def is_pre(year, rep):
    """사전기간 2019Q1~2021Q2 (10개 보고서)"""
    return (2019, 0) <= (year, REP_ORDER[rep]) <= (2021, 1)


def nonempty(v):
    return v is not None and str(v).strip() not in ("", "-")


def scan(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("list", [])
    out = {"n_rows": len(rows)}
    for k, (sjs, pat) in PATS.items():
        hits = [r for r in rows if r.get("sj_div") in sjs and pat.search(re.sub(r"\s+", "", r.get("account_nm", "")))
                and nonempty(r.get("thstrm_amount"))]
        out[k] = bool(hits)
        out[k + "_n"] = len(hits)
    for k in ADD_KEYS:
        sjs, pat = PATS[k]
        out[k + "_누적칸"] = any(r.get("sj_div") in sjs and pat.search(re.sub(r"\s+", "", r.get("account_nm", "")))
                              and nonempty(r.get("thstrm_add_amount")) for r in rows)
    return out


def main():
    firms = {r["corp_code"]: r for r in csv.DictReader(open(RESULT, encoding="utf-8-sig"))}
    chosen = {}                                  # (corp, year, rep) -> fs
    for r in csv.DictReader(open(LOG, encoding="utf-8-sig")):
        if r["status"] != "000":
            continue
        k = (r["corp_code"], int(r["year"]), r["report"])
        if k not in chosen or r["fs_div"] == "CFS":
            chosen[k] = r["fs_div"]
    print(f"확인할 응답 {len(chosen):,}개 (기업 {len(firms):,}곳)")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    per_report = []
    for i, ((corp, year, rep), fs) in enumerate(sorted(chosen.items()), 1):
        p = FS_DIR / f"{corp}_{year}_{config.REPORTS[rep]}_{fs}.json"
        s = scan(p)
        s.update({"corp_code": corp, "year": year, "report": rep, "fs_div": fs, "사전기간": is_pre(year, rep)})
        per_report.append(s)
        if i % 5000 == 0:
            print(f"  {i:,}개 읽음")

    cols = ["corp_code", "year", "report", "fs_div", "사전기간", "n_rows"] + KEYS + [k + "_n" for k in KEYS] + [k + "_누적칸" for k in ADD_KEYS]
    with open(OUTDIR / "계정확보_보고서별.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(per_report)

    # 기업별 집계
    agg = defaultdict(lambda: defaultdict(int))
    for s in per_report:
        a = agg[s["corp_code"]]
        a["n_all"] += 1
        a["n_pre"] += s["사전기간"]
        for k in KEYS:
            a[k + "_all"] += s[k]
            a[k + "_pre"] += s[k] and s["사전기간"]
    rows = []
    for c, f in firms.items():
        a = agg[c]
        row = {"corp_code": c, "회사명": f["회사명"], "현재_법인구분": f["현재_법인구분"], "업종2": f["업종코드"][:2],
               "연결별도_혼재": f["연결별도_혼재"], "보고서수": a["n_all"], "사전기간_보고서수": a["n_pre"]}
        for k in KEYS:
            row[k + "_전체"] = a[k + "_all"]
            row[k + "_사전"] = a[k + "_pre"]
        rows.append(row)
    with open(OUTDIR / "계정확보_기업별.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ── 요약 출력 ──
    N = len(per_report)
    print("\n== 1. 보고서 단위 확보율 (상태 000 응답 %d개 중 계정이 있고 값 칸이 비어 있지 않은 비율) ==" % N)
    pre = [s for s in per_report if s["사전기간"]]
    for k in KEYS:
        t = sum(s[k] for s in per_report)
        tp = sum(s[k] for s in pre)
        multi = sum(1 for s in per_report if s[k + "_n"] > 1)
        print(f"  {k:18s} 전체 {t/N:6.1%} ({t:,}) | 사전기간 {tp/len(pre):6.1%} ({tp:,}/{len(pre):,}) | 한 응답에 여러 줄 매칭 {multi:,}건")
    print("\n== 2. 누적 칸(thstrm_add_amount) 확보: 반기·3분기 응답 중 ==")
    h = [s for s in per_report if s["report"] in ("H1", "Q3")]
    for k in ADD_KEYS:
        have = [s for s in h if s[k]]
        t = sum(s[k + "_누적칸"] for s in have)
        print(f"  {k:14s} 계정이 있는 반기·3분기 응답 {len(have):,}개 중 누적 칸 있음 {t:,} ({t/max(1,len(have)):.1%})")

    print("\n== 3. 기업 단위: 사전기간 10개 보고서 중 계정이 확보된 개수 분포(기업 수) ==")
    for k in KEYS:
        cnt = Counter()
        for r in rows:
            n, tot = r[k + "_사전"], r["사전기간_보고서수"]
            cnt["0개" if n == 0 else ("보유 보고서 전부" if n == tot else "일부")] += 1
        print(f"  {k:18s} {dict(cnt)}")

    print("\n== 4. 이자 대용 계정 후보의 기업 단위 겹침: 사전기간 보유 보고서에서 한 번이라도 있는 기업 ==")
    for combo in (("interest_exp",), ("fin_cost",), ("interest_paid_cf",), ("fin_cost", "interest_paid_cf"), ("interest_exp", "fin_cost", "interest_paid_cf")):
        n_any = sum(1 for r in rows if all(r[k + "_사전"] > 0 for k in combo))
        n_full = sum(1 for r in rows if r["사전기간_보고서수"] > 0 and all(r[k + "_사전"] == r["사전기간_보고서수"] for k in combo))
        print(f"  {' + '.join(combo):45s} 한 번이라도 {n_any:,}곳 | 사전기간 보고서 전부에서 {n_full:,}곳")

    print("\n== 5. 노출도 E 분자 계정(사전기간): 한 번이라도 있는 기업 / 보유 보고서 전부에서 있는 기업 ==")
    for k in ("assets", "st_borrow", "cur_ltd", "cur_bond"):
        n_any = sum(1 for r in rows if r[k + "_사전"] > 0)
        n_full = sum(1 for r in rows if r["사전기간_보고서수"] > 0 and r[k + "_사전"] == r["사전기간_보고서수"])
        print(f"  {k:12s} {n_any:,}곳 / {n_full:,}곳")
    n_none = sum(1 for r in rows if r["st_borrow_사전"] == 0 and r["cur_ltd_사전"] == 0 and r["cur_bond_사전"] == 0)
    print(f"  차입 3계정이 사전기간에 하나도 없는 기업: {n_none:,}곳")

    print("\n== 6. 법인구분별: 영업이익·자산·(금융비용 또는 이자지급) 사전기간 전부 확보 기업 비율 ==")
    by = defaultdict(list)
    for r in rows:
        by[r["현재_법인구분"]].append(r)
    for g, rs in sorted(by.items()):
        def full(r, ks):
            return r["사전기간_보고서수"] > 0 and all(r[k + "_사전"] == r["사전기간_보고서수"] for k in ks)
        a = sum(full(r, ["op_income", "assets"]) for r in rs)
        b = sum(full(r, ["op_income", "assets", "fin_cost"]) for r in rs)
        c = sum(full(r, ["op_income", "assets", "interest_paid_cf"]) for r in rs)
        print(f"  {g}: {len(rs)}곳 | 영업이익+자산 {a/len(rs):.1%} | +금융비용 {b/len(rs):.1%} | +이자지급(CF) {c/len(rs):.1%}")

    ind = defaultdict(list)
    for r in rows:
        ind[r["업종2"]].append(r)
    ind_rows = []
    for g, rs in sorted(ind.items()):
        def full(r, ks):
            return r["사전기간_보고서수"] > 0 and all(r[k + "_사전"] == r["사전기간_보고서수"] for k in ks)
        ind_rows.append({"업종2": g, "기업수": len(rs),
                         "영업이익+자산_사전전부": sum(full(r, ["op_income", "assets"]) for r in rs),
                         "+금융비용_사전전부": sum(full(r, ["op_income", "assets", "fin_cost"]) for r in rs),
                         "+이자지급CF_사전전부": sum(full(r, ["op_income", "assets", "interest_paid_cf"]) for r in rs),
                         "차입3계정_사전_하나도없음": sum(1 for r in rs if r["st_borrow_사전"] == 0 and r["cur_ltd_사전"] == 0 and r["cur_bond_사전"] == 0)})
    with open(OUTDIR / "계정확보_업종별.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ind_rows[0].keys()))
        w.writeheader()
        w.writerows(ind_rows)
    print("\n업종별 표는 파일로 저장했습니다:", OUTDIR / "계정확보_업종별.csv")
    print("저장:", OUTDIR)


if __name__ == "__main__":
    main()
