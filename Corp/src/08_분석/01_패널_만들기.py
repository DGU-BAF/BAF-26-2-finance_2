# 이 파일은 노트북 '01_패널_만들기.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 08-01 · 패널 만들기 (분기값 → TTM → ICR) ───


# ─── 준비 — 불러오기와 경로 ───


"""정제: 저장된 응답에서 분기값·TTM·ICR 패널을 만든다. 규칙은 docs/A_결정_제안_근거표_11-05.md 8절(회귀 전 고정, 2026-11-05).

만드는 것
  1) 보고서별 추출값 캐시(outputs/07_분석/추출값_보고서별.csv): 영업이익·금융비용(3개월·누적), 현금 이자지급(누적), 자산총계
  2) 기업-분기 패널(outputs/07_분석/패널_기업분기.csv): 분기값 → TTM → ICR, Tight, E 등
  3) 표본 깔때기·점검 요약(outputs/07_분석/패널_요약.txt)

분기값(8절): Q1=1분기 3개월, Q2=반기 3개월, Q3=3분기 3개월, Q4=사업보고서 연간 − 3분기 누적.
 현금 이자지급은 누적만 있어 차분(Q2=반기−1분기, Q3=3분기−반기, Q4=사업−3분기).
규칙 ②: 같은 해 세 보고서가 같은 구분(연결/별도)일 때 (Q1+Q2 vs 반기누적), (반기누적+Q3 vs 3분기누적)의 상대차가 0.5% 초과면
 검사 A 실패 → 그 해 Q1·Q2 결측, 검사 B 실패 → 그 해 Q3·Q4 결측. (영업이익·금융비용 각각)
TTM = 연속 4분기 합(모두 있어야 함). ICR = 영업이익 TTM ÷ 금융비용 TTM (금융비용 TTM ≤ 0이면 결측).
Tight = max(0, 분기말 기준금리 − 2021Q2말 기준금리).

실행: python -X utf8 01_패널_만들기.py   (저장된 파일만 읽음, 키 필요 없음)
"""
import csv
import datetime as dt
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402
if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
    sys.stdout.reconfigure(encoding="utf-8")


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
EFIRM = config.BASE / "outputs" / "06_노출도E" / "E_기업별.csv"
EREP = config.BASE / "outputs" / "06_노출도E" / "E_보고서별.csv"
RATES = config.BASE.parent / "src" / "06_industry_analysis" / "rate_model_v1" / "inputs" / "rates.csv"
OUT = config.BASE / "outputs" / "07_분석"
FS_DIR = config.RAW / "fs"
REP_ORDER = {"Q1": 0, "H1": 1, "Q3": 2, "FY": 3}
TOL = 0.005
PAT = {k: (set(v[0].split("|")), re.compile(v[1])) for k, v in config.ACCOUNT_PATTERNS.items()
       if k in ("op_income", "fin_cost", "interest_paid_cf", "assets")}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def extract(d):
    out = {}
    for k, (sjs, pat) in PAT.items():
        hits = [x for x in d if x.get("sj_div") in sjs and pat.search(norm(x.get("account_nm"))) and num(x.get("thstrm_amount")) is not None]
        if k == "interest_paid_cf":
            if len(hits) == 1:
                out[k] = (num(hits[0]["thstrm_amount"]), None)
            else:
                out[k] = None
        elif k == "assets":
            out[k] = (num(hits[0]["thstrm_amount"]), None) if hits else None
        else:
            if hits:
                out[k] = (num(hits[0]["thstrm_amount"]), num(hits[0].get("thstrm_add_amount")))
            else:
                out[k] = None
    return out


