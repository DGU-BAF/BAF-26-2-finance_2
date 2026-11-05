"""사후 탐색 Q1: 주 표본에서 |ICR| 상위 20개 기업-분기의 자료를 원본 응답과 대조한다. (회귀 없음, docs/A_사후탐색_계획_11-05.md)
각 관측에 대해: ICR·영업이익 TTM·금융비용 TTM, 해당 4분기의 보고서별 추출값(3개월·누적), 원본 손익계산서에서 '금융·이자·영업이익' 행을 출력한다.
실행: python -X utf8 04_Q1_극단값_점검.py
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OUT = config.BASE / "outputs" / "07_분석"
FS_DIR = config.RAW / "fs"
CODE = config.REPORTS


def norm(s):
    return re.sub(r"\s+", "", s or "")


def main():
    P = pd.read_csv(OUT / "패널_기업분기.csv", dtype={"corp_code": str})
    P["corp_code"] = P["corp_code"].str.zfill(8)
    X = pd.read_csv(OUT / "추출값_보고서별.csv", dtype={"corp_code": str})
    X["corp_code"] = X["corp_code"].str.zfill(8)
    S = P[P["표본_주"] & P["icr"].notna()].copy()
    top = S.loc[S["icr"].abs().nlargest(20).index]
    lines = []
    for r in top.itertuples():
        y, q = int(r.year), int(r.q)
        lines.append("=" * 90)
        lines.append(f"기업 {r.corp_code} {y}Q{q}  ICR={r.icr:,.1f}  영업이익TTM={r.oi_ttm:,.0f}  금융비용TTM={r.fc_ttm:,.0f}  자산={r.assets:,.0f}")
        sub = X[(X["corp_code"] == r.corp_code) & (X["year"].isin([y - 1, y]))].copy()
        sub["ord"] = sub["report"].map({"Q1": 0, "H1": 1, "Q3": 2, "FY": 3})
        sub = sub.sort_values(["year", "ord"])
        for s in sub.itertuples():
            lines.append(f"   {s.year} {s.report:2s} {s.fs}  영업이익 3개월={s.op_income_m3} 누적={s.op_income_cum} | 금융비용 3개월={s.fin_cost_m3} 누적={s.fin_cost_cum}")
        # 원본 손익계산서의 금융·이자·영업이익 행 (해당 연도 사업보고서, 없으면 3분기)
        for rep in ("FY", "Q3"):
            for fs in ("CFS", "OFS"):
                p = FS_DIR / f"{r.corp_code}_{y}_{CODE[rep]}_{fs}.json"
                if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("status") == "000":
                    d = json.loads(p.read_text(encoding="utf-8"))["list"]
                    rows = [x for x in d if x.get("sj_div") in ("IS", "CIS") and re.search(r"금융|이자|영업이익|영업손", norm(x.get("account_nm")))]
                    lines.append(f"   [원본 {y} {rep} {fs} 손익계산서 일부]")
                    for x in rows[:14]:
                        lines.append(f"      {norm(x['account_nm']):26s} 당기={x.get('thstrm_amount')} 누적={x.get('thstrm_add_amount')}")
                    break
            else:
                continue
            break
    text = "\n".join(lines)
    (OUT / "Q1_극단값_점검.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
