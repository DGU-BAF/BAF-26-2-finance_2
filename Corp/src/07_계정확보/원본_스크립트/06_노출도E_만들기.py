"""사전기간(2019Q1~2021Q2) 노출도 E를 만든다. 규칙은 docs/A_결정_제안_근거표_11-05.md의 D3·D4·D8 (에이전트 제안, 팀 미확인).

규칙 (이 스크립트를 돌린 결과를 보고 바꾸지 않는다. 바꾸면 이유와 함께 변경 기록에 적는다)
  분자(D3) = 재무상태표 '유동부채' 구간(유동부채 머리행 ~ 비유동부채 머리행) 안에서, 이름에 '차입' 또는 '사채'가 있는 행의 금액 합.
             제외 단어: 리스, 할인발행차금, 상환할증금, 대손, 이자, 미지급, 매입, 채권, 차금.  (전환사채·신주인수권부사채·유동성사채 포함)
  분모       = 자산총계.     E_A = 분자 ÷ 분모 (분기마다)
  분기 상태(D4)
    DEBT  = 유동 구간에 위 차입·사채 행이 있음(합이 0일 수도 있음) → E 정의됨
    ZERO  = 차입·사채 행도 모호한 금융부채 행도 유동 구간에 없음 → E = 0 (확정)
    AMBIG = 차입·사채 행은 없고 '금융부채'(기타·단기·유동 금융부채 등, 파생·리스·손익인식 제외) 행만 있음 → 주 분석에서 E 정의 안 함
    NOHDR = 유동/비유동 머리행이 없음 → E 정의 안 함
  기업 E_pre(D8) = DEBT·ZERO 분기의 E_A 평균(주). AMBIG 분기를 0으로 넣은 값은 민감도 열(E_pre_A_amb0)로 따로 저장.
  보조(R1) E_B = 유동 구간 차입 ÷ (유동 + 비유동 구간 차입), 총차입금이 0이면 정의 안 함. 레버리지 = 총차입금 ÷ 자산총계.
  연결(CFS) 우선. 한 기업 안에서 연결·별도가 섞인 경우는 그대로 계산하고 '혼재' 표시만 한다.

ICR·영업이익은 읽지 않는다. E와 ICR의 관계를 보지 않는다.
실행: python -X utf8 06_노출도E_만들기.py  (저장된 파일만 읽음, 키 필요 없음)
저장: outputs/06_노출도E/E_보고서별.csv, E_기업별.csv, E_요약.txt
"""
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
RESULT = config.BASE / "outputs" / "04_본수집" / "본수집_결과_기업별.csv"
OUTDIR = config.BASE / "outputs" / "06_노출도E"
FS_DIR = config.RAW / "fs"
REP_ORDER = {"Q1": 0, "H1": 1, "Q3": 2, "FY": 3}
# 2026-11-05 보정: '유동성장기부채'(사전 고정 5절·config.ACCOUNT_PATTERNS에 원래 있던 이름)와 '당좌차월'을 추가.
# 1차 실행(07_E_검산 점검 3·4)에서 이 이름이 유동 구간 1,514개 보고서에 있는데 규칙에서 빠져 E가 과소 계산된 것을 발견. E와 ICR의 관계는 보지 않은 상태에서의 수정.
DEBT = re.compile(r"차입|사채|장기부채|당좌차월")
EXCL = re.compile(r"리스|할인발행차금|상환할증금|대손|이자|미지급|매입|채권|차금")
AMBIG = re.compile(r"금융부채")
AMBIG_EXCL = re.compile(r"파생|리스|손익|매매")


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def is_pre(y, rep):
    return (2019, 0) <= (y, REP_ORDER[rep]) <= (2021, 1)