def build_cache():
    path = OUT / "추출값_보고서별.csv"
    chosen = {}
    for r in csv.DictReader(open(LOG, encoding="utf-8-sig")):
        if r["status"] == "000":
            k = (r["corp_code"], int(r["year"]), r["report"])
            if k not in chosen or r["fs_div"] == "CFS":
                chosen[k] = r["fs_div"]
    rows = []
    for i, ((c, y, rep), fs) in enumerate(sorted(chosen.items()), 1):
        d = json.loads((FS_DIR / f"{c}_{y}_{config.REPORTS[rep]}_{fs}.json").read_text(encoding="utf-8"))["list"]
        e = extract(d)
        row = {"corp_code": c, "year": y, "report": rep, "fs": fs}
        for k in ("op_income", "fin_cost"):
            row[k + "_m3"] = e[k][0] if e[k] else None
            row[k + "_cum"] = e[k][1] if e[k] else None
        row["cf_interest"] = e["interest_paid_cf"][0] if e["interest_paid_cf"] else None
        row["assets"] = e["assets"][0] if e["assets"] else None
        rows.append(row)
        if i % 8000 == 0:
            print(f"  {i:,}개 읽음")
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def rate_at(rates, d):
    v = None
    for a, b in rates:
        if a <= d:
            v = b
    return v


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "추출값_보고서별.csv"
    df = pd.read_csv(cache, dtype={"corp_code": str}) if cache.exists() else build_cache()
    df["corp_code"] = df["corp_code"].astype(str).str.zfill(8)
    ef = pd.read_csv(EFIRM, dtype={"corp_code": str})
    ef["corp_code"] = ef["corp_code"].astype(str).str.zfill(8)
    er = pd.read_csv(EREP, dtype={"corp_code": str})
    er["corp_code"] = er["corp_code"].astype(str).str.zfill(8)
    rates = [(dt.date.fromisoformat(r["변경일자"]), float(r["기준금리"])) for r in csv.DictReader(open(RATES, encoding="utf-8-sig"))]
    base = rate_at(rates, dt.date(2021, 6, 30))
    qend = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

    rep = {}
    for r in df.itertuples(index=False):
        rep[(r.corp_code, r.year, r.report)] = r._asdict()

    def g(c, y, rp, k):
        r = rep.get((c, y, rp))
        if not r:
            return None
        v = r.get(k)
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)

    def fs(c, y, rp):
        r = rep.get((c, y, rp))
        return r["fs"] if r else None

    quarters = [(y, q) for y in range(2018, 2025) for q in (1, 2, 3, 4) if not (y == 2024 and q == 4)]
    firms = ef["corp_code"].tolist()
    stat = {"A실패": 0, "B실패": 0, "A검사": 0, "B검사": 0}
    qv = {}   # (c, item) -> {(y,q): value or None}
    for c in firms:
        for item in ("op_income", "fin_cost"):
            vals = {}
            for y in range(2018, 2025):
                q1, h1, q3, fy = (g(c, y, "Q1", item + "_m3"), g(c, y, "H1", item + "_m3"), g(c, y, "Q3", item + "_m3"), g(c, y, "FY", item + "_m3"))
                h1c, q3c = g(c, y, "H1", item + "_cum"), g(c, y, "Q3", item + "_cum")
                bad12 = bad34 = False
                f_q1, f_h1, f_q3 = fs(c, y, "Q1"), fs(c, y, "H1"), fs(c, y, "Q3")
                if None not in (q1, h1, h1c) and f_q1 == f_h1:
                    stat["A검사"] += 1
                    if abs(q1 + h1 - h1c) / max(abs(h1c), 1.0) > TOL:
                        bad12 = True
                        stat["A실패"] += 1
                if None not in (h1c, q3, q3c) and f_h1 == f_q3:
                    stat["B검사"] += 1
                    if abs(h1c + q3 - q3c) / max(abs(q3c), 1.0) > TOL:
                        bad34 = True
                        stat["B실패"] += 1
                vals[(y, 1)] = None if (q1 is None or bad12) else q1
                vals[(y, 2)] = None if (h1 is None or bad12) else h1
                vals[(y, 3)] = None if (q3 is None or bad34) else q3
                vals[(y, 4)] = None if (fy is None or q3c is None or bad34 or fs(c, y, "FY") != f_q3) else fy - q3c
            qv[(c, item)] = vals
        # 현금 이자지급(누적 차분, 합산 불일치 검사 없음)
        vals = {}
        for y in range(2018, 2025):
            a1, a2, a3, a4 = (g(c, y, "Q1", "cf_interest"), g(c, y, "H1", "cf_interest"), g(c, y, "Q3", "cf_interest"), g(c, y, "FY", "cf_interest"))
            f1, f2, f3, f4 = fs(c, y, "Q1"), fs(c, y, "H1"), fs(c, y, "Q3"), fs(c, y, "FY")
            vals[(y, 1)] = a1
            vals[(y, 2)] = (a2 - a1) if (a2 is not None and a1 is not None and f1 == f2) else None
            vals[(y, 3)] = (a3 - a2) if (a3 is not None and a2 is not None and f2 == f3) else None
            vals[(y, 4)] = (a4 - a3) if (a4 is not None and a3 is not None and f3 == f4) else None
        qv[(c, "cf")] = vals
    # 분기말 자산
    def assets_at(c, y, q):
        return g(c, y, {1: "Q1", 2: "H1", 3: "Q3", 4: "FY"}[q], "assets")

    def ttm(c, item, y, q):
        t = y * 4 + q - 1
        s = 0.0
        for k in range(4):
            yy, qq = divmod(t - k, 4)
            v = qv[(c, item)].get((yy, qq + 1))
            if v is None:
                return None
            s += v
        return s

    # 사전 사전특성 (E_보고서별의 사전기간 자산, 분기 영업이익/자산)
    pre_q = [(y, q) for y in (2019, 2020, 2021) for q in (1, 2, 3, 4) if y * 4 + q - 1 <= 2021 * 4 + 1]
    er_pre = er[er["자산이상"] == False]  # noqa: E712
    pre_assets = er_pre.groupby("corp_code")["자산총계"].mean()
    e21 = er[(er["year"] == 2021) & (er["report"] == "H1")].set_index("corp_code")["E_A"]
    e21b = er[(er["year"] == 2021) & (er["report"] == "H1")].set_index("corp_code")["E_B"]
    # 사전기간 안 연결/별도 혼재 (R4)
    pre_mix = {}
    for c in firms:
        s = {rep[(c, y, rp)]["fs"] for (cc, y, rp) in [(c, y, rp) for y in (2019, 2020, 2021) for rp in ("Q1", "H1", "Q3", "FY")] if (cc, y, rp) in rep and (y, {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}[rp]) in pre_q}
        pre_mix[c] = len(s) > 1
    rows = []
    for c in firms:
        # 사전 영업이익/자산 (분기 영업이익 ÷ 분기말 자산의 평균)
        roas = []
        for (y, q) in pre_q:
            v = qv[(c, "op_income")].get((y, q))
            a = assets_at(c, y, q)
            if v is not None and a and a > 0:
                roas.append(v / a)
        roa_pre = statistics.mean(roas) if len(roas) >= 6 else None
        for (y, q) in quarters:
            if y * 4 + q - 1 < 2019 * 4:
                continue
            t = y * 4 + q - 1
            oi, fc, cf = ttm(c, "op_income", y, q), ttm(c, "fin_cost", y, q), ttm(c, "cf", y, q)
            a = assets_at(c, y, q)
            r_end = rate_at(rates, dt.date(y, *qend[q]))
            rows.append({"corp_code": c, "year": y, "q": q, "t": t - 2019 * 4, "tight": (max(0.0, r_end - base) if t - 2019 * 4 >= 10 else 0.0),  # 2021Q3(t=10)부터만 양수, 2021Q2까지 0 (8절 수식 정정)
                         "oi_ttm": oi, "fc_ttm": fc, "cf_ttm": cf, "assets": a,
                         "icr": (oi / fc) if (oi is not None and fc is not None and fc > 0) else None,
                         "icr_cash": (oi / cf) if (oi is not None and cf is not None and cf > 0) else None,
                         "fc_a": (fc / a) if (fc is not None and a and a > 0) else None,
                         "oi_a": (oi / a) if (oi is not None and a and a > 0) else None,
                         "roa_pre": roa_pre})
    P = pd.DataFrame(rows)
    efm = ef.set_index("corp_code")
    P["업종2"] = P["corp_code"].map(efm["업종2"])
    P["법인구분"] = P["corp_code"].map(efm["현재_법인구분"])
    P["혼재"] = P["corp_code"].map(efm["연결별도_혼재"]).astype(str) == "True"
    P["E_pre_A"] = P["corp_code"].map(pd.to_numeric(efm["E_pre_A"], errors="coerce"))
    P["E_pre_B"] = P["corp_code"].map(pd.to_numeric(efm["E_pre_B(보조)"], errors="coerce"))
    P["E_pre_A_amb0"] = P["corp_code"].map(pd.to_numeric(efm["E_pre_A_amb0(민감도)"], errors="coerce"))
    P["E정의분기"] = P["corp_code"].map(efm["E정의된_분기수"])
    P["lev_pre"] = P["corp_code"].map(pd.to_numeric(efm["레버리지_pre"], errors="coerce"))
    P["ln_assets_pre"] = P["corp_code"].map(np.log(pre_assets))
    P["E_2021Q2"] = P["corp_code"].map(pd.to_numeric(e21, errors="coerce"))
    P["pre_mix"] = P["corp_code"].map(pre_mix)
    P["post"] = P["t"] >= (2021 * 4 + 2 - 2019 * 4)   # 2021Q3부터
    # 표본 깔때기
    post_n = P[P["post"]].groupby("corp_code")["icr"].apply(lambda s: s.notna().sum())
    post_n_cash = P[P["post"]].groupby("corp_code")["icr_cash"].apply(lambda s: s.notna().sum())
    P["post_icr_n"] = P["corp_code"].map(post_n)
    P["post_icr_cash_n"] = P["corp_code"].map(post_n_cash)
    P["표본_주"] = (~P["혼재"]) & (P["E정의분기"] >= 8) & (P["post_icr_n"] >= 8)
    P["표본_R4"] = (~P["pre_mix"]) & (P["E정의분기"] >= 8) & (P["post_icr_n"] >= 8)
    P.to_csv(OUT / "패널_기업분기.csv", index=False, encoding="utf-8-sig")

    firm = P.drop_duplicates("corp_code")
    L = []
    L.append(f"합산 불일치 검사(영업이익·금융비용 합): A 검사 {stat['A검사']:,}건 중 실패 {stat['A실패']:,}, B 검사 {stat['B검사']:,}건 중 실패 {stat['B실패']:,} (허용오차 0.5%)")
    L.append("[표본 깔때기] 기업 수")
    L.append(f"  본 수집 대상 {len(firm):,}")
    s1 = firm[~firm["혼재"]]
    L.append(f"  혼재 243곳 제외 후 {len(s1):,}")
    s2 = s1[s1["E정의분기"] >= 8]
    L.append(f"  E 사전 8/10 분기 이상 정의 {len(s2):,}")
    s3 = s2[s2["post_icr_n"] >= 8]
    L.append(f"  인상기 ICR 관측 8/13 이상(주 표본) {len(s3):,}")
    L.append(f"  (참고) R4 표본(사전기간 혼재 109곳만 제외) {int(firm['표본_R4'].sum()):,}")
    pm = P[P["표본_주"]]
    L.append(f"  주 표본 기업-분기 관측: {len(pm):,}개, ICR 관측 {int(pm['icr'].notna().sum()):,}개")
    L.append("[TTM·ICR 점검: 주 표본 관측]")
    L.append(f"  영업이익 TTM 있음 {pm['oi_ttm'].notna().mean():.1%}, 금융비용 TTM 있음 {pm['fc_ttm'].notna().mean():.1%}, 금융비용 TTM ≤ 0 {int((pm['fc_ttm'] <= 0).sum()):,}개")
    ic = pm["icr"].dropna()
    L.append(f"  ICR 분포: n={len(ic):,} | 1%={ic.quantile(.01):.2f} 10%={ic.quantile(.1):.2f} 중앙값={ic.median():.2f} 90%={ic.quantile(.9):.1f} 99%={ic.quantile(.99):.1f} 최대={ic.max():.1f} 최소={ic.min():.1f}")
    L.append(f"  영업이익 TTM 음수 관측 {int((pm['oi_ttm'] < 0).sum()):,}개, ICR < 1 관측 {int((ic < 1).sum()):,}개")
    L.append(f"  Tight: 사전기간 0 확인 최댓값(사전) = {pm[~pm['post']]['tight'].max():.2f}, 인상기 범위 {pm[pm['post']]['tight'].min():.2f}~{pm[pm['post']]['tight'].max():.2f}")
    text = "\n".join(L)
    print(text)
    (OUT / "패널_요약.txt").write_text(text, encoding="utf-8")
    print("저장:", OUT)


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───


# ─── 읽는 법 ───
