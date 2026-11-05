# 이 파일은 노트북 '05_사후탐색.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 08-05 · 사후 탐색 Q2~Q7 ───


# ─── 준비 — 불러오기와 경로 ───


"""사후 탐색 Q2~Q7 (docs/A_사후탐색_계획_11-05.md). 계획서에서 덜 구체적이던 구현 세부는 실행 **전에** 아래처럼 고정했다.
  - 방향 통일: T1(asinh ICR)·T3(순위)는 계수 음수=악화, T2(ICR<1 여부)는 계수 양수=악화.
  - 신호 기준 (a): Q2의 3개 계수가 같은 경제적 방향. (b): 그중 최소 2개가 18개 전체 Holm 보정 p<0.10. (c): Q5 위약 계수 중 같은 방향이면서 보정 전 p<0.10인 것이 없음.
    (d): Q4(E_perp)의 3개 계수가 Q2와 같은 방향. 네 가지를 모두 만족해야 '신호'. (모두 임의 기준)
  - T3 순위: 업종×분기 칸 관측이 3개 미만이면 결측.
  - Q3: 첫 회귀의 ICR 절단 사양(1%·99% 절단 경계는 주 표본 원값 기준 고정)에서 (i) |ICR| 상위 20개 기업-분기 제외, (ii) 기업별 |ICR| 평균 상위 10개 기업 제외. Holm 집합 밖.
  - Q5 위약: Tight_p(t)=Tight(t+8)를 사전기간(t≤9)에만 적용. Q6: 임계 k∈{6,10}을 E 정의 분기(10개 중)와 인상기 ICR 관측(13개 중)에 함께 적용.
  - Q7: t≤19(2019Q1~2023Q4)로 제한, E×전환기(2021Q3~Q4, t=10·11)와 E×Post(2022Q1~2023Q4, t=12~19)를 함께 추정, E×Post만 Holm 집합.
FE·군집은 M2(기업 FE + 업종×분기 FE, 기업 군집). 후보는 모두 한 표에 보고한다.
"""
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pandas as pd
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


spec = importlib.util.spec_from_file_location("reg", HERE / "02_회귀.py")
reg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reg)
if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
    sys.stdout.reconfigure(encoding="utf-8")
OUT = config.BASE / "outputs" / "07_분석"
FE = ["corp_code", "ind_t"]
TN = {"T1": "asinh(ICR)", "T2": "1{ICR<1}", "T3": "ICR 업종×분기 순위"}
WORSE = {"T1": -1, "T2": +1, "T3": -1}      # 악화 방향의 계수 부호


def add_T(df):
    d = df.copy()
    d["T1"] = np.arcsinh(d["icr"])
    d["T2"] = np.where(d["icr"].notna(), (d["icr"] < 1).astype(float), np.nan)
    n = d.groupby("ind_t")["icr"].transform(lambda s: s.notna().sum())
    d["T3"] = d.groupby("ind_t")["icr"].rank(pct=True)
    d.loc[n < 3, "T3"] = np.nan
    return d


def holm(ps):
    order = np.argsort(ps)
    m = len(ps)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        adj[i] = run
    return adj


