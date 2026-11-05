# 이 파일은 노트북 '03_회귀_구현검증.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 08-03 · 직접 구현한 회귀 검증 (statsmodels와 비교) ───


# ─── 준비 — 불러오기와 경로 ───


"""직접 구현한 고정효과 회귀(02_회귀.py의 fe_ols)를 statsmodels(더미 변수 OLS)와 비교해 구현을 검증한다.
 1) 합성 자료(참값 β=0.7): 계수가 statsmodels와 같은지, 참값 근처인지
 2) 실제 패널의 주 표본 일부: M2 계수가 statsmodels와 같은지, 군집 표준오차 비율
실행: python -X utf8 03_회귀_구현검증.py
"""
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


spec = importlib.util.spec_from_file_location("reg", HERE / "02_회귀.py")
reg = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
spec.loader.exec_module(reg)
if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
    sys.stdout.reconfigure(encoding="utf-8")


def compare(df, y, x, fes, label):
    me = reg.fe_ols(df, y, [x], fes)
    d = df[list(dict.fromkeys([y, x] + fes + ["corp_code"]))].dropna()
    # 싱글톤 제거를 같은 방식으로
    while True:
        keep = np.ones(len(d), bool)
        for f in fes:
            keep &= d[f].map(d[f].value_counts()).values > 1
        if keep.all():
            break
        d = d[keep]
    form = f"{y} ~ {x} + " + " + ".join(f"C({f})" for f in fes)
    sm = smf.ols(form, data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["corp_code"])[0]})
    print(f"[{label}] 직접구현 β={me['beta'][0]:.6f} se={me['se'][0]:.5f} | statsmodels β={sm.params[x]:.6f} se={sm.bse[x]:.5f} | β 차이 {abs(me['beta'][0]-sm.params[x]):.2e}, se 비율 {me['se'][0]/sm.bse[x]:.3f} | N={me['N']}")
    return me, sm


def main():
    rng = np.random.default_rng(1)
    F, T, I = 80, 14, 5
    firm = np.repeat(np.arange(F), T)
    t = np.tile(np.arange(T), F)
    ind = np.repeat(rng.integers(0, I, F), T)
    x = rng.normal(size=F * T) + 0.3 * (firm % 7)
    fe_f = rng.normal(size=F)[firm] * 2
    fe_it = rng.normal(size=I * T).reshape(I, T)[ind, t]
    y = 0.7 * x + fe_f + fe_it + rng.normal(size=F * T)
    d = pd.DataFrame({"y": y, "x": x, "corp_code": firm.astype(str), "ind_t": [f"{a}_{b}" for a, b in zip(ind, t)], "t": t.astype(str)})
    d = d.drop(d.sample(frac=0.08, random_state=2).index)     # 불균형 패널
    compare(d, "y", "x", ["corp_code", "ind_t"], "합성 M2 (참값 0.7)")
    compare(d, "y", "x", ["corp_code", "t"], "합성 M1 (참값 0.7)")
    P = pd.read_csv(HERE.parent.parent / "outputs" / "07_분석" / "패널_기업분기.csv", dtype={"corp_code": str})
    P["corp_code"] = P["corp_code"].str.zfill(8)
    P["ind_t"] = P["업종2"].astype(str) + "_" + P["t"].astype(str)
    P["Ex"] = P["E_pre_A"] * P["tight"]
    S = P[P["표본_주"]]
    firms = S["corp_code"].drop_duplicates().sample(150, random_state=3)
    compare(S[S["corp_code"].isin(firms)], "icr", "Ex", ["corp_code", "ind_t"], "실제 자료 150개 기업 부분표본 M2")


if __name__ == "__main__":
    main()
