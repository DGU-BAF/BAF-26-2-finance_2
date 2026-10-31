"""Notion 중간발표용 그림 생성 스크립트.

만드는 그림 (outputs/figures/notion/)
1. 04-2_event_study.png   : 인상 이전 연도별 '노출도 효과'(기준연도 2021 대비) 이벤트스터디
2. 04-1_coef_forest.png   : 예비추정 계수(Post × 사전노출도)와 95% 신뢰구간, 표본·ICR 처리 변경별
3. 기존 노트북에 이미 저장된 그림 3개를 PNG로 꺼냄 (금리 국면, 원자재 분산 성분, ICR 분위 곡선)

계산은 src/03_panel/02_사전추세_검정.ipynb(이벤트스터디), src/04_eda/10_다중공선성_ICR변환.ipynb(기본모형, 업종 제외, 윈저화)와 같은 정의를 쓴다.
실행: python src/05_notion_figures/make_notion_figures.py
"""
import base64
import glob
import re
import warnings
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "data" / "raw").exists())
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "figures" / "notion"
OUT.mkdir(parents=True, exist_ok=True)

for fname in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"]:
    try:
        mpl.font_manager.findfont(fname, fallback_to_default=False)
        mpl.rcParams["font.family"] = fname
        break
    except Exception:
        pass
mpl.rcParams["axes.unicode_minus"] = False

INK, GREY, ACC, WARN = "#1F2A44", "#8A93A6", "#2F6FB3", "#C0504D"

tight = pd.read_csv(PROCESSED / "재무_원자재_병합패널.csv", encoding="utf-8-sig")
normal = pd.read_csv(PROCESSED / "평시_재무_원자재_병합패널.csv", encoding="utf-8-sig")

# ------------------------------------------------------------------ 1. 이벤트스터디
exposure = tight.drop_duplicates("업종코드").set_index("업종코드")["사전노출도(%)"].to_dict()
pre = pd.concat([
    normal[normal["연도"] < 2018][["업종코드", "업종", "연도", "ICR"]],
    tight[tight["Post"] == 0][["업종코드", "업종", "연도", "ICR"]],
], ignore_index=True)
pre["노출도"] = pre["업종코드"].map(exposure)
pre = pre.sort_values(["업종코드", "연도"]).reset_index(drop=True)

years = sorted(pre["연도"].unique())
base = 2021
terms = {y: f"I((연도 == {y}) * 1):노출도" for y in years if y != base}
m = smf.ols("ICR ~ " + " + ".join(f"I((연도=={y})*1) : 노출도" for y in terms) + " + C(업종코드) + C(연도)",
            data=pre).fit(cov_type="cluster", cov_kwds={"groups": pre["업종코드"]})
res = pd.DataFrame({"year": list(terms), "beta": [m.params[t] for t in terms.values()],
                    "se": [m.bse[t] for t in terms.values()]})
f_wide = m.f_test(" = ".join(terms.values()) + " = 0")

# 패널 전체 모형: 긴축기 패널(2018~2023) 전 연도 더미(기준 2021), 인상 이전 세 해(2018·2019·2020)만 결합 검정
full = tight.copy()
full["노출도"] = full["업종코드"].map(exposure)
yrs_full = sorted(full["연도"].unique())
t_f = {y: f"I((연도 == {y}) * 1):노출도" for y in yrs_full if y != base}
mf = smf.ols("ICR ~ " + " + ".join(f"I((연도=={y})*1) : 노출도" for y in t_f) + " + C(업종코드) + C(연도)",
             data=full).fit(cov_type="cluster", cov_kwds={"groups": full["업종코드"]})
f_nar = mf.f_test(" = ".join(t_f[y] for y in [2018, 2019, 2020]) + " = 0")
res_full = pd.DataFrame({"year": list(t_f), "beta": [mf.params[t] for t in t_f.values()],
                         "se": [mf.bse[t] for t in t_f.values()], "p": [mf.pvalues[t] for t in t_f.values()]})

print("이벤트스터디 계수 — 넓은 창 모형(2015~2021 사전 자료, 기준 2021):")
print(res.round(4).to_string(index=False))
print("이벤트스터디 계수 — 패널 전체 모형(2018~2023, 기준 2021):")
print(res_full.round(4).to_string(index=False))
print(f"결합 F 넓은 창(2015~2020): F={float(f_wide.fvalue):.4f}, p={float(f_wide.pvalue):.4f}")
print(f"결합 F 좁은 창(2018~2020, 패널 전체 모형): F={float(f_nar.fvalue):.4f}, p={float(f_nar.pvalue):.4f}")

