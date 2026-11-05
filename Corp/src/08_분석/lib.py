# 이 파일은 노트북 '00_공통함수.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 08-00 · 공통 함수 (`lib.py`) ───


# ─── 준비 — 불러오기와 경로 ───


"""파이프라인(A_분석_파이프라인_v1대응_11-05.html) 공통 코드: 패널 불러오기, 고정효과 회귀, wild cluster bootstrap, Holm 보정.
고정효과 회귀는 02_회귀.py의 fe_ols와 같은 방식(교대 투영, CR1 군집 표준오차)이며, 군집 변수와 '군집에 속한 FE'를 지정할 수 있게 확장했다.
"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy import stats
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


OUT = config.BASE / "outputs" / "07_분석"
MOD = OUT / "모듈별"
MOD.mkdir(parents=True, exist_ok=True)
RATES = config.BASE.parent / "src" / "06_industry_analysis" / "rate_model_v1" / "inputs" / "rates.csv"
FE = ["corp_code", "ind_t"]
# 결과변수별 '악화' 방향의 계수 부호 (+1이면 계수가 양수일 때 악화)
WORSE = {"icr": -1, "icr_w": -1, "T1": -1, "T2": +1, "T3": -1, "fc_a": +1, "oi_a": -1, "cost_w": +1, "oi_asinh": -1}
LABEL = {"icr": "ICR 원값", "icr_w": "ICR 1·99% 절단", "T1": "asinh(ICR)", "T2": "1{ICR<1}", "T3": "ICR 업종×분기 순위",
         "fc_a": "금융비용 TTM/자산", "oi_a": "영업이익 TTM/자산", "cost_w": "비용률(금융비용/평균 총차입금, 절단)", "oi_asinh": "asinh(영업이익 TTM, 억원)"}


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


def fit(df, y, xs, fes=FE, cluster="corp_code", nested=("corp_code",), keep_internals=False):
    cols = list(dict.fromkeys([y] + xs + fes + [cluster]))
    d = df[cols].dropna().copy()
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
    K = k + sum(d[f].nunique() for f in fes if f not in nested and f != cluster)
    c = G / (G - 1) * (N - 1) / (N - K)
    V = c * bread @ (S.T @ S) @ bread
    se = np.sqrt(np.diag(V))
    t = beta / se
    p = 2 * stats.t.sf(np.abs(t), G - 1)
    out = {"y": y, "xs": xs, "beta": beta, "se": se, "t": t, "p": p, "V": V, "N": N, "N0": n0, "G": G}
    if keep_internals:
        out.update({"d": d, "X": d[xs].to_numpy(float), "yraw": d[y].to_numpy(float), "codes": codes, "cl": cl, "bread": bread, "c": c, "Xt": Xt, "yt": yt})
    return out


def wcr_p(f, test=0, B=9999, seed=20261105, batch=500):
    """Webb 6점 가중치 wild cluster bootstrap(귀무가설 부과, studentized). f는 fit(..., keep_internals=True)의 결과."""
    rng = np.random.default_rng(seed)
    webb = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])
    n = len(f["yt"])
    D = sp.hstack([sp.csr_matrix((np.ones(n), (np.arange(n), c)), shape=(n, c.max() + 1)) for c in f["codes"]]).tocsr()
    P = np.linalg.pinv((D.T @ D).toarray())

    def proj(Y):                         # FE 성분 제거 (Y - D(D'D)^+ D'Y)
        return Y - D @ (P @ (D.T @ Y))

    Xt, yt, cl, G, bread, c = f["Xt"], f["yt"], f["cl"], f["G"], f["bread"], f["c"]
    k = Xt.shape[1]
    others = [j for j in range(k) if j != test]
    if others:
        Xo = Xt[:, others]
        gam = np.linalg.solve(Xo.T @ Xo, Xo.T @ yt)
        base = Xo @ gam
        er = yt - base
    else:
        base = np.zeros(n)
        er = yt
    Cg = sp.csr_matrix((np.ones(n), (cl, np.arange(n))), shape=(G, n))
    # 원래 t (같은 군집 기준)
    t_hat = f["beta"][test] / np.sqrt(f["V"][test, test])
    # 귀무하의 부트스트랩은 검정 계수만 0으로 두고 나머지 계수는 원래 값으로 두는 제한 모형
    tstar = []
    done = 0
    while done < B:
        b = min(batch, B - done)
        W = webb[rng.integers(0, 6, size=(G, b))]
        Estar = er[:, None] * W[cl, :]
        Ystar = base[:, None] + proj(Estar)
        bet = np.linalg.solve(Xt.T @ Xt, Xt.T @ Ystar)             # k × b
        res = Ystar - Xt @ bet
        a = np.zeros((G, b))
        for j in range(k):
            Sj = Cg @ (Xt[:, [j]] * res)                           # G × b
            a += bread[test, j] * Sj
        var = c * (a ** 2).sum(axis=0)
        tstar.append(bet[test] / np.sqrt(var))
        done += b
    tstar = np.concatenate(tstar)
    return float((np.abs(tstar) >= abs(t_hat)).mean()), float(t_hat)


def holm(ps):
    ps = np.asarray(ps, float)
    order = np.argsort(ps)
    m = len(ps)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        adj[i] = run
    return adj


def add_T(df):
    d = df.copy()
    d["T1"] = np.arcsinh(d["icr"])
    d["T2"] = np.where(d["icr"].notna(), (d["icr"] < 1).astype(float), np.nan)
    n = d.groupby("ind_t")["icr"].transform(lambda s: s.notna().sum())
    d["T3"] = d.groupby("ind_t")["icr"].rank(pct=True)
    d.loc[n < 3, "T3"] = np.nan
    return d


def avg_rate_by_t():
    """분기 일수 가중 평균 기준금리(t=0이 2019Q1)."""
    import csv
    rates = [(dt.date.fromisoformat(r["변경일자"]), float(r["기준금리"])) for r in csv.DictReader(open(RATES, encoding="utf-8-sig"))]

    def at(d):
        v = None
        for a, b in rates:
            if a <= d:
                v = b
        return v
    out = {}
    for y in range(2019, 2025):
        for q in (1, 2, 3, 4):
            if y == 2024 and q == 4:
                continue
            s = dt.date(y, 3 * q - 2, 1)
            e = (dt.date(y, 3 * q + 1, 1) if q < 4 else dt.date(y + 1, 1, 1))
            days = (e - s).days
            tot = sum(at(s + dt.timedelta(days=i)) for i in range(days))
            out[(y * 4 + q - 1) - 2019 * 4] = tot / days
    return out


def load_panel():
    P = pd.read_csv(OUT / "패널_기업분기.csv", dtype={"corp_code": str})
    P["corp_code"] = P["corp_code"].str.zfill(8)
    P["ind_t"] = P["업종2"].astype(str) + "_" + P["t"].astype(str)
    P["Ex"] = P["E_pre_A"] * P["tight"]
    # 2019년 평균 E, 사전 장기차입/자산
    er = pd.read_csv(config.BASE / "outputs" / "06_노출도E" / "E_보고서별.csv", dtype={"corp_code": str})
    er["corp_code"] = er["corp_code"].str.zfill(8)
    ok = er[er["E_A"].notna()]
    e19 = ok[ok["year"] == 2019].groupby("corp_code")["E_A"].agg(["mean", "count"])
    e19 = e19[e19["count"] >= 3]["mean"]
    P["E_2019"] = P["corp_code"].map(e19)
    v = er[(er["상태"].isin(["DEBT", "ZERO"])) & (er["자산총계"] > 0)].copy()
    v["lt_a"] = v["비유동차입합"] / v["자산총계"]
    P["lt_pre"] = P["corp_code"].map(v.groupby("corp_code")["lt_a"].mean())
    # 평균 총차입금 (전 기간 차입 파일이 있으면)
    dp = MOD / "차입_전기간.csv"
    if dp.exists():
        db = pd.read_csv(dp, dtype={"corp_code": str})
        db["corp_code"] = db["corp_code"].str.zfill(8)
        db["tot"] = db["num_C"] + db["num_N"]
        db.loc[db["state"] == "NOHDR", "tot"] = np.nan          # 머리행이 없으면 차입 합을 알 수 없음
        qmap = {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}
        db["t"] = db["year"] * 4 + db["report"].map(qmap) - 1 - 2019 * 4
        dd = db.set_index(["corp_code", "t"])["tot"].to_dict()

        def _avg(c, t):
            v = [dd.get((c, t - k), np.nan) for k in range(4)]
            return np.nan if np.isnan(v).any() else float(np.mean(v))
        P["avg_debt"] = [_avg(c, t) for c, t in zip(P["corp_code"], P["t"])]
        P["cost_rate"] = np.where(P["avg_debt"] > 0, P["fc_ttm"] / P["avg_debt"], np.nan)
    P["oi_asinh"] = np.arcsinh(P["oi_ttm"] / 1e8)
    ar = avg_rate_by_t()
    P["avg_rate"] = P["t"].map(ar)
    P["RL"] = np.where(P["t"] >= 10, np.maximum(0.0, P["avg_rate"] - 0.50), 0.0)
    P["ExRL"] = P["E_pre_A"] * P["RL"]
    return P


def rows_from(fit_res, module, spec, labels, family=None, note="", y=None, fam_all=False):
    """family(Holm 가족)는 기본적으로 첫 번째 변수에만 붙인다(fam_all=True면 모든 변수)."""
    out = []
    y = y or fit_res["y"]
    for i, lab in enumerate(labels):
        if lab is None:
            continue
        out.append({"모듈": module, "사양": spec, "결과변수": y, "변수": lab, "계수": fit_res["beta"][i], "표준오차": fit_res["se"][i],
                    "p": fit_res["p"][i], "관측": fit_res["N"], "기업": fit_res["G"],
                    "가족": family if (i == 0 or fam_all) else None, "비고": note})
    return out


def finish(rows, module, name):
    R = pd.DataFrame(rows)
    if len(R):
        R["Holm_p"] = np.nan
        for fam, g in R[R["가족"].notna()].groupby("가족"):
            R.loc[g.index, "Holm_p"] = holm(g["p"].to_numpy())
        R["방향"] = [("악화" if np.sign(b) * WORSE.get(y, 0) > 0 else "개선") if (y in WORSE and b != 0) else "" for b, y in zip(R["계수"], R["결과변수"])]
    R.to_csv(MOD / f"{module}_{name}.csv", index=False, encoding="utf-8-sig")
    return R


# ─── 읽는 법과 주의 ───
