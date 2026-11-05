"""추가 탐색 N1~N7 (docs/A_추가탐색계획_11-05.html, 판정 세부는 같은 문서 7절에 실행 전 고정). 36개를 1회 실행한다. 전부 사후 탐색.
실행: python -X utf8 13_추가탐색.py
"""
import csv
import html
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
from lib import FE, LABEL, MOD, WORSE, add_T, config, finish, fit, load_panel, rows_from  # noqa: E402

spec = importlib.util.spec_from_file_location("mods", HERE / "11_모듈.py")
mods = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mods)
sys.stdout.reconfigure(encoding="utf-8")
T3 = ["T1", "T2", "T3"]
DOCS = config.BASE / "docs"


def main():
    P = load_panel()
    S = mods.prep_S(P)

    def pre_rank(tmax, minn):
        d = S[S["t"] <= tmax].groupby("corp_code")["T3"].agg(["mean", "count"])
        return d[d["count"] >= minn]["mean"]

    S["pr"] = S["corp_code"].map(pre_rank(9, 6))
    S["pr19"] = S["corp_code"].map(pre_rank(3, 3))
    S["pr_x"] = S["pr"] * S["tight"]
    S["pr19_x"] = S["pr19"] * S["tight"]
    rows = []
    VAR = (("pr", "pr_x", "사전ICR수준①"), ("pr19", "pr19_x", "사전ICR수준②(2019만)"))
    # N1, N2
    for v, vx, lab in VAR:
        for y in T3:
            r = fit(S, y, ["Ex", vx], FE)
            rows += rows_from(r, "N", f"N1 {lab} 통제", ["E×Tight", lab + "×Tight"], "N12")
            r = fit(S, y, ["Ex", vx, "size_x", "lev_x", "roa_x"], FE)
            rows += rows_from(r, "N", f"N2 {lab}+사전특성 통제", ["E×Tight", lab + "×Tight", "ln자산×Tight", "레버리지×Tight", "영업이익/자산×Tight"], "N12")
    # N3 분위 비교 (사전ICR수준①)
    F = S.drop_duplicates("corp_code").dropna(subset=["pr"])
    q1, q2 = F["pr"].quantile([1 / 3, 2 / 3])
    S["pt"] = np.where(S["pr"] <= q1, 1, np.where(S["pr"] <= q2, 2, 3))
    for k in (1, 2, 3):
        S[f"Ex_p{k}"] = np.where(S["pr"].notna(), S["Ex"] * (S["pt"] == k), np.nan)
    for y in T3:
        r = fit(S, y, ["Ex_p1", "Ex_p2", "Ex_p3"], FE)
        rows += rows_from(r, "N", "N3 사전ICR수준① 3분위별 E×Tight", ["사전ICR 하위", "중간", "상위"], "N3", fam_all=True)
    # N4 잔차 E
    for v, vx, lab in VAR:
        Fv = S.drop_duplicates("corp_code").dropna(subset=["E_pre_A", "lev_pre", v, "roa_pre", "ln_assets_pre"])
        X = np.column_stack([np.ones(len(Fv)), Fv["lev_pre"], Fv[v], Fv["roa_pre"], Fv["ln_assets_pre"]])
        coef = np.linalg.lstsq(X, Fv["E_pre_A"].to_numpy(), rcond=None)[0]
        res = Fv["E_pre_A"].to_numpy() - X @ coef
        S["Ep2_x"] = S["corp_code"].map(dict(zip(Fv["corp_code"], res))) * S["tight"]
        for y in T3:
            r = fit(S, y, ["Ep2_x"], FE)
            rows += rows_from(r, "N", f"N4 잔차 E({lab}) ×Tight", ["E_perp2×Tight"], "N4")
    # N5 이탈·ICR 미정의 기업 포함 (955곳)
    S5 = add_T(P[(~P["혼재"]) & (P["E정의분기"] >= 8)].copy())
    for y in T3:
        rows += rows_from(fit(S5, y, ["Ex"], FE), "N", "N5 인상기 ICR 8개 이상 규칙 삭제(955곳)", ["E×Tight"], "N5")
    R5 = pd.read_csv(config.BASE / "outputs" / "04_본수집" / "본수집_결과_기업별.csv", dtype={"corp_code": str})
    R5["corp_code"] = R5["corp_code"].str.zfill(8)
    f5 = S5.drop_duplicates("corp_code").merge(R5[["corp_code", "마지막_자료"]], on="corp_code")
    f5["이탈후보"] = f5["마지막_자료"] != "2024Q3"
    ex = f5[f5["이탈후보"]]
    main_firms = set(S["corp_code"])
    desc = [f"N5 기술통계: 955곳 중 마지막 자료가 2024Q3 이전인 이탈 후보 {len(ex)}곳 (E_pre_A 평균 {ex['E_pre_A'].mean():.3f}, 중앙값 {ex['E_pre_A'].median():.3f}; "
            f"나머지 평균 {f5[~f5['이탈후보']]['E_pre_A'].mean():.3f}, 중앙값 {f5[~f5['이탈후보']]['E_pre_A'].median():.3f})",
            f"   그중 주 표본(789곳)에 포함된 이탈 후보 {int(ex['corp_code'].isin(main_firms).sum())}곳, 제외된 이탈 후보 {int((~ex['corp_code'].isin(main_firms)).sum())}곳",
            f"   인상기 ICR 관측이 0개인 기업 {int((f5['post_icr_n'] == 0).sum())}곳, 8개 미만 {int((f5['post_icr_n'] < 8).sum())}곳"]
    # N7 통제 후 위약
    tmap = S.groupby("t")["tight"].first().to_dict()
    Sp = S[S["t"] <= 9].copy()
    for t0, nm in ((4, "2020Q1"), (6, "2020Q3")):
        Sp["tp"] = Sp["t"].map(lambda t: tmap[t - t0 + 10] if t >= t0 else 0.0)
        Sp["Epl"] = Sp["E_pre_A"] * Sp["tp"]
        Sp["pr19_p"] = Sp["pr19"] * Sp["tp"]
        for y in T3:
            r = fit(Sp, y, ["Epl", "pr19_p"], FE)
            rows += rows_from(r, "N", f"N7 위약 가짜 긴축 {nm} (사전ICR②×Tight_p 통제)", ["E×Tight_p", "사전ICR수준②×Tight_p"], "N7")
    R = finish(rows, "N", "결과")
    key = R[(R["변수"].isin(["E×Tight", "E_perp2×Tight", "E×Tight_p", "사전ICR 하위", "중간", "상위"]))]

    # 판정 (계획서 7절)
    def sel(prefix, var="E×Tight"):
        d = R[(R["사양"].str.startswith(prefix)) & (R["변수"] == var)]
        return d
    n2a = sel("N2 사전ICR수준①").set_index("결과변수")
    n2b = sel("N2 사전ICR수준②").set_index("결과변수")
    dA = {y: int(np.sign(n2a.loc[y, "계수"]) * WORSE[y]) for y in T3}      # +1 악화, -1 개선
    dB = {y: int(np.sign(n2b.loc[y, "계수"]) * WORSE[y]) for y in T3}
    same = len(set(dA.values())) == 1 and len(set(dB.values())) == 1 and set(dA.values()) == set(dB.values())
    direction = list(dA.values())[0] if same else 0
    c1 = same
    c2 = int((n2a["Holm_p"] < 0.10).sum()) >= 2
    n3 = R[R["사양"].str.startswith("N3")]
    ok3 = 0
    for y in T3:
        g = n3[n3["결과변수"] == y]
        ok3 += int((np.sign(g["계수"]) * WORSE[y] == direction).sum()) >= 2
    c3 = same and ok3 >= 2
    n7 = R[R["사양"].str.startswith("N7") & (R["변수"] == "E×Tight_p")]
    bad = n7[(np.sign(n7["계수"]) * n7["결과변수"].map(WORSE) == direction) & (n7["p"] < 0.10)]
    c4 = same and len(bad) == 0
    lab = {1: "악화", -1: "개선"}
    if same and c2 and c3 and c4:
        verdict = "악화 신호 (가설 방향)" if direction == 1 else "개선이 통제 후에도 남음"
    else:
        verdict = "통제 후 신호 없음"
    L = []
    L.append("[N 결과: 핵심 계수만]")
    for r in key.itertuples():
        hp = "" if pd.isna(r.Holm_p) else f" Holm={r.Holm_p:.3f}"
        L.append(f"  {r.사양[:52]:52s} {LABEL.get(r.결과변수, r.결과변수)[:14]:14s} {str(r.변수)[:14]:14s} {r.계수: .4f} ({r.표준오차:.4f}) p={r.p:.3f}{hp} N={r.관측:,}")
    L += [""] + desc + [""]
    L.append("[판정 세부]")
    L.append(f"  N2① 방향: " + ", ".join(f"{LABEL[y]}→{lab[dA[y]]}" for y in T3) + " | N2② 방향: " + ", ".join(f"{LABEL[y]}→{lab[dB[y]]}" for y in T3))
    L.append(f"  조건① N2 ①·② 방향이 모두 같다: {'예' if c1 else '아니오'}")
    L.append(f"  조건② N2①의 2개 이상이 Holm p<0.10: {'예' if c2 else '아니오'} (Holm p: " + ", ".join(f"{LABEL[y]} {n2a.loc[y,'Holm_p']:.3f}" for y in T3) + ")")
    L.append(f"  조건③ N3: 결과변수 3개 중 {ok3}개에서 3분위 중 2개 이상이 같은 방향: {'예' if c3 else '아니오'}")
    L.append(f"  조건④ N7: 같은 방향·p<0.10 위약 {len(bad)}개: {'예(없음)' if c4 else '아니오'}")
    L.append(f"  → 판정: {verdict}")
    text = "\n".join(L)
    print(text)
    (MOD / "N_요약.txt").write_text(text, encoding="utf-8")

    # HTML
    def tab(df, cols):
        h = "<thead><tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr></thead>"
        b = "".join("<tr>" + "".join(f"<td>{html.escape(str(r[c]))}</td>" for c in cols) + "</tr>" for _, r in df.iterrows())
        return f"<div class='tw'><table>{h}<tbody>{b}</tbody></table></div>"
    d = R.copy()
    for c in ("계수", "표준오차"):
        d[c] = d[c].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")
    for c in ("p", "Holm_p"):
        d[c] = d[c].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    d["결과변수"] = d["결과변수"].map(lambda y: LABEL.get(y, y))
    cols = ["사양", "결과변수", "변수", "계수", "표준오차", "p", "Holm_p", "방향", "관측", "기업"]
    css = """<style>:root{--ink:#1d2a33;--line:#dde4e8;--bg:#f4f6f7;--paper:#fff;--amber:#8a5a00;--ambbg:#fff4dc;--code:#eef2f4}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){--ink:#e6edf1;--line:#33424c;--bg:#12191e;--paper:#1a242b;--amber:#f0c36a;--ambbg:#3a3220;--code:#243139}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 'Malgun Gothic',sans-serif}.wrap{max-width:1000px;margin:0 auto;padding:18px 14px 60px}
section{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin-top:14px}.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12.5px;min-width:640px}th{background:var(--code);text-align:left}th,td{border-bottom:1px solid var(--line);padding:5px 8px}.box{background:var(--ambbg);border-left:4px solid var(--amber);border-radius:8px;padding:10px 14px;margin:10px 0}pre{background:var(--code);padding:10px 12px;border-radius:8px;overflow-x:auto;font-size:12.5px}</style>"""
    page = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>A 추가 탐색 결과</title>{css}</head><body><div class='wrap'>"
            "<h1>A 추가 탐색 결과 (사후 탐색 3차, 2026-11-05)</h1>"
            "<div class='box'><b>지위.</b> A_추가탐색계획_11-05.html에서 실행 전에 고정한 36개와 판정 세부를 그대로 1회 실행했습니다. 이전 결과를 본 뒤의 설계인 사후 탐색이며 확인 증거가 아닙니다. <b>이번이 마지막 사양 탐색 라운드</b>입니다.</div>"
            f"<section><h2>판정: {verdict}</h2><pre>{html.escape(chr(10).join(L[len(key)+1:]))}</pre></section>"
            f"<section><h2>전체 36개 사양 (모든 계수)</h2>{tab(d, cols)}</section></div></body></html>")
    (DOCS / "A_추가탐색결과_11-05.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