# 그림: 2015~2017은 넓은 창 모형, 2018~2023은 패널 전체 모형(2018~2020 계수는 두 모형이 같다)
plot = pd.concat([res[res["year"] < 2018][["year", "beta", "se"]], res_full[["year", "beta", "se"]]], ignore_index=True)
plot["post"] = plot["year"] > base
fig, ax = plt.subplots(figsize=(9.6, 5.0))
ax.axvspan(2017.5, 2020.5, color="#EEF2F8", zorder=0)
ax.axhline(0, color=GREY, lw=1)
for r in plot.itertuples():
    c = WARN if r.post else INK
    ax.vlines(r.year, r.beta - 1.96 * r.se, r.beta + 1.96 * r.se, color=c, lw=1.6, zorder=2)
    ax.scatter([r.year], [r.beta], color=c if not r.post else "white", edgecolors=c, s=48, zorder=3, linewidths=1.6)
ax.scatter([base], [0], facecolors="white", edgecolors=GREY, s=60, zorder=3)
ax.annotate("기준연도(2021) = 0", (base, 0), textcoords="offset points", xytext=(0, -26), ha="center", fontsize=9, color=GREY)
for r in plot.itertuples():
    if r.year in (2019, 2020, 2022, 2023):
        ax.annotate(f"{r.beta:+.1f}", (r.year, r.beta), textcoords="offset points", xytext=(15, 3), fontsize=10,
                    color=WARN if r.post else INK, fontweight="bold")
ax.set_xticks(sorted(plot["year"].tolist() + [base]))
ax.set_xlim(2014.5, 2023.8)
ax.set_xlabel("연도  (파랑=인상 이전, 빨강=인상 이후)", fontsize=10)
ax.set_ylabel("노출도 1단위당 ICR 차이 (2021 대비, %p)", fontsize=10)
ax.set_title("이벤트스터디: 연도별 '사전 노출도 효과' (기준연도 2021)", fontsize=12, color=INK, loc="left")
ax.text(0.01, 0.97,
        f"인상 이전 계수 결합 F검정:  2015~2020  p={float(f_wide.pvalue):.3f} (비유의)   |   2018~2020(음영)  p={float(f_nar.pvalue):.3f} (위반 신호)",
        transform=ax.transAxes, fontsize=9, color=INK, va="top")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.text(0.01, -0.02,
         "막대: 95% 신뢰구간(업종 군집 표준오차). 모든 계수가 2021년 대비이므로 2021년 자체가 낮거나 높은 해이면 전 구간이 한쪽으로 기운다. 비유의가 평행추세의 증명은 아니다.",
         fontsize=8.3, color=GREY, wrap=True)
fig.tight_layout()
fig.savefig(OUT / "04-2_event_study.png", dpi=170, bbox_inches="tight")
plt.close(fig)

# ------------------------------------------------------------------ 2. 계수 그림
d = tight.rename(columns={"Post×사전노출도": "px", "업종코드": "code", "연도": "year"})
d["업종"] = tight["업종"].values


def fit(df, y="ICR"):
    mm = smf.ols(f"{y} ~ px + C(code) + C(year)", df).fit(
        cov_type="cluster", cov_kwds={"groups": df.code, "use_correction": True, "df_correction": True}, use_t=True)
    ci = mm.conf_int().loc["px"]
    return float(mm.params["px"]), float(ci[0]), float(ci[1]), float(mm.pvalues["px"])


rows = [("기본모형 (40개 업종)", *fit(d))]
for nm in ["반도체", "통신기기", "담배"]:
    rows.append((f"{nm} 제외", *fit(d[d["업종"] != nm])))
lo_, hi_ = d.ICR.quantile([.01, .99])
rows.append(("ICR 윈저화 (1%/99%)", *fit(d.assign(ICRw=d.ICR.clip(lo_, hi_)), y="ICRw")))
fr = pd.DataFrame(rows, columns=["label", "beta", "lo", "hi", "p"])
print(fr.round(3).to_string(index=False))

