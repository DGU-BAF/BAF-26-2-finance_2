"""파이프라인 M0~M10 (A_분석_파이프라인_v1대응_11-05.html에서 고정한 목록 그대로). 전부 사후 탐색.
실행: python -X utf8 11_모듈.py M0 [M1 ...]
구현 세부(실행 전 고정): M8의 핵심 6개 = {M1, M2, M3} × {asinh(ICR), 1{ICR<1}}의 E×Tight. 가짜 긴축 시점 t0∈{2,4,6,8}(2019Q3·2020Q1·2020Q3·2021Q1):
Tight_p(t)=Tight(t−t0+10) (t≥t0), 사전기간(t≤9)만. 비용률은 주 표본에서 1%·99% 절단. 영업이익 수준은 asinh(영업이익 TTM/1억원).
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from lib import FE, LABEL, MOD, OUT, WORSE, add_T, config, finish, fit, holm, load_panel, rows_from, wcr_p  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
T3 = ["T1", "T2", "T3"]


def prep_S(P):
    S = P[P["표본_주"]].copy()
    lo, hi = S["icr"].quantile(.01), S["icr"].quantile(.99)
    S["icr_w"] = S["icr"].clip(lo, hi)
    S = add_T(S)
    S["size_x"] = S["ln_assets_pre"] * S["tight"]
    S["lev_x"] = S["lev_pre"] * S["tight"]
    S["roa_x"] = S["roa_pre"] * S["tight"]
    S["Ex19"] = S["E_2019"] * S["tight"]
    S["Ex21"] = S["E_2021Q2"] * S["tight"]
    if "cost_rate" in S:
        c = S["cost_rate"]
        S["cost_w"] = c.clip(c.quantile(.01), c.quantile(.99))
    return S


def show(R, cols=("사양", "결과변수", "변수", "계수", "표준오차", "p", "Holm_p", "관측", "기업"), maxrows=60):
    for r in R.head(maxrows).itertuples(index=False):
        d = r._asdict()
        hp = d.get("Holm_p")
        hp = "" if pd.isna(hp) else f" Holm={hp:.3f}"
        print(f"  {str(d['사양'])[:40]:40s} {LABEL.get(d['결과변수'], d['결과변수'])[:16]:16s} {str(d['변수'])[:20]:20s} {d['계수']: .4f} ({d['표준오차']:.4f}) p={d['p']:.3f}{hp} N={d['관측']:,} G={d['기업']:,}")


# ───────────────────────── M0 ─────────────────────────
def m0(P):
    import statsmodels.formula.api as smf
    spec = importlib.util.spec_from_file_location("reg", Path(__file__).resolve().parent / "02_회귀.py")
    reg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reg)
    S = prep_S(P)
    L, ok = [], True
    a = fit(S, "T1", ["Ex"], FE)
    b = reg.fe_ols(S, "T1", ["Ex"], FE)
    L.append(f"① 구현 대조: lib.fit β={a['beta'][0]:.8f}, 02_회귀 fe_ols β={b['beta'][0]:.8f}, 차이 {abs(a['beta'][0]-b['beta'][0]):.1e}; se {a['se'][0]:.5f} vs {b['se'][0]:.5f}")
    ok &= abs(a["beta"][0] - b["beta"][0]) < 1e-8 and abs(a["se"][0] - b["se"][0]) < 1e-8
    sub = S[S["corp_code"].isin(S["corp_code"].drop_duplicates().sample(150, random_state=3))]
    d = sub[["T1", "Ex", "corp_code", "ind_t"]].dropna()
    while True:
        keep = np.ones(len(d), bool)
        for f in FE:
            keep &= d[f].map(d[f].value_counts()).values > 1
        if keep.all():
            break
        d = d[keep]
    sm = smf.ols("T1 ~ Ex + C(corp_code) + C(ind_t)", data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["corp_code"])[0]})
    mine = fit(sub, "T1", ["Ex"], FE)
    L.append(f"   statsmodels(150개 기업 부분표본): β={sm.params['Ex']:.6f} vs {mine['beta'][0]:.6f}, se 비율 {mine['se'][0]/sm.bse['Ex']:.3f}")
    ok &= abs(sm.params["Ex"] - mine["beta"][0]) < 1e-6 and 0.9 < mine["se"][0] / sm.bse["Ex"] < 1.05
    # wild bootstrap 검증(합성): β=0이면 p가 크고 β=0.7이면 작아야 함
    rng = np.random.default_rng(5)
    F, T, I = 60, 12, 5
    firm = np.repeat(np.arange(F), T); t = np.tile(np.arange(T), F)
    ind = np.repeat(rng.integers(0, I, F), T)
    x = rng.normal(size=F * T) + 0.2 * (firm % 5)
    base = rng.normal(size=F)[firm] + rng.normal(size=I * T).reshape(I, T)[ind, t]
    for beta in (0.0, 0.7):
        y = beta * x + base + rng.normal(size=F * T)
        dd = pd.DataFrame({"y": y, "x": x, "corp_code": firm.astype(str), "ind_t": [f"{p}_{q}" for p, q in zip(ind, t)]})
        f = fit(dd, "y", ["x"], FE, keep_internals=True)
        p_w, th = wcr_p(f, 0, B=1999)
        L.append(f"   wild bootstrap 검증(합성, 참값 β={beta}): 추정 {f['beta'][0]:.3f}, 모수 p={f['p'][0]:.3f}, WCR p={p_w:.3f}")
        ok &= (p_w > 0.05) if beta == 0.0 else (p_w < 0.05)
    # ② 원본 대조
    chosen = {}
    import csv as _csv
    for r in _csv.DictReader(open(config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv", encoding="utf-8-sig")):
        if r["status"] == "000":
            k = (r["corp_code"], int(r["year"]), r["report"])
            if k not in chosen or r["fs_div"] == "CFS":
                chosen[k] = r["fs_div"]

    def val(c, y, rep, item):
        fs = chosen.get((c, y, rep))
        if not fs:
            return None, None
        dj = json.loads((config.RAW / "fs" / f"{c}_{y}_{config.REPORTS[rep]}_{fs}.json").read_text(encoding="utf-8"))["list"]
        pat = re.compile(r"^영업이익|^영업손" if item == "oi" else r"^(금융비용|금융원가)")
        for x in dj:
            if x.get("sj_div") in ("IS", "CIS") and pat.search(re.sub(r"\s+", "", x.get("account_nm", ""))) and str(x.get("thstrm_amount", "")).strip() not in ("", "-"):
                m3 = float(str(x["thstrm_amount"]).replace(",", ""))
                try:
                    cum = float(str(x.get("thstrm_add_amount", "")).replace(",", ""))
                except ValueError:
                    cum = None
                return m3, cum
        return None, None

    def qv(c, y, q, item):
        if q == 1:
            return val(c, y, "Q1", item)[0]
        if q == 2:
            return val(c, y, "H1", item)[0]
        if q == 3:
            return val(c, y, "Q3", item)[0]
        fy = val(c, y, "FY", item)[0]
        q3c = val(c, y, "Q3", item)[1]
        return None if fy is None or q3c is None else fy - q3c

    samp = S[S["oi_ttm"].notna() & S["fc_ttm"].notna()].sample(20, random_state=7)
    bad = 0
    for r in samp.itertuples():
        tt = r.year * 4 + r.q - 1
        res = []
        for item, tgt in (("oi", r.oi_ttm), ("fc", r.fc_ttm)):
            tot = 0.0
            miss = False
            for k in range(4):
                yy, qq = divmod(tt - k, 4)
                v = qv(r.corp_code, yy, qq + 1, item)
                if v is None:
                    miss = True
                    break
                tot += v
            res.append(None if miss else abs(tot - tgt))
        flag = any(x is None or x > 1.0 for x in res)
        bad += flag
    L.append(f"② 원본 대조: 무작위 20개 기업-분기의 영업이익·금융비용 TTM을 원본 응답에서 다른 코드로 다시 계산 → 불일치 {bad}개 (허용 1원)")
    ok &= bad == 0
    # ③ 합산 항등성
    X = pd.read_csv(OUT / "추출값_보고서별.csv", dtype={"corp_code": str})
    X["corp_code"] = X["corp_code"].str.zfill(8)
    firms = set(S["corp_code"])
    X = X[X["corp_code"].isin(firms)]
    cnt = {"op": [0, 0], "fc": [0, 0]}
    for (c, y), g in X[X["year"].between(2019, 2023)].groupby(["corp_code", "year"]):
        g = g.set_index("report")
        if not {"Q1", "H1", "Q3"} <= set(g.index) or len({g.loc[r, "fs"] for r in ("Q1", "H1", "Q3")}) > 1:
            continue
        for k, key in (("op", "op_income"), ("fc", "fin_cost")):
            try:
                s = g.loc["Q1", key + "_m3"] + g.loc["H1", key + "_m3"] + g.loc["Q3", key + "_m3"]
                cum = g.loc["Q3", key + "_cum"]
            except KeyError:
                continue
            if pd.notna(s) and pd.notna(cum):
                cnt[k][0] += 1
                cnt[k][1] += abs(s - cum) / max(abs(cum), 1.0) > 0.005
    L.append(f"③ 합산 항등성(주 표본 기업, 2019~2023): 영업이익 {cnt['op'][1]}/{cnt['op'][0]}건, 금융비용 {cnt['fc'][1]}/{cnt['fc'][0]}건이 0.5% 초과(이 불일치 분기는 규칙 ②로 결측 처리됨)")
    L.append(f"\n[M0 판정] {'통과' if ok else '실패 — 멈춤'}")
    text = "\n".join(L)
    print(text)
    (MOD / "M0_점검.md").write_text("# M0 점검\n\n```\n" + text + "\n```\n", encoding="utf-8")
    return ok


# ───────────────────────── M1 ─────────────────────────
def m1(P):
    S = prep_S(P)
    rows = []
    for y in ["icr", "icr_w", "T1", "T2", "T3"]:
        r = fit(S, y, ["Ex"], ["corp_code", "t"])
        rows += rows_from(r, "M1", "M1 기업FE+분기FE", ["E×Tight"], "M1")
        r = fit(S, y, ["Ex"], FE)
        rows += rows_from(r, "M1", "M2 기업FE+업종×분기FE", ["E×Tight"], "M1")
        r = fit(S, y, ["Ex", "size_x", "lev_x", "roa_x"], FE)
        rows += rows_from(r, "M1", "M3 M2+사전특성×Tight", ["E×Tight", "ln자산×Tight", "레버리지×Tight", "영업이익/자산×Tight"], "M1")
    R = finish(rows, "M1", "결과")
    print("M1 결과 (E×Tight만)")
    show(R[R["변수"] == "E×Tight"])
    return R


# ───────────────────────── M2 ─────────────────────────
def m2(P):
    S = prep_S(P)
    rows = []
    S2 = S[~S["t"].isin([10, 11])]
    for y in T3:
        rows += rows_from(fit(S2, y, ["Ex"], FE), "M2", "전환기(2021Q3~Q4) 제외", ["E×Tight"], "M2")
    for nm, col in (("E=2019년 평균", "Ex19"), ("E=2021Q2 단독", "Ex21")):
        for y in T3:
            rows += rows_from(fit(S, y, [col], FE), "M2", nm, [nm], "M2")
    inds = sorted(S["업종2"].unique())
    loo = []
    for code in inds:
        Si = S[S["업종2"] != code]
        for y in T3:
            r = fit(Si, y, ["Ex"], FE)
            rows += rows_from(r, "M2", f"업종 제외 {code}", ["E×Tight"], None, note=f"제외 업종 {code}")
            loo.append({"업종": code, "y": y, "b": r["beta"][0], "se": r["se"][0], "p": r["p"][0]})
    R = finish(rows, "M2", "결과")
    L = pd.DataFrame(loo)
    fig, axes = plt.subplots(1, 3, figsize=(13, 5))
    base = {y: fit(S, y, ["Ex"], FE)["beta"][0] for y in T3}
    for ax, y in zip(axes, T3):
        g = L[L["y"] == y].sort_values("b")
        ax.errorbar(g["b"], range(len(g)), xerr=1.96 * g["se"], fmt="o", capsize=2, color="#165a70")
        ax.axvline(base[y], color="red", ls="--", lw=0.8)
        ax.axvline(0, color="gray", lw=0.8)
        ax.set_yticks(range(len(g)))
        ax.set_yticklabels(g["업종"], fontsize=7)
        ax.set_title(f"업종 하나씩 제외: {LABEL[y]}", fontsize=10)
    fig.tight_layout()
    fig.savefig(MOD / "M2_업종제외범위.png", dpi=140)
    print("M2 결과 (업종 제외 제외)")
    show(R[~R["사양"].str.startswith("업종 제외")])
    for y in T3:
        g = L[L["y"] == y]
        print(f"  업종 하나씩 제외 {LABEL[y]}: 계수 범위 {g['b'].min():.3f} ~ {g['b'].max():.3f} (기준 {base[y]:.3f}), p<0.05인 경우 {(g['p']<0.05).sum()}/{len(g)}, 부호 바뀐 경우 {(np.sign(g['b'])!=np.sign(base[y])).sum()}")
    return R


# ───────────────────────── M3 ─────────────────────────
def m3(P):
    S = prep_S(P)
    rows = []
    ts = [t for t in range(23) if t != 9]
    names = {t: f"{2019 + t // 4}Q{t % 4 + 1}" for t in range(23)}
    fig, axes = plt.subplots(3, 1, figsize=(9, 11))
    for ax, y in zip(axes, T3):
        for t in ts:
            S[f"Ev{t}"] = S["E_pre_A"] * (S["t"] == t)
        r = fit(S, y, [f"Ev{t}" for t in ts], FE)
        for i, t in enumerate(ts):
            rows.append({"모듈": "M3", "사양": "이벤트 스터디", "결과변수": y, "변수": f"E×1[{names[t]}]", "계수": r["beta"][i], "표준오차": r["se"][i],
                         "p": r["p"][i], "관측": r["N"], "기업": r["G"], "가족": None, "비고": "기준 2021Q2"})
        pre = [i for i, t in enumerate(ts) if t < 9]
        bb = r["beta"][pre]
        W = float(bb @ np.linalg.solve(r["V"][np.ix_(pre, pre)], bb))
        pj = stats.f.sf(W / len(pre), len(pre), r["G"] - 1)
        rows.append({"모듈": "M3", "사양": "사전 계수 공동 Wald", "결과변수": y, "변수": "사전 9개 공동 0", "계수": W, "표준오차": np.nan, "p": pj,
                     "관측": r["N"], "기업": r["G"], "가족": "M3Wald", "비고": "F 근사"})
        ax.errorbar(ts, r["beta"], yerr=1.96 * r["se"], fmt="o", capsize=2, color="#165a70")
        ax.axhline(0, color="gray", lw=0.8)
        ax.axvline(9.5, color="red", ls="--", lw=0.8)
        ax.set_xticks(range(23))
        ax.set_xticklabels([names[t] for t in range(23)], rotation=70, fontsize=7)
        ax.set_title(f"이벤트 스터디(기준 2021Q2): {LABEL[y]}", fontsize=10)
    fig.tight_layout()
    fig.savefig(MOD / "M3_이벤트스터디.png", dpi=140)
    tmap = S.groupby("t")["tight"].first().to_dict()
    Sp = S[S["t"] <= 9].copy()
    for t0, nm in ((2, "2019Q3"), (4, "2020Q1"), (6, "2020Q3"), (8, "2021Q1")):
        Sp["tp"] = Sp["t"].map(lambda t: tmap[t - t0 + 10] if t >= t0 else 0.0)
        Sp["Epl"] = Sp["E_pre_A"] * Sp["tp"]
        for y in T3:
            rows += rows_from(fit(Sp, y, ["Epl"], FE), "M3", f"위약: 가짜 긴축 시작 {nm}", ["E×Tight_p"], "M3위약")
    R = finish(rows, "M3", "결과")
    print("M3: 사전 계수 공동 Wald + 위약")
    show(R[R["사양"].str.startswith("사전") | R["사양"].str.startswith("위약")])
    return R


# ───────────────────────── M4 ─────────────────────────
def m4(P):
    S = prep_S(P)
    S["oi_asinh"] = np.arcsinh(S["oi_ttm"] / 1e8)
    rows = []
    for y in ["fc_a", "oi_a", "cost_w", "oi_asinh"]:
        rows += rows_from(fit(S, y, ["Ex"], FE), "M4", "구성요소 " + LABEL[y], ["E×Tight"], "M4")
    R = finish(rows, "M4", "결과")
    print("M4 결과")
    show(R)
    return R


# ───────────────────────── M5 ─────────────────────────
def m5(P):
    S = prep_S(P)
    S["ExRL"] = S["E_pre_A"] * S["RL"]
    rows = []
    for y in T3:
        rows += rows_from(fit(S, y, ["ExRL"], FE), "M5", "E×금리수준(일수가중 분기평균−0.50, 사전기간 0)", ["E×RL"], "M5")
    for y in T3:
        r = fit(S, y, ["ExRL", "Ex"], FE)
        rows += rows_from(r, "M5", "동시 투입: E×RL과 E×Tight", ["E×RL", "E×Tight(동시)"], "M5", fam_all=False)
    R = finish(rows, "M5", "결과")
    print("M5 결과")
    show(R)
    c = S[["Ex", "ExRL"]].corr().iloc[0, 1]
    print(f"  (참고) E×Tight와 E×RL의 상관 {c:.3f}")
    return R


# ───────────────────────── M6 ─────────────────────────
def m6(P):
    S = prep_S(P)
    lo, hi = S["icr"].quantile(.01), S["icr"].quantile(.99)
    S6 = S[~(S["icr"] < lo) & ~(S["icr"] > hi)]
    rows = []
    r = fit(S6, "icr", ["Ex"], ["corp_code", "t"])
    rows += rows_from(r, "M6", f"M1: ICR P1/P99({lo:.1f}/{hi:.1f}) 밖 관측 행 제외", ["E×Tight"], "M6")
    r = fit(S6, "icr", ["Ex"], FE)
    rows += rows_from(r, "M6", "M2: P1/P99 밖 행 제외", ["E×Tight"], "M6")
    r = fit(S6, "icr", ["Ex", "size_x", "lev_x", "roa_x"], FE)
    rows += rows_from(r, "M6", "M3: P1/P99 밖 행 제외", ["E×Tight", "ln자산×Tight", "레버리지×Tight", "영업이익/자산×Tight"], "M6")
    top = S.groupby("corp_code")["icr"].apply(lambda s: s.abs().mean()).nlargest(10).index
    St = add_T(S[~S["corp_code"].isin(top)])
    for y in T3:
        rows += rows_from(fit(St, y, ["Ex"], FE), "M6", "M2: |ICR| 평균 상위 10개 기업 제외", ["E×Tight"], "M6")
    R = finish(rows, "M6", "결과")
    print("M6 결과")
    show(R[R["변수"] == "E×Tight"])
    return R


# ───────────────────────── M7 ─────────────────────────
def m7(P):
    S = prep_S(P)
    rows = []
    S["Qx"] = S["lev_pre"] * S["tight"]
    S7 = S[S["E_pre_B"].notna()].copy()
    S7["Sx"] = S7["E_pre_B"] * S7["tight"]
    for y in ["T1", "T2", "T3", "cost_w"]:
        r = fit(S7, y, ["Qx", "Sx"], FE)
        rows += rows_from(r, "M7", "Q(레버리지)×Tight와 S(단기 비중)×Tight 동시", ["Q 레버리지×Tight", "S 단기 비중×Tight"], "M7a", fam_all=True)
    S8 = S[S["lt_pre"].notna()].copy()
    S8["Stx"] = S8["E_pre_A"] * S8["tight"]
    S8["Ltx"] = S8["lt_pre"] * S8["tight"]
    for y in T3:
        r = fit(S8, y, ["Stx", "Ltx"], FE)
        rows += rows_from(r, "M7", "단기(E)×Tight와 장기(비유동 차입/자산)×Tight 동시", ["단기 E×Tight", "장기 차입×Tight"], "M7b", fam_all=True)
    F = S.drop_duplicates("corp_code")
    q1, q2 = F["lev_pre"].quantile([1 / 3, 2 / 3])
    S["lt3"] = np.where(S["lev_pre"] <= q1, 1, np.where(S["lev_pre"] <= q2, 2, 3))
    for k in (1, 2, 3):
        S[f"Ex_l{k}"] = S["Ex"] * (S["lt3"] == k)
    for y in T3:
        rows += rows_from(fit(S, y, ["Ex_l1", "Ex_l2", "Ex_l3"], FE), "M7", "레버리지 3분위별 E×Tight", ["하위", "중간", "상위"], "M7c", fam_all=True)
    R = finish(rows, "M7", "결과")
    print("M7 결과")
    show(R)
    return R


# ───────────────────────── M8 ─────────────────────────
def m8(P):
    S = prep_S(P)
    rows = []
    specs = [("M1", ["Ex"], ["corp_code", "t"], ("corp_code",)), ("M2", ["Ex"], FE, ("corp_code",)),
             ("M3", ["Ex", "size_x", "lev_x", "roa_x"], FE, ("corp_code",))]
    for nm, xs, fes, nest in specs:
        for y in ["T1", "T2"]:
            f = fit(S, y, xs, fes, "corp_code", nest, keep_internals=True)
            pw, th = wcr_p(f, 0, B=9999)
            rows.append({"모듈": "M8", "사양": f"{nm} 기업 군집", "결과변수": y, "변수": "E×Tight", "계수": f["beta"][0], "표준오차": f["se"][0], "p": f["p"][0],
                         "관측": f["N"], "기업": f["G"], "가족": None, "비고": f"WCR p={pw:.4f} (Webb, 9999회)", "WCR_p": pw})
            fi = fit(S, y, xs, fes, "업종2", ("corp_code", "ind_t"), keep_internals=True)
            pwi, thi = wcr_p(fi, 0, B=9999, seed=20261106)
            rows.append({"모듈": "M8", "사양": f"{nm} 업종 군집", "결과변수": y, "변수": "E×Tight", "계수": fi["beta"][0], "표준오차": fi["se"][0], "p": fi["p"][0],
                         "관측": fi["N"], "기업": fi["G"], "가족": None, "비고": f"WCR p={pwi:.4f} (Webb, 9999회, 업종 {fi['G']}개)", "WCR_p": pwi})
            print(f"  {nm} {y}: 기업군집 p={f['p'][0]:.4f}/WCR {pw:.4f} | 업종군집 p={fi['p'][0]:.4f}/WCR {pwi:.4f}")
    R = finish(rows, "M8", "결과")
    return R


# ───────────────────────── M9 ─────────────────────────
def m9(P):
    S = prep_S(P)
    rows = []
    F = S.drop_duplicates("corp_code")
    q1, q2 = F["ln_assets_pre"].quantile([1 / 3, 2 / 3])
    S["sz3"] = np.where(S["ln_assets_pre"] <= q1, 1, np.where(S["ln_assets_pre"] <= q2, 2, 3))
    for k in (1, 2, 3):
        S[f"Ex_s{k}"] = S["Ex"] * (S["sz3"] == k)
    for y in T3:
        rows += rows_from(fit(S, y, ["Ex_s1", "Ex_s2", "Ex_s3"], FE), "M9", "사전 자산 3분위별 E×Tight", ["작은 기업", "중간", "큰 기업"], "M9", fam_all=True)
    for mk, nm in (("Y", "코스피(Y)"), ("K", "코스닥(K)")):
        Sm = add_T(S[S["법인구분"] == mk].drop(columns=["T1", "T2", "T3"]))
        for y in T3:
            rows += rows_from(fit(Sm, y, ["Ex"], FE), "M9", f"시장 {nm}만", ["E×Tight"], "M9")
    for code, nm in (("26", "업종 26(전자·반도체) 제외"), ("12", "담배(12) 제외")):
        Sx = add_T(S[S["업종2"].astype(str) != code].drop(columns=["T1", "T2", "T3"]))
        for y in T3:
            rows += rows_from(fit(Sx, y, ["Ex"], FE), "M9", nm, ["E×Tight"], "M9")
    R = finish(rows, "M9", "결과")
    print("M9 결과")
    show(R)
    return R


# ───────────────────────── M10 ─────────────────────────
def m10(P):
    S = prep_S(P)
    g = []
    for c, d in S.groupby("corp_code"):
        pre = d[(d["t"] <= 9) & d["oi_ttm"].notna() & d["fc_ttm"].notna()]
        post = d[(d["t"] >= 10) & d["oi_ttm"].notna() & d["fc_ttm"].notna()]
        if len(pre) < 4 or len(post) < 4:
            continue
        o0, f0, o1, f1 = pre["oi_ttm"].mean(), pre["fc_ttm"].mean(), post["oi_ttm"].mean(), post["fc_ttm"].mean()
        if f0 <= 0 or f1 <= 0:
            continue
        r0, r1 = o0 / f0, o1 / f1
        c_oi = 0.5 * ((o1 - o0) / f0 + (o1 - o0) / f1)
        c_fc = 0.5 * (o0 * (1 / f1 - 1 / f0) + o1 * (1 / f1 - 1 / f0))
        g.append({"corp_code": c, "E": d["E_pre_A"].iloc[0], "ICR_pre": r0, "ICR_post": r1, "dICR": r1 - r0, "기여_영업이익": c_oi, "기여_금융비용": c_fc,
                  "OI_up": o1 > o0, "FC_up": f1 > f0})
    G = pd.DataFrame(g)
    G["E분위"] = pd.qcut(G["E"], 3, labels=["E 하위 1/3", "E 중간", "E 상위 1/3"])
    G.to_csv(MOD / "M10_기업별분해.csv", index=False, encoding="utf-8-sig")
    out = []
    for lab, d in list(G.groupby("E분위", observed=True)) + [("전체", G)]:
        out.append({"집단": lab, "기업": len(d), "ICR_사전 중앙값": d["ICR_pre"].median(), "ICR_인상기 중앙값": d["ICR_post"].median(),
                    "dICR 중앙값": d["dICR"].median(), "영업이익 기여 중앙값": d["기여_영업이익"].median(), "금융비용 기여 중앙값": d["기여_금융비용"].median(),
                    "ICR 하락 기업 비율": (d["dICR"] < 0).mean(), "금융비용↑ 비율": d["FC_up"].mean(), "영업이익↓ 비율": (~d["OI_up"]).mean(),
                    "금융비용↑&영업이익↓ 비율": (d["FC_up"] & ~d["OI_up"]).mean()})
    T = pd.DataFrame(out)
    T.to_csv(MOD / "M10_분해.csv", index=False, encoding="utf-8-sig")
    print("M10 회계 분해 (기업별 사전 vs 인상기 평균, 대칭 분해, 중앙값)")
    print(T.round(3).to_string(index=False))
    return T


MODS = {"M0": m0, "M1": m1, "M2": m2, "M3": m3, "M4": m4, "M5": m5, "M6": m6, "M7": m7, "M8": m8, "M9": m9, "M10": m10}


def main():
    P = load_panel()
    for name in sys.argv[1:]:
        print("=" * 80, "\n", name, flush=True)
        res = MODS[name](P)
        if name == "M0" and res is False:
            print("M0 실패: 멈춥니다.")
            sys.exit(2)
        print(flush=True)


if __name__ == "__main__":
    main()
