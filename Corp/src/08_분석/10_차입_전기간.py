# 이 파일은 노트북 '10_차입_전기간.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 08-10 · M4 준비: 전 기간 총차입금 ───


# ─── 준비 — 불러오기와 경로 ───


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
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


spec = importlib.util.spec_from_file_location("e06", HERE.parent / "07_계정확보" / "06_노출도E_만들기.py")
e06 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e06)
if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
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


# ─── 저장된 결과 미리보기 (맨 위 5행) ───
