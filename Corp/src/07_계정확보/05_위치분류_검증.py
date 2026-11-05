# 이 파일은 노트북 '05_위치분류_검증.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 07-05 · '위치 방식' 검증 (유동/비유동 구간으로 단기·장기 판정) ───


# ─── 준비 — 불러오기와 경로 ───


"""재무상태표에서 차입·사채 행의 '단기(유동)/장기(비유동)'를 위치로 판단하는 방법을 전체 응답으로 검증한다.

방법(위치 방식): 재무상태표(BS)에서 '유동부채' 머리행과 '비유동부채' 머리행을 찾고, 차입·사채 행이 그 사이 어디에 있는지로 단기/장기를 판단한다.
검증: 위치 판단을 (1) 계정 이름 접두어(유동·단기 / 장기·비유동), (2) 표준 계정코드(account_id)의 의미와 비교해 어긋남을 센다.
금액은 읽지 않는다. ICR·E를 계산하지 않는다.

차입·사채 행의 정의(탐색용, 에이전트가 정함): 정규화한 계정 이름에 '차입' 또는 '사채'가 있고,
 '리스', '할인발행차금', '상환할증금', '대손', '이자', '미지급', '매입', '채권' 가운데 하나라도 있으면 제외.
실행: python -X utf8 05_위치분류_검증.py (저장된 파일만 읽음, 키 필요 없음)
저장: outputs/05_계정확보/위치분류_검증_요약.txt, 위치분류_검증_어긋남_목록.csv
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402
if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
    sys.stdout.reconfigure(encoding="utf-8")


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
OUTDIR = config.BASE / "outputs" / "05_계정확보"
FS_DIR = config.RAW / "fs"
DEBT = re.compile(r"차입|사채")
EXCL = re.compile(r"리스|할인발행차금|상환할증금|대손|이자|미지급|매입|채권")
# 대소문자를 구분한다: 'NoncurrentPortion…' 안의 소문자 'currentPortion'이 단기로 잘못 잡히지 않게 하려는 것(1차 실행의 규칙 결함을 고침)
ID_C = re.compile(r"Shortterm|ShortTerm|CurrentPortion|CurrentBond|CurrentBorrow|CurrentLoan")
ID_N = re.compile(r"LongTerm|Longterm|Noncurrent|NonCurrent")


def norm(s):
    return re.sub(r"\s+", "", s or "")


def name_sig(nm):
    # '비유동차입금의유동성대체부분', '장기차입금(유동성)'처럼 이름이 장기로 시작해도 1년 안에 갚을 몫이면 단기(1차 실행의 규칙 결함을 고침)
    if re.search(r"유동성|\(유동\)|유동성대체", nm) and not re.match(r"^비유동(?!.*유동성)", nm):
        return "C"
    if re.match(r"^(유동|단기)", nm):
        return "C"
    if re.match(r"^(장기|비유동)", nm):
        return "N"
    return "?"


def id_sig(aid):
    if aid and not aid.startswith("-"):
        if ID_C.search(aid):
            return "C"
        if ID_N.search(aid):
            return "N"
    return "?"


def sections(bs):
    """BS 행 목록(ord순)에서 각 행의 구간: C(유동부채 구간) / N(비유동부채 구간) / O(그 밖)"""
    hdr = []
    for i, r in enumerate(bs):
        nm, aid = norm(r["account_nm"]), r.get("account_id", "")
        if nm == "유동부채" or aid == "ifrs-full_CurrentLiabilities":
            hdr.append((i, "C"))
        elif nm == "비유동부채" or aid == "ifrs-full_NoncurrentLiabilities":
            hdr.append((i, "N"))
        elif nm == "부채총계" or aid == "ifrs-full_Liabilities":
            hdr.append((i, "T"))
    has_c = any(t == "C" for _, t in hdr)
    has_n = any(t == "N" for _, t in hdr)
    sec = {}
    cur = "O"
    hi = 0
    for i, r in enumerate(bs):
        while hi < len(hdr) and hdr[hi][0] <= i:
            cur = {"C": "C", "N": "N", "T": "O"}[hdr[hi][1]]
            hi += 1
        sec[i] = cur
    return sec, has_c, has_n


def main():
    chosen = {}
    for r in csv.DictReader(open(LOG, encoding="utf-8-sig")):
        if r["status"] == "000":
            k = (r["corp_code"], int(r["year"]), r["report"])
            if k not in chosen or r["fs_div"] == "CFS":
                chosen[k] = r["fs_div"]
    n_resp = n_hdr = 0
    rows_total = Counter()
    conf = []
    for i, ((corp, year, rep), fs) in enumerate(sorted(chosen.items()), 1):
        d = json.loads((FS_DIR / f"{corp}_{year}_{config.REPORTS[rep]}_{fs}.json").read_text(encoding="utf-8"))["list"]
        bs = sorted([x for x in d if x.get("sj_div") == "BS"], key=lambda x: int(x["ord"]))
        n_resp += 1
        sec, has_c, has_n = sections(bs)
        if has_c and has_n:
            n_hdr += 1
        for j, x in enumerate(bs):
            nm = norm(x["account_nm"])
            if not DEBT.search(nm) or EXCL.search(nm):
                continue
            pos = sec[j] if (has_c and has_n) else "?"
            ns, ids = name_sig(nm), id_sig(x.get("account_id", ""))
            rows_total["차입·사채 행"] += 1
            if pos == "?":
                rows_total["머리행 없음으로 위치 판단 불가"] += 1
                continue
            if pos == "O":
                rows_total["부채 구간 밖(유동/비유동 어느 쪽도 아님)"] += 1
                continue
            rows_total["위치로 단기/장기 판단됨"] += 1
            if ns == "?" and ids == "?":
                rows_total["이름·코드로는 판단 불가, 위치로만 판단"] += 1
            for lab, sg in (("이름", ns), ("표준코드", ids)):
                if sg != "?":
                    rows_total[f"{lab} 신호 있음"] += 1
                    if sg != pos:
                        rows_total[f"{lab}과 위치가 어긋남"] += 1
                        if len(conf) < 3000:
                            conf.append({"corp_code": corp, "year": year, "report": rep, "fs": fs, "계정명": nm,
                                         "account_id": x.get("account_id", ""), "위치": pos, "비교": lab, "비교신호": sg})
        if i % 8000 == 0:
            print(f"  {i:,}개 읽음")
    lines = [f"응답 {n_resp:,}개 중 유동부채·비유동부채 머리행이 모두 있는 응답: {n_hdr:,}개 ({n_hdr/n_resp:.1%})"]
    for k in ["차입·사채 행", "머리행 없음으로 위치 판단 불가", "부채 구간 밖(유동/비유동 어느 쪽도 아님)", "위치로 단기/장기 판단됨",
              "이름·코드로는 판단 불가, 위치로만 판단", "이름 신호 있음", "이름과 위치가 어긋남", "표준코드 신호 있음", "표준코드과 위치가 어긋남"]:
        lines.append(f"{k}: {rows_total[k]:,}")
    for lab in ("이름", "표준코드"):
        a, b = rows_total[f"{lab} 신호 있음"], rows_total[f"{lab}과 위치가 어긋남"] + rows_total[f"{lab}과 위치가 어긋남"] * 0
        if a:
            lines.append(f"  {lab} 신호와 위치가 일치한 비율: {1 - rows_total[f'{lab}과 위치가 어긋남']/a:.2%}")
    text = "\n".join(lines)
    print(text)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "위치분류_검증_요약.txt").write_text(text, encoding="utf-8")
    with open(OUTDIR / "위치분류_검증_어긋남_목록.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["corp_code", "year", "report", "fs", "계정명", "account_id", "위치", "비교", "비교신호"])
        w.writeheader()
        w.writerows(conf)
    print("저장:", OUTDIR)


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───
