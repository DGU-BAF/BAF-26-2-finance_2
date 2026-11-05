"""회귀: 사전 고정한 모형 사다리(M1~M3), 이질성, 이벤트 스터디, 보조 결과, 강건성 R1~R4, 진단을 **한 번** 실행한다.
규칙은 docs/A_결정_제안_근거표_11-05.md 8절(회귀 전 고정). 결과를 보고 사양을 고르거나 바꾸지 않는다.

모형: ICR_it = α_i + λ(...) + β·(E_i × Tight_t) + [γ'·사전특성_i×Tight_t] + ε_it
  M1: 기업 FE + 분기 FE / M2: 기업 FE + 업종(앞 2자리)×분기 FE / M3: M2 + 사전특성×Tight
  표준오차: 기업 단위 군집(CR1: G/(G-1)·(N-1)/(N-K), K에는 기업 FE는 군집에 포함되므로 세지 않고 그 밖의 FE는 셈), 검정은 t(G-1)
  싱글톤(FE 칸에 관측 1개)은 반복해서 제거.
고정효과는 직접 구현한 교대 투영(demeaning)으로 흡수한다(전용 라이브러리 없음). 구현 검증은 03_회귀_구현검증.py.
"""
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OUT = config.BASE / "outputs" / "07_분석"
BASE_T = 9           # 2021Q2 (t=0이 2019Q1)
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def demean(M, codes, maxit=1000, tol=1e-10):
    M = M.astype(float).copy()
    cnts = [np.bincount(c) for c in codes]
    for _ in range(maxit):
        mx = 0.0
        for c, cn in zip(codes, cnts):
            for j in range(M.shape[1]):
                m = np.bincount(c, weights=M[:, j]) / cn
                M[:, j] -= m[c]
                mx = max(mx, np.abs(m).max())
        if mx < tol * max(1.0, np.abs(M).max()):
            break
    return M


def fe_ols(df, y, xs, fes, cluster="corp_code", label=""):
    cols = [y] + xs + fes + [cluster]
    d = df[list(dict.fromkeys(cols))].dropna().copy()
    n0 = len(d)
    while True:
        keep = np.ones(len(d), bool)
        for f in fes:
            keep &= d[f].map(d[f].value_counts()).values > 1
        if keep.all():
            break
        d = d[keep]
    codes = [pd.factorize(d[f])[0] for f in fes]
    M = d[[y] + xs].to_numpy(float)
    Mt = demean(M, codes)
    yt, Xt = Mt[:, 0], Mt[:, 1:]
    XtX = Xt.T @ Xt
    beta = np.linalg.solve(XtX, Xt.T @ yt)
    e = yt - Xt @ beta
    cl = pd.factorize(d[cluster])[0]
    G = cl.max() + 1
    S = pd.DataFrame(Xt * e[:, None]).groupby(cl).sum().to_numpy()
    bread = np.linalg.inv(XtX)
    N, k = Xt.shape
    nonnested = sum(d[f].nunique() for f in fes if f != cluster and f != "corp_code")
    K = k + nonnested
    c = G / (G - 1) * (N - 1) / (N - K)
    V = c * bread @ (S.T @ S) @ bread
    se = np.sqrt(np.diag(V))
    t = beta / se
    p = 2 * stats.t.sf(np.abs(t), G - 1)
    r2_within = 1 - (e @ e) / (yt @ yt)
    return {"label": label, "y": y, "xs": xs, "beta": beta, "se": se, "t": t, "p": p, "V": V, "N": N, "N0": n0, "G": G,
            "r2w": r2_within, "dropped_singletons": n0 - N}


def fmt(res, i=0):
    return f"{res['beta'][i]: .4f} ({res['se'][i]:.4f}) p={res['p'][i]:.3f}"