fig, ax = plt.subplots(figsize=(9, 4.2))
ypos = np.arange(len(fr))[::-1]
ax.axvline(0, color=GREY, lw=1)
for yv, r in zip(ypos, fr.itertuples()):
    c = INK if r.Index == 0 else ACC
    ax.hlines(yv, r.lo, r.hi, color=c, lw=2)
    ax.scatter([r.beta], [yv], color=c, s=55, zorder=3)
    ax.text(r.hi + 6, yv, f"{r.beta:+.1f}  (p={r.p:.2f})", va="center", fontsize=9.5, color=INK)
ax.set_yticks(ypos)
ax.set_yticklabels(fr["label"], fontsize=10)
ax.set_xlabel("Post × 사전 단기부채 노출도 계수 β (%p)", fontsize=10)
ax.set_xlim(min(fr["lo"].min() - 10, -60), fr["hi"].max() + 90)
ax.set_title("예비추정: 계수는 0보다 크고(가설과 반대) 신뢰구간이 0을 포함한다", fontsize=12, color=INK, loc="left")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.text(0.01, -0.03, "막대: 95% 신뢰구간(업종 군집 표준오차). 음수여야 '노출도가 높을수록 인상 후 ICR이 더 악화'라는 가설과 같은 방향.",
         fontsize=8.5, color=GREY)
fig.tight_layout()
fig.savefig(OUT / "04-1_coef_forest.png", dpi=170, bbox_inches="tight")
plt.close(fig)

# ------------------------------------------------------------------ 2-1. 기간 설계 도식 (1-3 분석 아이디어)
rate = pd.read_csv(ROOT / "data" / "raw" / "BOK 기준금리 데이터" / "BOK_기준금리_변경이력.csv", encoding="utf-8-sig")
rate["변경일자"] = pd.to_datetime(rate["변경일자"])
rate = rate.sort_values("변경일자")
xs, ys = [], []
for d0, v in zip(rate["변경일자"], rate["기준금리"]):
    xs.append(d0)
    ys.append(v)
xs.append(pd.Timestamp("2024-12-31"))
ys.append(ys[-1])
fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(10, 5.4), gridspec_kw={"height_ratios": [2.2, 1.5]}, sharex=True)
mask = [(x >= pd.Timestamp("2014-06-01")) for x in xs]
x_in = [x for x, mk in zip(xs, mask) if mk]
y_in = [y for y, mk in zip(ys, mask) if mk]
prev = [y for x, y in zip(xs, ys) if x < pd.Timestamp("2014-06-01")]
x_in = [pd.Timestamp("2014-06-01")] + x_in
y_in = [prev[-1] if prev else y_in[0]] + y_in
ax0.step(x_in, y_in, where="post", color=INK, lw=2)
ax0.set_ylabel("기준금리 (%)", fontsize=10)
ax0.set_title("분석 기간 설계: 인상 이전 재무구조(사전기간) → 인상 이후 ICR 변화(Post)", fontsize=12, color=INK, loc="left")
for s in ("top", "right"):
    ax0.spines[s].set_visible(False)
ax0.annotate("2021-08 인상 시작 (0.50→0.75%)", (pd.Timestamp("2021-08-26"), 0.75), xytext=(pd.Timestamp("2018-12-01"), 2.3),
             fontsize=9, color=WARN, arrowprops=dict(arrowstyle="-", color=WARN))
ax0.annotate("2023-01 정점 3.50%", (pd.Timestamp("2023-01-13"), 3.5), xytext=(pd.Timestamp("2022-06-01"), 3.9),
             fontsize=9, color=INK)
ax0.set_ylim(0, 4.4)
def band(ax, y, x0, x1, label, color):
    ax.barh(y, (pd.Timestamp(x1) - pd.Timestamp(x0)).days, left=mpl.dates.date2num(pd.Timestamp(x0)), height=0.55, color=color, alpha=0.9)
    ax.text(mpl.dates.date2num(pd.Timestamp(x0)) + (pd.Timestamp(x1) - pd.Timestamp(x0)).days / 2, y, label,
            ha="center", va="center", fontsize=9, color="white", fontweight="bold")
