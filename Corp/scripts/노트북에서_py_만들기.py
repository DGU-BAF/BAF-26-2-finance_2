"""노트북(.ipynb)에서 같은 이름의 .py를 자동으로 만든다.   ★ 원본은 노트북, .py는 생성물 ★

왜 이렇게 하나
  - 사람이 읽고 고치는 것은 노트북(마크다운 설명 + 코드 + 실행 출력)이다.
  - 다른 스크립트가 경로로 불러오거나 명령줄로 실행하는 .py는 노트북에서 만들어 낸다. 그래서 코드는 한 벌만 존재한다.
  - 규칙: .py를 직접 고치지 않는다. 고치고 싶으면 노트북에서 고친 뒤 이 스크립트로 .py를 다시 만든다.

노트북 약속 (노트북 메타데이터와 셀 태그)
  - 노트북 메타데이터 "생성_py": 만들 .py 파일 이름(노트북과 같은 폴더). 이 값이 없는 노트북은 건너뛴다.
  - 코드 셀 태그 "노트북전용": .py에 넣지 않는다(설명용 예시, 결과 표시, 실행 셀).
  - 마크다운 셀 태그 "py전용_코드": ```python 코드 블록 안의 코드를 .py에만 넣는다(예: if __name__ == "__main__": main()).
    (노트북은 이 코드를 실행하지 않는다. 노트북에서는 __name__이 "__main__"이라 그대로 두면 명령줄 처리가 실행되어 버리기 때문)
  - 마크다운 셀의 첫 제목 줄은 .py에 구분선 주석으로 들어간다.

사용법 (Corp 폴더에서 또는 어디서든)
  python -X utf8 scripts/노트북에서_py_만들기.py                 # src 아래 모든 노트북에서 .py 생성
  python -X utf8 scripts/노트북에서_py_만들기.py 노트북경로.ipynb   # 하나만
  python -X utf8 scripts/노트북에서_py_만들기.py --검사            # 쓰지 않고 노트북과 .py가 같은지만 확인(어긋나면 종료 코드 1)
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
CORP = Path(__file__).resolve().parent.parent
HEADER = ("# 이 파일은 노트북 '{nb}'에서 자동 생성되었습니다. 직접 수정하지 마세요.\n"
          "# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.\n")


def 만들기(nbpath: Path):
    """(대상 .py 경로, 내용) 또는 None"""
    nb = json.loads(nbpath.read_text(encoding="utf-8"))
    target = nb.get("metadata", {}).get("생성_py")
    if not target:
        return None
    parts = []
    for c in nb["cells"]:
        tags = c.get("metadata", {}).get("tags", [])
        src = "".join(c.get("source", ""))
        if c["cell_type"] == "code":
            if "노트북전용" in tags or not src.strip():
                continue
            parts.append(src.rstrip())
        elif c["cell_type"] == "markdown":
            if "py전용_코드" in tags:
                m = re.search(r"```python\n(.*?)\n```", src, re.S)
                if not m:
                    raise ValueError(f"{nbpath.name}: py전용_코드 셀에 ```python 블록이 없습니다")
                parts.append(m.group(1).rstrip())
            else:
                for line in src.splitlines():
                    if re.match(r"#{1,3} ", line):
                        parts.append("# " + "─" * 3 + " " + line.lstrip("#").strip() + " " + "─" * 3)
                        break
    text = HEADER.format(nb=nbpath.name) + "\n" + "\n\n\n".join(parts) + "\n"
    return nbpath.parent / target, text


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--검사" in sys.argv
    if args:
        nbs = [Path(a).resolve() for a in args]
    else:
        nbs = sorted(p for p in (CORP / "src").rglob("*.ipynb") if ".ipynb_checkpoints" not in p.parts)
    bad = 0
    n = 0
    for nb in nbs:
        res = 만들기(nb)
        if res is None:
            continue
        n += 1
        py, text = res
        if check:
            same = py.exists() and py.read_bytes() == text.encode("utf-8")
            print(("일치  " if same else "어긋남") + f"  {nb.name} → {py.name}")
            bad += not same
        else:
            py.write_bytes(text.encode("utf-8"))
            print(f"생성: {py.relative_to(CORP)}  (원본 {nb.name})")
    if not n:
        print("'생성_py' 메타데이터가 있는 노트북이 없습니다.")
    if check and bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
