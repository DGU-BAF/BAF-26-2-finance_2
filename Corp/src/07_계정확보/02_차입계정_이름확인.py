# 이 파일은 노트북 '02_차입계정_이름확인.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 07-02 · 차입 계정이 없던 249곳의 재무상태표 이름 확인 ───


# ─── 준비 — 불러오기와 경로 ───


"""차입 3계정이 사전기간에 하나도 없던 기업(249곳)의 재무상태표에 '차입·사채'처럼 보이는 이름의 계정이 있는지 이름만 확인한다.

이 스크립트가 하는 일 (금액은 읽지 않는다. 값 칸이 비어 있지 않은지만 본다. ICR·E는 계산하지 않는다)
  A. 249곳의 사전기간 보고서(상태 000)마다 재무상태표(BS)에서 차입 관련 단어가 들어간 계정 이름을 모은다.
  B. 비교용: 전체 1,321곳에서 기업마다 사전기간 보고서 1개(2020 사업보고서, 없으면 사전기간 중 가장 늦은 것)를 골라
     같은 단어가 들어간 계정 이름의 기업 수를 센다. 현재 규칙(단기차입금 등 3계정)에 안 잡히는 이름이 무엇인지 보려는 것이다.
  차입 관련 단어: 차입, 사채, 금융부채, 대출, 리스부채, 금융리스, 단기금융, 어음 (이 단어 목록은 에이전트가 정한 탐색용이며
  공식 분류가 아니다. 이 결과로 곧바로 E의 정의를 정하지 않는다.)

실행: python -X utf8 02_차입계정_이름확인.py  (저장된 파일만 읽음, 키 필요 없음)
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
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


OUTDIR = config.BASE / "outputs" / "05_계정확보"
LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
BYFIRM = OUTDIR / "계정확보_기업별.csv"
FS_DIR = config.RAW / "fs"
REP_ORDER = {"Q1": 0, "H1": 1, "Q3": 2, "FY": 3}
WORDS = re.compile(r"차입|사채|금융부채|대출|리스부채|금융리스|단기금융|어음")
CURRENT_RULE = re.compile(r"^(단기차입금|유동성장기차입금|유동성장기부채|유동성차입금|유동성사채|유동성장기사채)")


def nonempty(v):
    return v is not None and str(v).strip() not in ("", "-")


def is_pre(year, rep):
    return (2019, 0) <= (year, REP_ORDER[rep]) <= (2021, 1)


def bs_names(corp, year, rep, fs):
    p = FS_DIR / f"{corp}_{year}_{config.REPORTS[rep]}_{fs}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    out = set()
    for r in d.get("list", []):
        if r.get("sj_div") != "BS" or not nonempty(r.get("thstrm_amount")):
            continue
        nm = re.sub(r"\s+", "", r.get("account_nm", ""))
        if WORDS.search(nm):
            out.add(nm)
    return out


def main():
    firms = list(csv.DictReader(open(BYFIRM, encoding="utf-8-sig")))
    none249 = {r["corp_code"] for r in firms if r["st_borrow_사전"] == "0" and r["cur_ltd_사전"] == "0" and r["cur_bond_사전"] == "0"}
    chosen = {}
    for r in csv.DictReader(open(LOG, encoding="utf-8-sig")):
        if r["status"] != "000":
            continue
        k = (r["corp_code"], int(r["year"]), r["report"])
        if k not in chosen or r["fs_div"] == "CFS":
            chosen[k] = r["fs_div"]

    # A. 249곳 전체 사전기간 보고서
    names_by_firm = defaultdict(set)
    n_reports = Counter()
    for (corp, year, rep), fs in chosen.items():
        if corp in none249 and is_pre(year, rep):
            n_reports[corp] += 1
            names_by_firm[corp] |= bs_names(corp, year, rep, fs)
    with_any = [c for c in none249 if names_by_firm[c]]
    print(f"A. 차입 3계정이 없는 {len(none249)}곳 중 사전기간 재무상태표에 차입 관련 단어가 든 계정이 있는 기업: {len(with_any)}곳, 하나도 없는 기업: {len(none249) - len(with_any)}곳")
    cnt = Counter(nm for c in none249 for nm in names_by_firm[c])
    print("  이름별 기업 수 (상위 25):")
    for nm, n in cnt.most_common(25):
        print(f"    {nm:30s} {n}곳")

    # B. 전체 비교 (기업당 보고서 1개)
    pick = {}
    for (corp, year, rep), fs in chosen.items():
        if not is_pre(year, rep):
            continue
        key = (year == 2020 and rep == "FY", year, REP_ORDER[rep])
        if corp not in pick or key > pick[corp][0]:
            pick[corp] = (key, year, rep, fs)
    allcnt = Counter()
    uncaught = Counter()
    no_word = 0
    for corp, (_, year, rep, fs) in pick.items():
        names = bs_names(corp, year, rep, fs)
        if not names:
            no_word += 1
        for nm in names:
            allcnt[nm] += 1
            if not CURRENT_RULE.search(nm):
                uncaught[nm] += 1
    print(f"\nB. 전체 {len(pick):,}곳(기업당 보고서 1개): 차입 관련 단어가 든 계정이 하나도 없는 기업 {no_word:,}곳")
    print("  현재 규칙(단기차입금·유동성장기차입금·유동성사채 계열)에 잡히지 않는 이름 (상위 30):")
    for nm, n in uncaught.most_common(30):
        print(f"    {nm:30s} {n}곳")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    with open(OUTDIR / "차입계정_이름빈도_249곳.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["계정이름(공백제거)", "249곳 중 기업수"])
        w.writerows(cnt.most_common())
    with open(OUTDIR / "차입계정_이름빈도_전체_현재규칙밖.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["계정이름(공백제거)", "전체 기업수(기업당 보고서 1개)"])
        w.writerows(uncaught.most_common())
    with open(OUTDIR / "차입계정_이름확인_249곳_기업별.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["corp_code", "사전기간_보고서수", "차입관련_이름_있음", "이름들"])
        for c in sorted(none249):
            w.writerow([c, n_reports[c], bool(names_by_firm[c]), " | ".join(sorted(names_by_firm[c]))])
    print("\n저장:", OUTDIR)


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───


# ─── 알아둘 점 — 같은 빈도끼리의 줄 순서 ───
