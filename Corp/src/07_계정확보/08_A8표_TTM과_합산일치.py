# 이 파일은 노트북 '08_A8표_TTM과_합산일치.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 07-08 · A8 판단표 2·4번 (TTM 가능 분기 수, 분기 합산 불일치) ───


# ─── 준비 — 불러오기와 경로 ───


"""A8 판단용 표 2번(ICR 분모를 만들 수 있는 기업)과 4번(분기 합산 불일치).  (3번 쏠림은 06 결과에 있음)

ICR·E 관계는 보지 않는다. ICR 값 자체를 계산하지 않는다.

[표 2] 후행 4분기 합(TTM)을 만들 수 있는 분기 수 (존재 여부만 사용, 금액은 읽지 않음: outputs/05_계정확보/계정확보_보고서별.csv의 확보 여부 사용)
  분기값이 있다고 보는 조건
    손익 계정(영업이익·금융비용): Q1=1분기 보고서에 계정 있음 / Q2=반기 보고서 / Q3=3분기 보고서 /
                                  Q4=사업보고서에 계정 있음 + 3분기 보고서에 '누적 칸'이 있음(Q4 = 연간 − 3분기 누적)
    현금 이자지급(누적만 있음): Q1=1분기 / Q2=반기와 1분기 둘 다 / Q3=3분기와 반기 둘 다 / Q4=사업과 3분기 둘 다
  TTM(t) 가능 = t를 포함한 연속 4분기의 분기값이 모두 있음. 대상 시점: 사전기간 2019Q1~2021Q2(10개), 인상기 2021Q3~2024Q3(13개)
[표 4] 분기 합산 불일치 (금액을 읽음. 영업이익·금융비용만)
  검사 A: 1분기 3개월 값 + 반기 3개월 값  vs 반기 누적 값
  검사 B: 반기 누적 값 + 3분기 3개월 값   vs 3분기 누적 값
  같은 기업·연도에서 세 보고서가 모두 같은 구분(연결/별도)일 때만 검사. 허용오차 0.5%는 파일럿에서 정한 임의 기준(공식·학술 기준 아님)이므로 5% 구간도 같이 보인다.
저장: outputs/06_노출도E/A8_TTM가능분기수.csv, A8_합산불일치_요약.txt
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402
if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
    sys.stdout.reconfigure(encoding="utf-8")


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


OUT = config.BASE / "outputs" / "06_노출도E"
ACC = config.BASE / "outputs" / "05_계정확보" / "계정확보_보고서별.csv"
LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
RES = config.BASE / "outputs" / "04_본수집" / "본수집_결과_기업별.csv"
FS_DIR = config.RAW / "fs"
PAT = {k: (set(config.ACCOUNT_PATTERNS[k][0].split("|")), re.compile(config.ACCOUNT_PATTERNS[k][1])) for k in ("op_income", "fin_cost")}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def qidx(y, q):
    return y * 4 + (q - 1)


def table2():
    flags = defaultdict(dict)   # corp -> (year, rep) -> row
    for r in csv.DictReader(open(ACC, encoding="utf-8-sig")):
        flags[r["corp_code"]][(int(r["year"]), r["report"])] = r
    firms = {r["corp_code"]: r for r in csv.DictReader(open(RES, encoding="utf-8-sig"))}

    def has(c, y, rep, k):
        r = flags[c].get((y, rep))
        return bool(r) and r[k] == "True"

    def cum(c, y, rep, k):
        r = flags[c].get((y, rep))
        return bool(r) and r.get(k + "_누적칸") == "True"

    def qval_is(c, k, y, q):
        if q == 1:
            return has(c, y, "Q1", k)
        if q == 2:
            return has(c, y, "H1", k)
        if q == 3:
            return has(c, y, "Q3", k)
        return has(c, y, "FY", k) and cum(c, y, "Q3", k)

    def qval_cf(c, y, q):
        k = "interest_paid_cf"
        if q == 1:
            return has(c, y, "Q1", k)
        if q == 2:
            return has(c, y, "H1", k) and has(c, y, "Q1", k)
        if q == 3:
            return has(c, y, "Q3", k) and has(c, y, "H1", k)
        return has(c, y, "FY", k) and has(c, y, "Q3", k)

    pre = [(y, q) for y in (2019, 2020, 2021) for q in (1, 2, 3, 4) if qidx(y, q) <= qidx(2021, 2)]
    post = [(y, q) for y in (2021, 2022, 2023, 2024) for q in (1, 2, 3, 4) if qidx(2021, 3) <= qidx(y, q) <= qidx(2024, 3)]
    rows = []
    for c in firms:
        avail = {}
        for nm, fn in (("op", lambda y, q: qval_is(c, "op_income", y, q)),
                       ("fin", lambda y, q: qval_is(c, "fin_cost", y, q)),
                       ("cf", lambda y, q: qval_cf(c, y, q))):
            avail[nm] = {(y, q): fn(y, q) for y in range(2018, 2025) for q in (1, 2, 3, 4)}

        def ttm(nm_list, y, q):
            for k in range(4):
                t = qidx(y, q) - k
                yy, qq = divmod(t, 4)
                qq += 1
                if not all(avail[n].get((yy, qq), False) for n in nm_list):
                    return False
            return True
        row = {"corp_code": c, "회사명": firms[c]["회사명"], "현재_법인구분": firms[c]["현재_법인구분"]}
        for lab, ns in (("영업이익+금융비용", ["op", "fin"]), ("영업이익+현금이자지급", ["op", "cf"])):
            row[f"사전_{lab}"] = sum(ttm(ns, y, q) for y, q in pre)
            row[f"인상기_{lab}"] = sum(ttm(ns, y, q) for y, q in post)
        rows.append(row)
    with open(OUT / "A8_TTM가능분기수.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    L = [f"[표 2] TTM 가능 분기 수 분포 (기업 {len(rows):,}곳; 사전기간 {len(pre)}개 분기, 인상기 {len(post)}개 분기)"]
    for lab in ("영업이익+금융비용", "영업이익+현금이자지급"):
        for per, n in (("사전", len(pre)), ("인상기", len(post))):
            c = Counter(r[f"{per}_{lab}"] for r in rows)
            full = c[n]
            zero = c[0]
            L.append(f"  {lab} / {per}: 전부 가능 {full:,}곳, 하나도 없음 {zero:,}곳, 나머지 {len(rows)-full-zero:,}곳")
            L.append("      분포(가능한 분기 수:기업 수) " + ", ".join(f"{k}:{c[k]}" for k in sorted(c)))
    both = sum(1 for r in rows if r["사전_영업이익+금융비용"] == len(pre) and r["인상기_영업이익+금융비용"] == len(post))
    L.append(f"  영업이익+금융비용으로 사전기간·인상기 모든 분기의 TTM이 가능한 기업: {both:,}곳")
    bothcf = sum(1 for r in rows if r["사전_영업이익+현금이자지급"] == len(pre) and r["인상기_영업이익+현금이자지급"] == len(post))
    L.append(f"  영업이익+현금 이자지급으로 같은 조건: {bothcf:,}곳")
    return L


def read_vals():
    chosen = {}
    for r in csv.DictReader(open(LOG, encoding="utf-8-sig")):
        if r["status"] == "000" and r["report"] in ("Q1", "H1", "Q3"):
            k = (r["corp_code"], int(r["year"]), r["report"])
            if k not in chosen or r["fs_div"] == "CFS":
                chosen[k] = r["fs_div"]
    vals = {}
    for i, ((c, y, rep), fs) in enumerate(sorted(chosen.items()), 1):
        d = json.loads((FS_DIR / f"{c}_{y}_{config.REPORTS[rep]}_{fs}.json").read_text(encoding="utf-8"))["list"]
        rec = {"fs": fs}
        for k, (sjs, pat) in PAT.items():
            hit = next((x for x in d if x.get("sj_div") in sjs and pat.search(norm(x.get("account_nm"))) and num(x.get("thstrm_amount")) is not None), None)
            rec[k] = (num(hit["thstrm_amount"]), num(hit.get("thstrm_add_amount"))) if hit else None
        vals[(c, y, rep)] = rec
        if i % 8000 == 0:
            print(f"  {i:,}개 읽음")
    return vals


def table4(vals):
    firms = {r["corp_code"]: r for r in csv.DictReader(open(RES, encoding="utf-8-sig"))}
    L = ["", "[표 4] 분기 합산 불일치 (허용오차 0.5%는 파일럿의 임의 기준)"]
    stat = {}
    for k in ("op_income", "fin_cost"):
        for chk in ("A", "B"):
            stat[(k, chk)] = Counter()
    by_grp = defaultdict(Counter)
    firm_bad = defaultdict(int)
    corps = {c for (c, _, _) in vals}
    for c in corps:
        for y in range(2018, 2025):
            q1, h1, q3 = vals.get((c, y, "Q1")), vals.get((c, y, "H1")), vals.get((c, y, "Q3"))
            for k in ("op_income", "fin_cost"):
                # A
                if q1 and h1 and q1["fs"] == h1["fs"] and q1[k] and h1[k] and h1[k][1] is not None:
                    lhs, rhs = q1[k][0] + h1[k][0], h1[k][1]
                    stat[(k, "A")]["검사"] += 1
                    gap = abs(lhs - rhs) / max(abs(rhs), 1.0)
                    if gap > 0.005:
                        stat[(k, "A")][">0.5%"] += 1
                        firm_bad[c] += 1
                        by_grp[firms[c]["현재_법인구분"]][k + "A>0.5%"] += 1
                    if gap > 0.05:
                        stat[(k, "A")][">5%"] += 1
                    by_grp[firms[c]["현재_법인구분"]][k + "A검사"] += 1
                else:
                    stat[(k, "A")]["검사불가"] += 1
                # B
                if h1 and q3 and h1["fs"] == q3["fs"] and h1[k] and q3[k] and h1[k][1] is not None and q3[k][1] is not None:
                    lhs, rhs = h1[k][1] + q3[k][0], q3[k][1]
                    stat[(k, "B")]["검사"] += 1
                    gap = abs(lhs - rhs) / max(abs(rhs), 1.0)
                    if gap > 0.005:
                        stat[(k, "B")][">0.5%"] += 1
                        firm_bad[c] += 1
                        by_grp[firms[c]["현재_법인구분"]][k + "B>0.5%"] += 1
                    if gap > 0.05:
                        stat[(k, "B")][">5%"] += 1
                    by_grp[firms[c]["현재_법인구분"]][k + "B검사"] += 1
                else:
                    stat[(k, "B")]["검사불가"] += 1
    for (k, chk), c in stat.items():
        n = c["검사"]
        L.append(f"  {k} 검사 {chk}: 검사 {n:,}건 | 0.5% 초과 {c['>0.5%']:,}건({c['>0.5%']/max(n,1):.1%}) | 5% 초과 {c['>5%']:,}건({c['>5%']/max(n,1):.1%}) | 검사불가 {c['검사불가']:,}건")
    L.append(f"  0.5% 초과가 한 번이라도 있는 기업: {sum(1 for v in firm_bad.values() if v>0):,}곳 / {len(corps):,}곳")
    L.append("  법인구분별 0.5% 초과 비율(영업이익·금융비용, 검사 A+B 합):")
    for g, c in sorted(by_grp.items()):
        bad = sum(v for k, v in c.items() if k.endswith(">0.5%"))
        tot = sum(v for k, v in c.items() if k.endswith("검사"))
        L.append(f"    {g}: {bad:,}/{tot:,} ({bad/max(tot,1):.1%})")
    return L


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    L = table2()
    print("\n".join(L))
    vals = read_vals()
    L += table4(vals)
    text = "\n".join(L)
    print("\n".join(L[-14:]))
    (OUT / "A8_합산불일치_요약.txt").write_text(text, encoding="utf-8")
    print("저장:", OUT)


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───