band(ax1, 1, "2018-01-01", "2021-01-01", "사전 2018~2020", ACC)
band(ax1, 1, "2021-01-01", "2022-01-01", "전환 2021", GREY)
band(ax1, 1, "2022-01-01", "2024-01-01", "Post 2022~2023", WARN)
band(ax1, 0, "2015-01-01", "2018-01-01", "사전 2015~2017", ACC)
band(ax1, 0, "2018-01-01", "2020-01-01", "가상 Post 2018~2019", "#D9923B")
ax1.set_yticks([0, 1])
ax1.set_yticklabels(["비교기간", "금리상승기"], fontsize=10)
ax1.set_ylim(-0.6, 1.6)
ax1.xaxis_date()
ax1.set_xlim(pd.Timestamp("2014-06-01"), pd.Timestamp("2024-06-01"))
for s in ("top", "right", "left"):
    ax1.spines[s].set_visible(False)
ax1.tick_params(left=False)
fig.text(0.01, -0.01, "비교기간(2015~2019)에도 기준금리가 7차례 변경되어 '충격이 없는 평시'가 아니다. 사전기간 평균으로 노출도·유동비율을 계산한다.",
         fontsize=8.5, color=GREY)
fig.tight_layout()
fig.savefig(OUT / "01-3_period_design.png", dpi=170, bbox_inches="tight")
plt.close(fig)

# ------------------------------------------------------------------ 2-2. 원자재 충격의 변동 구성 (3-3)
shock = pd.read_csv(PROCESSED / "원자재_가격충격_패널.csv", encoding="utf-8-sig")
col = "shock_baseline_1111only"
vt = shock[col].var()
vy = shock.groupby("year")[col].transform("mean").var()
vi = shock.groupby("industry_code")[col].transform("mean").var()
parts = pd.Series({"연도 공통 성분 (모든 업종에 같은 해별 변동)": vy / vt * 100,
                   "업종 고유 평균 성분 (업종마다 일정한 차이)": vi / vt * 100})
parts["그 밖의 업종×연도 변동 (고정효과 후 남는 부분)"] = 100 - parts.sum()
print("원자재 충격 분산 구성(%):", parts.round(2).to_dict())
fig, ax = plt.subplots(figsize=(9, 3.8))
cols = [GREY, "#D9923B", ACC]
ax.barh(range(3)[::-1], parts.values, color=cols, height=0.55)
for yv, v in zip(range(3)[::-1], parts.values):
    ax.text(v + 1.2, yv, f"{v:.1f}%", va="center", fontsize=11, color=INK, fontweight="bold")
ax.set_yticks(range(3)[::-1])
ax.set_yticklabels(parts.index, fontsize=10)
ax.set_xlim(0, 100)
ax.set_xlabel("원자재 충격 전체 변동 중 비중 (%)", fontsize=10)
ax.set_title("원자재 충격의 변동은 어디에서 오나 (고정효과 분해)", fontsize=12, color=INK, loc="left")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.text(0.01, -0.03, f"기준: shock_baseline 40업종×2015~2025 (440관측). 고정효과 반영 후에도 {parts.iloc[2]:.1f}%가 남아 회귀에 투입할 수 있다.",
         fontsize=8.5, color=GREY)
fig.tight_layout()
fig.savefig(OUT / "03-3_shock_variance_clean.png", dpi=170, bbox_inches="tight")
plt.close(fig)

# ------------------------------------------------------------------ 3. 기존 노트북 그림 꺼내기
EXTRACT = [
    ("7_*.ipynb", 20, "01-3_rate_regimes.png"),      # 알려진 국면(긴축·완화) → 1-3 기간 도식, 3-4
    ("5_*.ipynb", 14, "03-3_shock_variance.png"),    # 분산 성분 → 3-3
    ("4_*.ipynb", 20, "03-5_icr_quantile_tail.png"),  # ICR 분위 곡선 → 3-5 (선택)
]
for pattern, cell_idx, outname in EXTRACT:
    f = glob.glob(str(ROOT / "src" / "04_eda" / pattern))[0]
    nb = nbformat.read(f, as_version=4)
    imgs = [o["data"]["image/png"] for o in nb.cells[cell_idx].outputs if "image/png" in o.get("data", {})]
    if imgs:
        data = imgs[0] if isinstance(imgs[0], str) else "".join(imgs[0])
        (OUT / outname).write_bytes(base64.b64decode(data))
        print("추출:", outname)
    else:
        print("그림 없음:", pattern, cell_idx)
print("완료 →", OUT)
