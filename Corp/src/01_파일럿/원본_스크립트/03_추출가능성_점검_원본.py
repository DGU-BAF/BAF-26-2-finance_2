"""3단계: 내려받은 파일럿 자료의 추출 가능성을 점검한다. 회귀·계수는 계산하지 않는다.

실행: python -X utf8 03_check_pilot.py
      python -X utf8 03_check_pilot.py --raw 다른폴더/fs --out 다른폴더/out   (테스트용)

점검: (1) 대상 계정 확보율  (2) 계정명 변형 목록  (3) 분기 환원 항등성  (4) 단위·통화
계정 매핑 규칙(TARGETS)은 '첫 추정'이다. 변형 목록을 보고 팀이 고쳐 쓴다.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import config

sys.stdout.reconfigure(encoding="utf-8")

# 계정명 정규식은 첫 추정. (재무제표 구분, 정규식). 규칙은 config.ACCOUNT_PATTERNS에서 관리한다
TARGETS = config.ACCOUNT_PATTERNS
VARIANT_PATTERN = re.compile(r"차입|사채|이자|금융비용|금융원가|영업이익|유동성|장기부채")
REP_BY_CODE = {v: k for k, v in config.REPORTS.items()}
FILE_RE = re.compile(r"^(\d{8})_(\d{4})_(\d{5})_(CFS|OFS)\.json$")
TOL_REL = 0.005  # 항등식 허용오차(상대). 임의 기준이므로 팀이 정하고 근거를 적는다


def parse_amount(text):
    if text is None:
        return None
    s = str(text).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def first_match(rows, sj_pattern, name_pattern):
    sj_re, nm_re = re.compile(sj_pattern), re.compile(name_pattern)
    # 실제 응답에 '유동성 장기부채'처럼 띄어쓰기가 들어간 계정명이 있어서 공백을 제거한 뒤 비교한다
    matches = [
        r
        for r in rows
        if sj_re.fullmatch(r.get("sj_div", "")) and nm_re.search(re.sub(r"\s+", "", r.get("account_nm", "")))
    ]
    if not matches:
        return None, 0
    def order_key(r):
        try:
            return int(r.get("ord", "0") or 0)
        except ValueError:
            return 0

    matches.sort(key=order_key)
    return matches[0], len(matches)


def load_files(raw_dir):
    files = []
    for path in sorted(Path(raw_dir).glob("*.json")):
        m = FILE_RE.match(path.name)
        if not m:
            continue
        corp, year, rep_code, fs = m.groups()
        data = json.loads(path.read_text(encoding="utf-8"))
        files.append({"corp": corp, "year": int(year), "rep": REP_BY_CODE.get(rep_code, rep_code), "fs": fs, "data": data})
    return files


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def check_close(a, b):
    """a와 b가 같은지. 반환: 'exact' / 'within_tol' / 'exceed'"""
    if abs(a - b) < 1e-9:
        return "exact"
    scale = max(abs(a), abs(b), 1.0)
    return "within_tol" if abs(a - b) <= TOL_REL * scale else "exceed"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(config.RAW / "fs"))
    parser.add_argument("--out", default=str(config.OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    files = load_files(args.raw)
    if not files:
        sys.exit("점검할 파일이 없습니다. 02를 먼저 실행하세요.")
    ok_files = [f for f in files if f["data"].get("status") == "000"]
    print(f"파일 {len(files)}개 중 자료가 있는 것 {len(ok_files)}개")
    print("상태 분포:", dict(Counter(f["data"].get("status") for f in files)))
    print("연결/별도 분포(자료가 있는 파일):", dict(Counter(f["fs"] for f in ok_files)))
    fs_by_year, fs_by_firm = defaultdict(set), defaultdict(set)
    for f in ok_files:
        fs_by_year[(f["corp"], f["year"])].add(f["fs"])
        fs_by_firm[f["corp"]].add(f["fs"])
    print(
        f"연결·별도 혼재: 같은 기업-연도 안에서 {sum(len(s) > 1 for s in fs_by_year.values())}건, "
        f"같은 기업의 연도 간 {sum(len(s) > 1 for s in fs_by_firm.values())}개 기업 "
        "(0이 아니면 사전 고정 문서 3절의 '기준을 섞지 않는다' 규칙을 어긴 것이므로 처리 규칙이 필요)"
    )

    # (1) 계정 확보율, (2) 계정명 변형
    cover = defaultdict(lambda: Counter())
    n_by_rep = Counter(f["rep"] for f in ok_files)
    store = {}  # (corp, year, fs, rep) -> {target: (3m, cum, level)}
    variants = Counter()
    currencies = Counter()
    asset_values = defaultdict(list)
    for f in ok_files:
        rows = f["data"].get("list", [])
        entry = {}
        for r in rows:
            currencies[r.get("currency", "")] += 1
            if VARIANT_PATTERN.search(r.get("account_nm", "")):
                variants[(r.get("sj_div", ""), r.get("account_nm", ""))] += 1
        for tname, (sj, pat) in TARGETS.items():
            row, n = first_match(rows, sj, pat)
            if row is None:
                continue
            cover[tname][f["rep"]] += 1
            amt = parse_amount(row.get("thstrm_amount"))
            add = parse_amount(row.get("thstrm_add_amount"))
            entry[tname] = {"amount": amt, "cum": add, "n_matches": n, "name": row.get("account_nm")}
            if tname == "assets" and amt is not None:
                asset_values[f["corp"]].append(amt)
        store[(f["corp"], f["year"], f["fs"], f["rep"])] = entry

    cover_rows = []
    for tname in TARGETS:
        row = {"target": tname}
        total = 0
        for rep in config.REPORTS:
            got = cover[tname][rep]
            total += got
            row[f"{rep}_확보"] = got
            row[f"{rep}_전체"] = n_by_rep[rep]
        row["확보율(%)"] = round(100 * total / max(len(ok_files), 1), 1)
        cover_rows.append(row)
    write_csv(out / "pilot_account_coverage.csv", cover_rows)
    print("\n[대상 계정 확보율] (파일 단위. 매핑 규칙은 첫 추정)")
    for r in cover_rows:
        print(f"  {r['target']:<18} {r['확보율(%)']:>5}%")

    INTEREST_PROXIES = ("interest_exp", "fin_cost", "interest_paid_cf")
    any_int = sum(1 for e in store.values() if any(t in e for t in INTEREST_PROXIES))
    print(f"  {'이자비용 대용(하나라도)':<14} {round(100 * any_int / max(len(store), 1), 1):>5}%  ← 이자비용/금융비용/이자지급 중 하나라도 구해진 파일 비율")

    # 기업별 확보율: 실패가 '특정 기업만의 문제'인지 '전반적 규칙 문제'인지 가르는 용도(사전 고정 문서 9절 판정 방식)
    firm_rows = []
    for corp in sorted({k[0] for k in store}):
        entries = [e for k, e in store.items() if k[0] == corp]
        row = {"corp": corp, "files": len(entries)}
        for tname in TARGETS:
            row[tname] = sum(1 for e in entries if tname in e)
        row["any_interest_proxy"] = sum(1 for e in entries if any(t in e for t in INTEREST_PROXIES))
        firm_rows.append(row)
    write_csv(out / "pilot_firm_coverage.csv", firm_rows)
    no_int = [r["corp"] for r in firm_rows if r["any_interest_proxy"] == 0]
    print(f"  이자비용 대용이 한 번도 안 구해진 기업 {len(no_int)}개 / {len(firm_rows)}개 → out/pilot_firm_coverage.csv")

    var_rows = [
        {"sj_div": k[0], "account_nm": k[1], "count": v} for k, v in variants.most_common()
    ]
    write_csv(out / "pilot_account_variants.csv", var_rows)
    print(f"\n[계정명 변형] out/pilot_account_variants.csv에 {len(var_rows)}종 저장 (이 목록을 보고 매핑 사전을 고친다)")

    # (3) 분기 환원 항등성
    q_rows = []
    by_firm_year = defaultdict(dict)
    for (corp, year, fs, rep), entry in store.items():
        by_firm_year[(corp, year, fs)][rep] = entry
    for (corp, year, fs), reps in sorted(by_firm_year.items()):
        for tname in ("op_income", "interest_exp", "fin_cost"):
            q1 = reps.get("Q1", {}).get(tname)
            h1 = reps.get("H1", {}).get(tname)
            q3 = reps.get("Q3", {}).get(tname)
            fy = reps.get("FY", {}).get(tname)
            res = {"corp": corp, "year": year, "fs": fs, "target": tname}
            res["have_Q1"], res["have_H1"], res["have_Q3"], res["have_FY"] = (
                q1 is not None, h1 is not None, q3 is not None, fy is not None,
            )
            res["Q1+Q2=H1누적"] = ""
            res["H1누적+Q3=Q3누적"] = ""
            res["Q4(=FY-Q3누적)"] = ""
            if q1 and h1 and None not in (q1["amount"], h1["amount"], h1["cum"]):
                res["Q1+Q2=H1누적"] = check_close(q1["amount"] + h1["amount"], h1["cum"])
            if h1 and q3 and None not in (h1["cum"], q3["amount"], q3["cum"]):
                res["H1누적+Q3=Q3누적"] = check_close(h1["cum"] + q3["amount"], q3["cum"])
            if fy and q3 and None not in (fy["amount"], q3["cum"]):
                res["Q4(=FY-Q3누적)"] = fy["amount"] - q3["cum"]
            q_rows.append(res)
    write_csv(out / "pilot_quarterly_check.csv", q_rows)
    print("\n[분기 환원 항등성] (허용오차는 임의 기준 상대 {:.1%})".format(TOL_REL))
    for tname in ("op_income", "interest_exp", "fin_cost"):
        for col in ("Q1+Q2=H1누적", "H1누적+Q3=Q3누적"):
            vals = [r[col] for r in q_rows if r["target"] == tname and r[col]]
            print(f"  {tname:<13} {col:<16} {dict(Counter(vals))}")

    # (4) 단위·통화
    print("\n[통화 값]", dict(currencies))
    med = sorted(sum(v) / len(v) for v in asset_values.values())
    if med:
        print(f"[총자산 값의 규모(기업별 평균) 최소 {med[0]:,.0f} / 중앙 {med[len(med)//2]:,.0f} / 최대 {med[-1]:,.0f}]")
        print("  -> 값이 너무 작으면 천원/백만원 단위일 수 있으니 원 공시와 대조해 단위를 확인하세요.")
    print("\n끝. 이 결과는 '추출 가능성'만 보여줍니다. 통과 판단은 사전 고정 문서 9절의 기준으로 팀이 합니다.")


if __name__ == "__main__":
    main()
