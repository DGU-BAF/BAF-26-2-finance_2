# 이 파일은 노트북 '12_통합정리.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 08-12 · M11: 모듈 결과 통합 정리와 종합 판정 ───


# ─── 준비 — 불러오기와 경로 ───


"""M11: 모듈 M1~M10의 결과 csv를 읽어 방향·유의 요약표와 신호 기준 종합 판정을 만들고 HTML로 저장한다. 전부 사후 탐색.
종합 판정 규칙(실행 전 고정, 파이프라인 문서 4절의 4가지에 대응):
 (a) M1의 M2 사양(E×Tight)에서 asinh·ICR<1·순위 3개 결과변수의 경제적 방향이 같다
 (b) 위 3개 중 2개 이상이 M1 가족(15개) Holm p < 0.10
 (c) M3 위약 12개 중 같은 방향이면서 보정 전 p<0.10인 것이 없다
 (d) M7의 S(단기 비중×Tight) 계수 방향이 asinh·ICR<1·순위 3개에서 모두 (a)의 방향과 같다
 네 가지를 모두 만족해야 '신호'. (모두 임의 기준, 확인 증거가 아님)
저장: Corp/docs/A_분석_통합결과_11-05.html, outputs/07_분석/모듈별/M11_요약.csv
"""
import html
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from lib import LABEL, MOD, WORSE, config
if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
    sys.stdout.reconfigure(encoding="utf-8")


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


DOCS = config.BASE / "docs"


def load(m):
    p = MOD / f"{m}_결과.csv"
    return pd.read_csv(p) if p.exists() else None


