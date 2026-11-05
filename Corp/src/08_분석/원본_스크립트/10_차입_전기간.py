"""M4 준비: 전 기간(2018~2024Q3) 모든 보고서에서 유동 구간·비유동 구간 이자부 차입 합(총차입금)을 만든다.
06_노출도E_만들기.py의 규칙(위치 방식, 유동성장기부채 포함, 합계·세부 행 이중 계산 제거)을 그대로 쓴다. 금액·계산 규칙은 06과 같고 대상 기간만 넓다.
저장: outputs/07_분석/모듈별/차입_전기간.csv
"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402

spec = importlib.util.spec_from_file_location("e06", HERE.parent / "07_계정확보" / "06_노출도E_만들기.py")
e06 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e06)
sys.stdout.reconfigure(encoding="utf-8")
OUT = config.BASE / "outputs" / "07_분석" / "모듈별"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    chosen = {}
    for r in csv.DictReader(open(e06.LOG, encoding="utf-8-sig")):
        if r["status"] == "000":
            k = (r["corp_code"], int(r["year"]), r["report"])
            if k not in chosen or r["fs_div"] == "CFS":
                chosen[k] = r["fs_div"]
    rows = []
    for i, ((c, y, rep), fs) in enumerate(sorted(chosen.items()), 1):
        d = json.loads((e06.FS_DIR / f"{c}_{y}_{config.REPORTS[rep]}_{fs}.json").read_text(encoding="utf-8"))["list"]
        o = e06.one_report(d)
        rows.append({"corp_code": c, "year": y, "report": rep, "fs": fs, "state": o["state"], "num_C": o["num_C"], "num_N": o["num_N"], "assets": o["assets"]})
        if i % 8000 == 0:
            print(f"  {i:,}개 읽음")
    pd.DataFrame(rows).to_csv(OUT / "차입_전기간.csv", index=False, encoding="utf-8-sig")
    print("저장", len(rows), "행")


if __name__ == "__main__":
    main()