def sections(bs):
    hdr = []
    for i, r in enumerate(bs):
        nm, aid = norm(r["account_nm"]), r.get("account_id", "")
        if nm == "유동부채" or aid == "ifrs-full_CurrentLiabilities":
            hdr.append((i, "C"))
        elif nm == "비유동부채" or aid == "ifrs-full_NoncurrentLiabilities":
            hdr.append((i, "N"))
        elif nm == "부채총계" or aid == "ifrs-full_Liabilities":
            hdr.append((i, "T"))
    has = any(t == "C" for _, t in hdr) and any(t == "N" for _, t in hdr)
    sec, cur, hi = {}, "O", 0
    for i in range(len(bs)):
        while hi < len(hdr) and hdr[hi][0] <= i:
            cur = {"C": "C", "N": "N", "T": "O"}[hdr[hi][1]]
            hi += 1
        sec[i] = cur
    return sec, has


def dedup(rows):
    """같은 차입이 '합계 행'과 '세부 행'으로 함께 적힌 경우의 이중 계산을 막는다. (2026-11-05 보정 2: 07_E_검산 점검 2에서 발견)
    규칙 1) 어떤 행의 금액이 바로 뒤 연속 1~5개 차입 행의 합과 같으면(±1원 또는 0.001%) 그 행은 합계 행이므로 뺀다.
    규칙 2) 남은 행 중 이름이 같은 연속 두 행에서 앞 행에 표준 계정코드가 있고 뒤 행에 없으면(표준계정코드 미사용) 뒤 행을 뺀다(액면·장부 이중 표기).
    rows: [(이름, 금액, account_id)] → (남은 행, 뺀 행 수)"""
    drop = set()
    n = len(rows)
    for i in range(n):
        amt = rows[i][1]
        if amt <= 0:
            continue
        s = 0.0
        for k in range(i + 1, min(n, i + 6)):
            s += rows[k][1]
            if abs(s - amt) <= max(1.0, amt * 1e-5):
                drop.add(i)
                break
    kept = [r for i, r in enumerate(rows) if i not in drop]
    drop2 = set()
    for i in range(len(kept) - 1):
        a, b = kept[i], kept[i + 1]
        if a[0] == b[0] and not a[2].startswith("-") and b[2].startswith("-"):
            drop2.add(i + 1)
    kept = [r for i, r in enumerate(kept) if i not in drop2]
    return kept, len(drop) + len(drop2)