def main():
    P = pd.read_csv(OUT / "패널_기업분기.csv", dtype={"corp_code": str})
    P["corp_code"] = P["corp_code"].str.zfill(8)
    P["ind_t"] = P["업종2"].astype(str) + "_" + P["t"].astype(str)
    P["Ex"] = P["E_pre_A"] * P["tight"]
    P["ExB"] = P["E_pre_B"] * P["tight"]
    P["Ex21"] = P["E_2021Q2"] * P["tight"]
    P["Ex0"] = P["E_pre_A_amb0"] * P["tight"]
    P["size_x"] = P["ln_assets_pre"] * P["tight"]
    P["lev_x"] = P["lev_pre"] * P["tight"]
    P["roa_x"] = P["roa_pre"] * P["tight"]
    L = []
    rows = []

    def rec(res, spec, var="E×Tight", i=0):
        rows.append({"사양": spec, "종속변수": res["y"], "변수": var, "계수": res["beta"][i], "표준오차": res["se"][i], "t": res["t"][i],
                     "p": res["p"][i], "관측": res["N"], "기업": res["G"], "within_R2": res["r2w"]})

    S = P[P["표본_주"]].copy()
    firms_main = S["corp_code"].nunique()
    L.append(f"주 표본: 기업 {firms_main:,}곳, 기업-분기 {len(S):,}개 (ICR 관측 {int(S['icr'].notna().sum()):,}개)")
    lo, hi = S["icr"].quantile(.01), S["icr"].quantile(.99)
    S["icr_w"] = S["icr"].clip(lo, hi)
    L.append(f"ICR 1%·99% 절단 경계: {lo:.2f} / {hi:.2f}")
    e1 = S.drop_duplicates("corp_code")["E_pre_A"]
    L.append(f"E_pre_A 분포(주 표본 기업): 평균 {e1.mean():.3f}, 중앙값 {e1.median():.3f}, 표준편차 {e1.std():.3f}, 상위25% 경계 {e1.quantile(.75):.3f}")
    L.append(f"긴축 3%p, E 0.1 증가일 때 계수 해석 배율: 0.1×3.0 = 0.30 (예: β=-1이면 ICR 약 -0.3)")
    L.append("")

    # ── 모형 사다리 ──
    L.append("[1] 모형 사다리 — 종속변수 ICR (E×Tight 계수, 기업 군집 표준오차)")
    m1 = fe_ols(S, "icr", ["Ex"], ["corp_code", "t"], label="M1")
    m2 = fe_ols(S, "icr", ["Ex"], ["corp_code", "ind_t"], label="M2")
    m3 = fe_ols(S, "icr", ["Ex", "size_x", "lev_x", "roa_x"], ["corp_code", "ind_t"], label="M3")
    for nm, m in (("M1 기업FE+분기FE", m1), ("M2 기업FE+업종×분기FE (기준)", m2)):
        L.append(f"  {nm:34s} β={fmt(m)}  N={m['N']:,} 기업={m['G']:,} 싱글톤제거={m['dropped_singletons']}")
        rec(m, nm)
    L.append(f"  {'M3 M2+사전특성×Tight':34s} β={fmt(m3)}  N={m3['N']:,} 기업={m3['G']:,}")
    rec(m3, "M3 M2+사전특성×Tight")
    for j, v in enumerate(["ln자산_사전×Tight", "레버리지_사전×Tight", "영업이익/자산_사전×Tight"], 1):
        L.append(f"       {v:28s} {fmt(m3, j)}")
        rec(m3, "M3 M2+사전특성×Tight", v, j)
    m2w = fe_ols(S, "icr_w", ["Ex"], ["corp_code", "ind_t"], label="M2 절단")
    L.append(f"  {'M2, ICR 1%·99% 절단(보조)':34s} β={fmt(m2w)}  N={m2w['N']:,}")
    rec(m2w, "M2 ICR 절단(보조)")
    L.append("")

    # ── 이질성 ──
    L.append("[2] 이질성 — 사전 평균 자산 3분위별 β (M2)")
    q1, q2 = S.drop_duplicates("corp_code")["ln_assets_pre"].quantile([1 / 3, 2 / 3])
    S["tercile"] = np.where(S["ln_assets_pre"] <= q1, 1, np.where(S["ln_assets_pre"] <= q2, 2, 3))
    for k in (1, 2, 3):
        S[f"Ex_s{k}"] = S["Ex"] * (S["tercile"] == k)
    mh = fe_ols(S, "icr", ["Ex_s1", "Ex_s2", "Ex_s3"], ["corp_code", "ind_t"], label="이질성")
    for k, nm in enumerate(["하위 1/3(작은 기업)", "중간 1/3", "상위 1/3(큰 기업)"]):
        L.append(f"  {nm:20s} β={fmt(mh, k)}")
        rec(mh, "이질성(자산 3분위)", f"E×Tight, {nm}", k)
    L.append("")

    # ── 이벤트 스터디 ──
    L.append("[3] 이벤트 스터디 — 분기별 E 계수, 기준 2021Q2(t=9), M2의 FE")
    ts = [t for t in range(0, 23) if t != BASE_T]
    for t in ts:
        S[f"Ev{t}"] = S["E_pre_A"] * (S["t"] == t)
    me = fe_ols(S, "icr", [f"Ev{t}" for t in ts], ["corp_code", "ind_t"], label="이벤트스터디")
    names = {t: f"{2019 + t // 4}Q{t % 4 + 1}" for t in range(23)}
    ev = []
    for i, t in enumerate(ts):
        ev.append({"분기": names[t], "t": t, "계수": me["beta"][i], "표준오차": me["se"][i], "p": me["p"][i]})
        L.append(f"  {names[t]}  {me['beta'][i]: .3f} ({me['se'][i]:.3f})")
    pre_idx = [i for i, t in enumerate(ts) if t < BASE_T]
    b = me["beta"][pre_idx]
    Vp = me["V"][np.ix_(pre_idx, pre_idx)]
    W = float(b @ np.linalg.solve(Vp, b))
    pj = stats.f.sf(W / len(pre_idx), len(pre_idx), me["G"] - 1)
    L.append(f"  사전 분기 계수 {len(pre_idx)}개 공동 0 검정(군집 Wald, F 근사): W={W:.2f}, p={pj:.3f}")
    pd.DataFrame(ev).to_csv(OUT / "이벤트스터디.csv", index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    xs = [e["t"] for e in ev]
    ax.errorbar(xs, [e["계수"] for e in ev], yerr=[1.96 * e["표준오차"] for e in ev], fmt="o", capsize=3, color="#165a70")
    ax.axhline(0, color="gray", lw=0.8)
    ax.axvline(BASE_T + 0.5, color="red", ls="--", lw=0.8)
    ax.set_xticks(range(23))
    ax.set_xticklabels([names[t] for t in range(23)], rotation=70, fontsize=8)
    ax.set_ylabel("E 계수 (기준: 2021Q2)")
    ax.set_title("이벤트 스터디: 사전 단기차입 노출도(E)와 ICR (M2, 95% 신뢰구간, 기업 군집)")
    fig.tight_layout()
    fig.savefig(OUT / "이벤트스터디.png", dpi=150)
    L.append("")

    # ── 보조 결과 ──
    L.append("[4] 보조 결과 (M2, E×Tight)")
    for y, nm in (("fc_a", "금융비용 TTM/자산"), ("oi_a", "영업이익 TTM/자산")):
        m = fe_ols(S, y, ["Ex"], ["corp_code", "ind_t"], label=nm)
        L.append(f"  {nm:22s} β={fmt(m)}  N={m['N']:,}")
        rec(m, f"보조결과 {nm}")
    L.append("")

    # ── 강건성 ──
    L.append("[5] 강건성 (M2, 종속변수 ICR, E×Tight 계수)")
    # R1
    R1 = S[S["E_pre_B"].notna()]
    r1 = fe_ols(R1, "icr", ["ExB"], ["corp_code", "ind_t"], label="R1")
    L.append(f"  R1 E=단기차입/총차입금          β={fmt(r1)}  N={r1['N']:,} 기업={r1['G']:,}")
    rec(r1, "R1 E=단기차입/총차입금", "E_B×Tight")
    # R2
    R2 = P[(P["표본_주"]) & (P["post_icr_cash_n"] >= 8)]
    r2 = fe_ols(R2, "icr_cash", ["Ex"], ["corp_code", "ind_t"], label="R2")
    L.append(f"  R2 ICR 분모=현금 이자지급       β={fmt(r2)}  N={r2['N']:,} 기업={r2['G']:,}")
    rec(r2, "R2 ICR분모=현금 이자지급")
    # R3
    R3 = S[S["E_2021Q2"].notna()]
    r3 = fe_ols(R3, "icr", ["Ex21"], ["corp_code", "ind_t"], label="R3")
    L.append(f"  R3 E=2021Q2 단독                β={fmt(r3)}  N={r3['N']:,} 기업={r3['G']:,}")
    rec(r3, "R3 E=2021Q2", "E_2021Q2×Tight")
    # R4
    R4 = P[P["표본_R4"]].copy()
    R4["ind_t"] = R4["업종2"].astype(str) + "_" + R4["t"].astype(str)
    r4 = fe_ols(R4, "icr", ["Ex"], ["corp_code", "ind_t"], label="R4")
    L.append(f"  R4 사전기간 혼재만 제외         β={fmt(r4)}  N={r4['N']:,} 기업={r4['G']:,}")
    rec(r4, "R4 사전기간 혼재만 제외")
    # 규칙 ④ 보조: 애매=0
    S0 = S[S["E_pre_A_amb0"].notna()]
    s0 = fe_ols(S0, "icr", ["Ex0"], ["corp_code", "ind_t"], label="S1")
    L.append(f"  S1 애매 분기를 E=0으로(규칙④ 보조) β={fmt(s0)}  N={s0['N']:,} 기업={s0['G']:,}")
    rec(s0, "S1 애매=0 민감도", "E_amb0×Tight")
    L.append("")

    # ── 진단 ──
    L.append("[6] 진단")
    F = S.drop_duplicates("corp_code")
    dm = pd.get_dummies(F["업종2"], dtype=float)
    X = dm.to_numpy()
    yv = F["E_pre_A"].to_numpy()
    fit = X @ np.linalg.lstsq(X, yv, rcond=None)[0]
    r2 = 1 - ((yv - fit) ** 2).sum() / ((yv - yv.mean()) ** 2).sum()
    L.append(f"  (1) 업종 더미로 설명되는 E의 비율 R²={r2:.3f}; 업종 안에서 남는 E의 표준편차 {np.std(yv - fit):.3f} (전체 {yv.std():.3f})")
    cm = F[["E_pre_A", "ln_assets_pre", "lev_pre", "roa_pre"]].corr()
    L.append("  (3) 기업 단위 상관(E, ln자산_사전, 레버리지_사전, 영업이익/자산_사전):")
    for a in cm.index:
        L.append("      " + f"{a:14s} " + " ".join(f"{cm.loc[a, b]: .2f}" for b in cm.columns))
    ic = S["icr"].dropna()
    L.append(f"  (4) ICR 극단값: >50 {int((ic > 50).sum()):,}개, >100 {int((ic > 100).sum()):,}개, <-20 {int((ic < -20).sum()):,}개, 최대 {ic.max():.1f}, 최소 {ic.min():.1f}")
    top = S.loc[S["icr"].abs().nlargest(5).index, ["corp_code", "year", "q", "icr"]]
    L.append("      |ICR| 상위 5: " + "; ".join(f"{r.corp_code} {int(r.year)}Q{int(r.q)} {r.icr:.1f}" for r in top.itertuples()))
    L.append("  (5) 기업 수·관측: 위 사양별 N, 기업 수 및 패널 요약(패널_요약.txt)")
    L.append("  (6) 위약 검정(가짜 긴축 시점)은 이번 실행에 넣지 않음(8절 기재).")
    text = "\n".join(L)
    print(text)
    (OUT / "회귀_요약.txt").write_text(text, encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT / "회귀_결과.csv", index=False, encoding="utf-8-sig")
    print("저장:", OUT)


if __name__ == "__main__":
    main()
