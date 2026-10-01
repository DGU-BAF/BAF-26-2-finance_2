"""전체 파이프라인을 순서대로 실행한다.

사용법 (레포 루트 어디에서든):
    python scripts/run_all.py              # 원자재 충격 스크립트 + 노트북 전부
    python scripts/run_all.py --scripts    # 원자재 충격 스크립트(01~05)만
    python scripts/run_all.py --notebooks  # 노트북만

주의
- 노트북은 실행하면 저장된 출력이 새 결과로 바뀐다(nbconvert --inplace).
- src/01_data_check의 두 노트북은 엑셀 입출력에 `artifact_tool`(Claude 환경 전용 모듈)을 쓴다.
  이 모듈이 없으면 엑셀 저장 단계만 건너뛰며, 결과 파일은 레포에 이미 들어 있다.
"""
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "data" / "raw").exists())
SHOCK = ROOT / "src" / "02_rawmaterial_shock"

SCRIPTS = [
    SHOCK / "01_원본데이터_추출" / "IO코드_추출.py",
    SHOCK / "02_카테고리_태깅" / "원자재_품목목록_추출.py",
    SHOCK / "02_카테고리_태깅" / "원자재_카테고리_태깅.py",
    SHOCK / "03_ECOS_IO_매칭" / "ECOS_IO코드_매칭.py",
    SHOCK / "04_크로스워크_병합" / "최종_크로스워크_병합.py",
    SHOCK / "05_충격지표_계산" / "충격지표_계산.py",
]

NOTEBOOKS = (
    sorted((ROOT / "src" / "01_data_check").glob("*.ipynb"))
    + sorted((ROOT / "src" / "03_panel").glob("*.ipynb"))
    + sorted((ROOT / "src" / "04_eda").glob("*.ipynb"), key=lambda p: int(p.name.split("_")[0]))
)


def run_scripts():
    for s in SCRIPTS:
        print(f"[script] {s.relative_to(ROOT)}")
        subprocess.run([sys.executable, "-X", "utf8", str(s)], check=True)


def run_notebooks():
    for nb in NOTEBOOKS:
        print(f"[notebook] {nb.relative_to(ROOT)}")
        subprocess.run(
            [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "--ExecutePreprocessor.timeout=1800", str(nb)],
            check=True,
        )


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--notebooks" not in args:
        run_scripts()
    if "--scripts" not in args:
        run_notebooks()
    print("완료")