def one_report(d):
    bs = sorted([x for x in d if x.get("sj_div") == "BS"], key=lambda x: int(x["ord"]))
    sec, has = sections(bs)
    assets = next((to_num(x["thstrm_amount"]) for x in bs if norm(x["account_nm"]) == "자산총계"), None)
    out = {"assets": assets, "num_C": 0.0, "num_N": 0.0, "n_debt_rows_C": 0, "n_ambig_rows_C": 0}
    if not has:
        out["state"] = "NOHDR"
        return out
    rows_c, rows_n = [], []
    for i, x in enumerate(bs):
        nm = norm(x["account_nm"])
        amt = to_num(x["thstrm_amount"])
        aid = x.get("account_id", "")
        if sec[i] == "C":
            if DEBT.search(nm) and not EXCL.search(nm):
                rows_c.append((nm, amt or 0.0, aid))
            elif AMBIG.search(nm) and not AMBIG_EXCL.search(nm) and not DEBT.search(nm):
                out["n_ambig_rows_C"] += 1
        elif sec[i] == "N":
            if DEBT.search(nm) and not EXCL.search(nm):
                rows_n.append((nm, amt or 0.0, aid))
    rows_c, dc = dedup(rows_c)
    rows_n, dn = dedup(rows_n)
    out["n_debt_rows_C"] = len(rows_c)
    out["num_C"] = sum(a for _, a, _ in rows_c)
    out["num_N"] = sum(a for _, a, _ in rows_n)
    out["n_dedup"] = dc + dn
    out["state"] = "DEBT" if out["n_debt_rows_C"] else ("AMBIG" if out["n_ambig_rows_C"] else "ZERO")
    return out


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def main():
    firms = {r["corp_code"]: r for r in csv.DictReader(open(RESULT, encoding="utf-8-sig"))}
    chosen = {}
    for r in csv.DictReader(open(LOG, encoding="utf-8-sig")):
        if r["status"] == "000" and is_pre(int(r["year"]), r["report"]):
            k = (r["corp_code"], int(r["year"]), r["report"])
            if k not in chosen or r["fs_div"] == "CFS":
                chosen[k] = r["fs_div"]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    rep_rows = []
    for i, ((c, y, rep), fs) in enumerate(sorted(chosen.items()), 1):
        d = json.loads((FS_DIR / f"{c}_{y}_{config.REPORTS[rep]}_{fs}.json").read_text(encoding="utf-8"))["list"]
        o = one_report(d)
        st, a = o["state"], o["assets"]
        valid_assets = a is not None and a > 0
        e_a = None
        if st in ("DEBT", "ZERO") and valid_assets:
            e_a = (o["num_C"] / a) if st == "DEBT" else 0.0
        tot = o["num_C"] + o["num_N"]
        e_b = (o["num_C"] / tot) if (st in ("DEBT", "ZERO") and tot > 0) else None
        lev = (tot / a) if (st != "NOHDR" and valid_assets) else None
        rep_rows.append({"corp_code": c, "year": y, "report": rep, "fs_div": fs, "상태": st,
                         "자산총계": a, "유동차입합": o["num_C"], "비유동차입합": o["num_N"],
                         "유동차입행수": o["n_debt_rows_C"], "중복제거행수": o.get("n_dedup", 0), "모호금융부채행수": o["n_ambig_rows_C"],
                         "E_A": e_a, "E_B": e_b, "레버리지": lev, "자산이상": (not valid_assets)})
        if i % 4000 == 0:
            print(f"  {i:,}개 읽음")
    cols = list(rep_rows[0].keys())
    with open(OUTDIR / "E_보고서별.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rep_rows)

    by = defaultdict(list)
    for r in rep_rows:
        by[r["corp_code"]].append(r)
    frows = []
    for c, f in firms.items():
        rs = by.get(c, [])
        df = [r for r in rs if r["E_A"] is not None]
        st = Counter(r["상태"] for r in rs)
        amb0 = [r["E_A"] if r["E_A"] is not None else (0.0 if r["상태"] == "AMBIG" and not r["자산이상"] else None) for r in rs]
        amb0 = [x for x in amb0 if x is not None]
        eb = [r["E_B"] for r in rs if r["E_B"] is not None]
        lev = [r["레버리지"] for r in rs if r["레버리지"] is not None]
        n_def = len(df)
        if n_def == 0:
            cls = "정의불가"
        elif all(r["상태"] == "DEBT" for r in df):
            cls = "차입있음(정의된 전 분기)"
        elif all(r["상태"] == "ZERO" for r in df):
            cls = "0확정(정의된 전 분기)"
        else:
            cls = "혼합"
        frows.append({"corp_code": c, "회사명": f["회사명"], "현재_법인구분": f["현재_법인구분"], "업종2": f["업종코드"][:2],
                      "연결별도_혼재": f["연결별도_혼재"], "사전기간_보고서수": len(rs), "E정의된_분기수": n_def,
                      "상태_DEBT": st["DEBT"], "상태_ZERO": st["ZERO"], "상태_AMBIG": st["AMBIG"], "상태_NOHDR": st["NOHDR"],
                      "E_pre_A": statistics.mean([r["E_A"] for r in df]) if df else "",
                      "E_pre_A_amb0(민감도)": statistics.mean(amb0) if amb0 else "",
                      "E_pre_B(보조)": statistics.mean(eb) if eb else "",
                      "레버리지_pre": statistics.mean(lev) if lev else "",
                      "기업분류": cls, "모호분기_있음": st["AMBIG"] > 0})
    with open(OUTDIR / "E_기업별.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(frows[0].keys()))
        w.writeheader()
        w.writerows(frows)

    L = []
    N = len(rep_rows)
    L.append(f"사전기간 보고서 {N:,}개(기업 {len(frows):,}곳)")
    c = Counter(r["상태"] for r in rep_rows)
    L.append("분기 상태: " + ", ".join(f"{k} {v:,}({v/N:.1%})" for k, v in c.most_common()))
    L.append(f"자산총계가 없거나 0 이하: {sum(1 for r in rep_rows if r['자산이상']):,}건")
    over = sum(1 for r in rep_rows if r["E_A"] is not None and r["E_A"] > 1)
    L.append(f"E_A > 1(유동 차입이 자산보다 큼): {over:,}건")
    L.append("")
    L.append("[A8 목록 1] 사전기간 E를 만들 수 있는 기업")
    nd = Counter(r["E정의된_분기수"] for r in frows)
    L.append("  E가 정의된 분기 수별 기업 수: " + ", ".join(f"{k}개:{nd[k]}" for k in sorted(nd)))
    L.append(f"  E가 정의된 분기가 1개 이상인 기업 {sum(1 for r in frows if r['E정의된_분기수']>=1):,}곳 / 정의불가 {nd[0]}곳")
    cl = Counter((r["기업분류"], r["모호분기_있음"]) for r in frows)
    L.append("  기업 분류(모호 분기 여부):")
    for (k, a), v in sorted(cl.items()):
        L.append(f"    {k} / 모호분기 {'있음' if a else '없음'}: {v:,}곳")
    L.append("")
    L.append("[분포] 기업별 E_pre_A (정의된 기업만)")
    vals = [r["E_pre_A"] for r in frows if r["E_pre_A"] != ""]
    L.append(f"  n={len(vals):,} | 평균={statistics.mean(vals):.3f} | 10%={q(vals,.1):.3f} 25%={q(vals,.25):.3f} 중앙값={statistics.median(vals):.3f} 75%={q(vals,.75):.3f} 90%={q(vals,.9):.3f} 최대={max(vals):.3f}")
    L.append(f"  E_pre_A = 0인 기업: {sum(1 for v in vals if v == 0):,}곳 ({sum(1 for v in vals if v==0)/len(vals):.1%})")
    L.append("  법인구분별(정의된 기업): ")
    g = defaultdict(list)
    for r in frows:
        if r["E_pre_A"] != "":
            g[r["현재_법인구분"]].append(r["E_pre_A"])
    for k, v in sorted(g.items()):
        L.append(f"    {k}: n={len(v)} 중앙값={statistics.median(v):.3f} 평균={statistics.mean(v):.3f}")
    L.append("")
    L.append("[A8 목록 3] E를 못 만드는/애매한 기업이 몰리는가")
    tot_g = Counter(r["현재_법인구분"] for r in frows)
    und_g = Counter(r["현재_법인구분"] for r in frows if r["E정의된_분기수"] == 0)
    amb_g = Counter(r["현재_법인구분"] for r in frows if r["모호분기_있음"])
    for k in sorted(tot_g):
        L.append(f"  {k}: {tot_g[k]}곳 | 정의불가 {und_g[k]}({und_g[k]/tot_g[k]:.1%}) | 모호 분기 있음 {amb_g[k]}({amb_g[k]/tot_g[k]:.1%})")
    ind_t = Counter(r["업종2"] for r in frows)
    ind_a = Counter(r["업종2"] for r in frows if r["모호분기_있음"] or r["E정의된_분기수"] == 0)
    L.append("  업종(앞 2자리)별 '모호 분기 있음 또는 정의불가' 비율 (기업 10곳 이상 업종):")
    for k in sorted(ind_t):
        if ind_t[k] >= 10:
            L.append(f"    {k}: {ind_a[k]}/{ind_t[k]} ({ind_a[k]/ind_t[k]:.0%})")
    mx = Counter(r["연결별도_혼재"] for r in frows)
    L.append("")
    L.append(f"연결·별도 혼재 기업 {mx['True']}곳(사전기간 분기 상태가 섞여 있을 수 있음). 주 분석은 혼재 기업 제외(D6)이므로 아래 수는 참고:")
    main_f = [r for r in frows if r["연결별도_혼재"] != "True"]
    L.append(f"  혼재 제외 후 {len(main_f):,}곳 중 E 정의된 기업 {sum(1 for r in main_f if r['E정의된_분기수']>=1):,}곳, 모호 분기 있음 {sum(1 for r in main_f if r['모호분기_있음']):,}곳")
    ntxt = "\n".join(L)
    print(ntxt)
    (OUTDIR / "E_요약.txt").write_text(ntxt, encoding="utf-8")
    print("저장:", OUTDIR)


if __name__ == "__main__":
    main()