def main():
    mods = {m: load(m) for m in ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"]}
    rows = []
    for m, R in mods.items():
        if R is None:
            continue
        sel = R[(~R["결과변수"].isna()) & (R["결과변수"].isin(WORSE.keys())) & (R["변수"].astype(str).str.len() > 0)].copy()
        sel = sel[~sel["사양"].astype(str).str.startswith(("이벤트", "사전 계수"))]
        sel = sel[~sel["사양"].astype(str).str.startswith("업종 제외")]
        sel = sel[sel["표준오차"].notna()]
        if len(sel) == 0:
            continue
        worse = int((sel["방향"] == "악화").sum())
        better = int((sel["방향"] == "개선").sum())
        sig = int((sel["p"] < 0.05).sum())
        sig_w = int(((sel["p"] < 0.05) & (sel["방향"] == "악화")).sum())
        sig_b = int(((sel["p"] < 0.05) & (sel["방향"] == "개선")).sum())
        rows.append({"모듈": m, "계수 수": len(sel), "악화 방향": worse, "개선 방향": better, "p<0.05": sig, "그중 악화": sig_w, "그중 개선": sig_b})
    S = pd.DataFrame(rows)
    S.to_csv(MOD / "M11_요약.csv", index=False, encoding="utf-8-sig")

    # 종합 판정
    J = []
    M1 = mods["M1"]
    base = M1[(M1["사양"].str.startswith("M2")) & (M1["변수"] == "E×Tight") & (M1["결과변수"].isin(["T1", "T2", "T3"]))].set_index("결과변수")
    dirs = {y: np.sign(base.loc[y, "계수"]) * WORSE[y] for y in ["T1", "T2", "T3"]}
    a = len(set(dirs.values())) == 1
    b = int((base["Holm_p"] < 0.10).sum()) >= 2
    pl = mods["M3"][mods["M3"]["사양"].str.startswith("위약")]
    main_dir = list(dirs.values())[0] if a else 99
    bad = pl[(np.sign(pl["계수"]) * pl["결과변수"].map(WORSE) == main_dir) & (pl["p"] < 0.10)]
    c = a and len(bad) == 0
    s7 = mods["M7"][(mods["M7"]["변수"] == "S 단기 비중×Tight") & (mods["M7"]["결과변수"].isin(["T1", "T2", "T3"]))].set_index("결과변수")
    d = a and all(np.sign(s7.loc[y, "계수"]) * WORSE[y] == main_dir for y in ["T1", "T2", "T3"] if y in s7.index) and len(s7) == 3
    sig = a and b and c and d
    lab = {1: "악화", -1: "개선"}
    J = [("(a) M2 사양의 3개 결과변수 방향이 같다", a, ", ".join(f"{LABEL[y]}→{lab[int(dirs[y])]}" for y in dirs)),
         ("(b) 그중 2개 이상이 M1 가족 Holm p<0.10", b, ", ".join(f"{LABEL[y]} {base.loc[y,'Holm_p']:.3f}" for y in dirs)),
         ("(c) 위약 12개 중 같은 방향·p<0.10 없음", c, f"해당 {len(bad)}개" + ("" if len(bad) == 0 else ": " + ", ".join(f"{r.사양[-8:]} {r.결과변수} p={r.p:.3f}" for r in bad.itertuples()))),
         ("(d) M7의 S(단기 비중) 방향이 (a)와 같다", d, ", ".join(f"{LABEL[y]} {s7.loc[y,'계수']:.3f}(p={s7.loc[y,'p']:.3f})" for y in s7.index))]

    def table(df, cols):
        h = "<thead><tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr></thead>"
        b_ = "".join("<tr>" + "".join(f"<td>{html.escape(str(r[c]))}</td>" for c in cols) + "</tr>" for _, r in df.iterrows())
        return f"<div class='tw'><table>{h}<tbody>{b_}</tbody></table></div>"

    def fmt(df):
        d = df.copy()
        for c in ("계수", "표준오차"):
            if c in d:
                d[c] = d[c].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")
        for c in ("p", "Holm_p"):
            if c in d:
                d[c] = d[c].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
        return d

    css = """<style>:root{--ink:#1d2a33;--muted:#5d6b75;--line:#dde4e8;--bg:#f4f6f7;--paper:#fff;--blue:#165a70;--amber:#8a5a00;--ambbg:#fff4dc;--redbg:#fbeceb;--red:#b3392f;--grnbg:#e8f4ec;--green:#2d6b3f;--code:#eef2f4}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){--ink:#e6edf1;--muted:#a3b1ba;--line:#33424c;--bg:#12191e;--paper:#1a242b;--blue:#7cc4dc;--amber:#f0c36a;--ambbg:#3a3220;--redbg:#3a2220;--red:#ff9a90;--grnbg:#1e3326;--green:#8fd6a4;--code:#243139}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 'Malgun Gothic',sans-serif}.wrap{max-width:1000px;margin:0 auto;padding:18px 14px 70px}
section{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-top:14px}h1{font-size:23px}h2{font-size:18px;margin:0 0 6px}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;min-width:560px}th{background:var(--code);text-align:left}th,td{border-bottom:1px solid var(--line);padding:6px 9px}
.box{border-radius:8px;padding:10px 14px;margin:10px 0}.amb{background:var(--ambbg);border-left:4px solid var(--amber)}.ok{background:var(--grnbg);border-left:4px solid var(--green)}.no{background:var(--redbg);border-left:4px solid var(--red)}img{max-width:100%}.small{font-size:12.5px;color:var(--muted)}</style>"""
    parts = [f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>A 분석 통합 결과</title>{css}</head><body><div class='wrap'>",
             "<h1>A 트랙 통합 결과 (사후 탐색 2차, 2026-11-05)</h1>",
             "<div class='box amb'><b>지위.</b> 파이프라인 문서(A_분석_파이프라인_v1대응_11-05.html)에서 실행 전에 고정한 목록(M0~M11)을 그대로 돌린 결과입니다. 첫 회귀와 1차 탐색 결과를 본 뒤의 설계이므로 <b>전부 사후 탐색</b>이며 가설의 확인 증거가 아닙니다. 모든 계수를 같은 파일에 남겼고 결과를 본 뒤 사양을 바꾸지 않았습니다.</div>"]
    parts.append("<section><h2>1. 모듈별 방향·유의 요약</h2><p class='small'>방향은 결과변수별로 '악화'(원래 가설 방향)·'개선'으로 통일했습니다. 이벤트 스터디 계수와 업종 하나씩 제외 72개는 별도 절에서 범위로 보고하며 이 표에 넣지 않았습니다.</p>"
                 + table(S, list(S.columns)) + "</section>")
    jr = "".join(f"<tr><td>{n}</td><td>{'예' if ok else '아니오'}</td><td>{html.escape(t)}</td></tr>" for n, ok, t in J)
    parts.append(f"<section><h2>2. 신호 기준 종합 판정 (임의 기준)</h2><div class='tw'><table><thead><tr><th>기준</th><th>충족</th><th>근거</th></tr></thead><tbody>{jr}</tbody></table></div>"
                 f"<div class='box {'ok' if sig else 'no'}'><b>종합: {'신호 기준 충족' if sig else '신호 기준 불충족 (측정에 민감하여 결론 불가 또는 신호 없음)'}</b> — 어느 쪽이든 가설의 확인 증거나 기각 근거로 쓰지 않습니다.</div></section>")
    names = {"M1": "M1 기본 사다리 (결과변수 5개)", "M2": "M2 기간·변환 (업종 제외 72개는 그림 참조)", "M3": "M3 사전 공동검정·위약 (분기별 계수는 그림 참조)", "M4": "M4 구성요소",
             "M5": "M5 실제 기준금리", "M6": "M6 극단값", "M7": "M7 차입구조 분리", "M8": "M8 wild bootstrap", "M9": "M9 분할"}
    for m in ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"]:
        R = mods[m]
        if R is None:
            continue
        d = R.copy()
        if m == "M2":
            d = d[~d["사양"].astype(str).str.startswith("업종 제외")]
        if m == "M3":
            d = d[~d["사양"].astype(str).str.startswith("이벤트")]
        cols = [c for c in ["사양", "결과변수", "변수", "계수", "표준오차", "p", "Holm_p", "방향", "관측", "기업", "비고"] if c in d.columns]
        d["결과변수"] = d["결과변수"].map(lambda y: LABEL.get(y, y))
        parts.append(f"<section><h2>{names[m]}</h2>{table(fmt(d), cols)}</section>")
    for img, ttl in (("M2_업종제외범위.png", "M2 업종 하나씩 제외 — 계수 범위"), ("M3_이벤트스터디.png", "M3 이벤트 스터디")):
        if (MOD / img).exists():
            import base64
            b64 = base64.b64encode((MOD / img).read_bytes()).decode()
            parts.append(f"<section><h2>{ttl}</h2><img alt='{ttl}' src='data:image/png;base64,{b64}'></section>")
    t10 = MOD / "M10_분해.csv"
    if t10.exists():
        T = pd.read_csv(t10).round(3)
        parts.append(f"<section><h2>M10 ICR 변화의 회계 분해 (기술통계)</h2>{table(T, list(T.columns))}</section>")
    parts.append("<section><h2>한계</h2><ul><li>모든 결과는 사후 탐색이며 팀 확인 전 규칙(E 정의, ICR=영업이익/금융비용, 표본, 긴축 변수)에 기대고 있습니다.</li><li>E와 총차입 수준(레버리지)의 상관이 0.90이라 단기 비중 고유의 효과와 분리하기 어렵습니다.</li><li>ICR(영업이익÷금융비용)은 금융비용이 매우 작은 기업에서 폭발하며, 금융비용에는 이자가 아닌 항목이 섞입니다.</li><li>원자재·환율 충격, 경기 통제, 유동성 조절, 이탈 기업 포함 분석은 이번에 하지 않았습니다.</li></ul></section></div></body></html>")
    (DOCS / "A_분석_통합결과_11-05.html").write_text("".join(parts), encoding="utf-8")
    print(S.to_string(index=False))
    for n, ok, t in J:
        print(f"{n}: {'예' if ok else '아니오'} | {t}")
    print("종합:", "신호 기준 충족" if sig else "신호 기준 불충족")


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───