def main():
    P = pd.read_csv(OUT / "패널_기업분기.csv", dtype={"corp_code": str})
    P["corp_code"] = P["corp_code"].str.zfill(8)
    P["ind_t"] = P["업종2"].astype(str) + "_" + P["t"].astype(str)
    P["Ex"] = P["E_pre_A"] * P["tight"]
    S = add_T(P[P["표본_주"]])
    rows = []

    def run(df, y, x, group, spec, note=""):
        r = reg.fe_ols(df, y, [x] if isinstance(x, str) else x, FE)
        rows.append({"집합": group, "사양": spec, "결과변수": y, "계수": r["beta"][0], "표준오차": r["se"][0], "p": r["p"][0],
                     "관측": r["N"], "기업": r["G"], "비고": note})
        return r

    # Q2
    for y in ("T1", "T2", "T3"):
        run(S, y, "Ex", "Holm", "Q2 척도 " + TN[y])
    # Q4: E_perp
    F = S.drop_duplicates("corp_code").dropna(subset=["lev_pre", "E_pre_A"])
    X = np.column_stack([np.ones(len(F)), F["lev_pre"].to_numpy()])
    coef = np.linalg.lstsq(X, F["E_pre_A"].to_numpy(), rcond=None)[0]
    resid = F["E_pre_A"].to_numpy() - X @ coef
    S["E_perp"] = S["corp_code"].map(dict(zip(F["corp_code"], resid)))
    S["Ep_x"] = S["E_perp"] * S["tight"]
    for y in ("T1", "T2", "T3"):
        run(S, y, "Ep_x", "Holm", "Q4 E_perp " + TN[y], f"E-레버리지 회귀 계수 {coef[1]:.3f}")
    # Q5: 위약
    ts = S.groupby("t")["tight"].first().to_dict()
    Sp = S[S["t"] <= 9].copy()
    Sp["tp"] = Sp["t"].map(lambda t: ts.get(t + 8, np.nan))
    Sp["Epl"] = Sp["E_pre_A"] * Sp["tp"]
    for y in ("T1", "T2", "T3"):
        run(Sp, y, "Epl", "Holm", "Q5 위약(Tight 8분기 앞당김) " + TN[y], "사전기간 t≤9만")
    # Q6: 임계 6, 10
    for k in (6, 10):
        Sk = add_T(P[(~P["혼재"]) & (P["E정의분기"] >= k) & (P["post_icr_n"] >= k)])
        for y in ("T1", "T2", "T3"):
            run(Sk, y, "Ex", "Holm", f"Q6 임계 {k} " + TN[y], f"기업 {Sk['corp_code'].nunique()}")
    # Q7: v1식 Post
    S7 = S[S["t"] <= 19].copy()
    S7["Post7"] = S7["E_pre_A"] * S7["t"].between(12, 19)
    S7["Tr7"] = S7["E_pre_A"] * S7["t"].between(10, 11)
    for y in ("T1", "T2", "T3"):
        r = reg.fe_ols(S7, y, ["Post7", "Tr7"], FE)
        rows.append({"집합": "Holm", "사양": "Q7 E×Post(2022~23) " + TN[y], "결과변수": y, "계수": r["beta"][0], "표준오차": r["se"][0], "p": r["p"][0],
                     "관측": r["N"], "기업": r["G"], "비고": "t≤19"})
        rows.append({"집합": "참고", "사양": "Q7 E×전환기(2021Q3~Q4) " + TN[y], "결과변수": y, "계수": r["beta"][1], "표준오차": r["se"][1], "p": r["p"][1],
                     "관측": r["N"], "기업": r["G"], "비고": "Holm 집합 밖"})
    # Q3: 절단 사양의 영향 점검
    lo, hi = S["icr"].quantile(.01), S["icr"].quantile(.99)
    S["icr_w"] = S["icr"].clip(lo, hi)
    run(S, "icr_w", "Ex", "Q3(참고)", "Q3 기준: 절단 사양(첫 회귀 보조)", f"경계 {lo:.1f}/{hi:.1f}")
    top20 = S["icr"].abs().nlargest(20).index
    run(S.drop(index=top20), "icr_w", "Ex", "Q3(참고)", "Q3(i) |ICR| 상위 20개 기업-분기 제외", "")
    mabs = S.groupby("corp_code")["icr"].apply(lambda s: s.abs().mean()).nlargest(10).index
    run(S[~S["corp_code"].isin(mabs)], "icr_w", "Ex", "Q3(참고)", "Q3(ii) |ICR| 평균 상위 10개 기업 제외", f"제외 기업 {len(mabs)}")

    R = pd.DataFrame(rows)
    mask = R["집합"] == "Holm"
    R.loc[mask, "Holm_p"] = holm(R.loc[mask, "p"].to_numpy())
    R.to_csv(OUT / "사후탐색_결과.csv", index=False, encoding="utf-8-sig")

    # 신호 기준
    q2 = R[R["사양"].str.startswith("Q2")].set_index("결과변수")
    q4 = R[R["사양"].str.startswith("Q4")].set_index("결과변수")
    q5 = R[R["사양"].str.startswith("Q5")].set_index("결과변수")
    dir2 = {y: np.sign(q2.loc[y, "계수"]) * WORSE[y] for y in TN}   # +1 = 악화 방향, -1 = 개선 방향
    dir4 = {y: np.sign(q4.loc[y, "계수"]) * WORSE[y] for y in TN}
    a = len(set(dir2.values())) == 1
    b = int((q2["Holm_p"] < 0.10).sum()) >= 2
    c_bad = [y for y in TN if (np.sign(q5.loc[y, "계수"]) * WORSE[y] == (list(dir2.values())[0] if a else 99)) and q5.loc[y, "p"] < 0.10]
    c = a and not c_bad
    d = all(dir4[y] == dir2[y] for y in TN)
    sig = a and b and c and d

    L = ["[사후 탐색 결과] 주 표본 기업 %d곳, 관측 %d개 (M2: 기업 FE + 업종×분기 FE, 기업 군집)" % (S["corp_code"].nunique(), len(S)), ""]
    pd.set_option("display.width", 220)
    L.append("Holm 집합 18개 (표시는 계수 (표준오차), 보정 전 p, Holm p)")
    for r in R[R["집합"] == "Holm"].itertuples():
        L.append(f"  {r.사양:46s} {r.계수: .4f} ({r.표준오차:.4f})  p={r.p:.3f}  Holm p={r.Holm_p:.3f}  N={r.관측:,} 기업={r.기업:,} {r.비고}")
    L.append("")
    L.append("참고(Holm 집합 밖)")
    for r in R[R["집합"].isin(["참고", "Q3(참고)"])].itertuples():
        L.append(f"  {r.사양:46s} {r.계수: .4f} ({r.표준오차:.4f})  p={r.p:.3f}  N={r.관측:,} 기업={r.기업:,} {r.비고}")
    L.append("")
    L.append("[신호 기준 판정] (모두 임의 기준)")
    lab = {1: "악화", -1: "개선"}
    L.append(f"  Q2 방향: " + ", ".join(f"{TN[y]}→{lab[int(dir2[y])]}" for y in TN))
    L.append(f"  (a) 3개 결과변수의 방향이 같다: {'예' if a else '아니오'}")
    L.append(f"  (b) Q2 중 Holm p<0.10이 2개 이상: {'예' if b else '아니오'} (Holm p: " + ", ".join(f"{y} {q2.loc[y,'Holm_p']:.3f}" for y in TN) + ")")
    L.append(f"  (c) 위약에서 같은 방향·보정 전 p<0.10이 없다: {'예' if c else '아니오'} (위약 p: " + ", ".join(f"{y} {q5.loc[y,'p']:.3f}" for y in TN) + ")")
    L.append(f"  (d) E_perp의 방향이 Q2와 같다: {'예' if d else '아니오'}")
    L.append(f"  → 신호 기준 충족: {'예 (신호 있음)' if sig else '아니오 (측정에 민감하여 결론 불가 또는 신호 없음)'}")
    text = "\n".join(L)
    print(text)
    (OUT / "사후탐색_요약.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───
