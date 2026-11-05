# 이 파일은 노트북 '07_E_검산.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 07-07 · E 검산 (06에서 만든 E가 맞는지) ───


# ─── 준비 — 불러오기와 경로 ───


"""06에서 만든 E를 검산한다. ICR·영업이익은 읽지 않는다.

점검 1) E_A > 1 인 보고서, 자산총계가 없거나 0 이하인 보고서를 목록으로 남긴다.
점검 2) 이중 계산: 유동 구간 차입 합이 같은 응답의 '유동부채' 머리행 금액보다 크면 의심(머리행이 합계 행일 때).
점검 3) 누락: 유동 구간에 있는데 차입·사채 규칙(DEBT)에 안 잡힌 '차입 성격' 이름(유동성장기부채, 당좌차월 등)이 있는지 이름 빈도를 센다.
        특히 사전 고정 5절·config의 규칙에 있는 '유동성장기부채'가 위치 방식 규칙(이름에 차입·사채)에 빠져 있지 않은지 본다.
점검 4) 파일럿의 이름 규칙(config.ACCOUNT_PATTERNS의 단기차입금·유동성장기차입금·유동성사채) 합과 위치 방식 분자의 관계.
        위치 방식 분자가 이름 규칙 합보다 작으면 위치 방식이 무언가 빠뜨린 것.
저장: outputs/06_노출도E/E_검산_요약.txt, E_검산_목록.csv
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


OUTDIR = config.BASE / "outputs" / "06_노출도E"
FS_DIR = config.RAW / "fs"
REP_CODE = config.REPORTS
DEBT = re.compile(r"차입|사채|장기부채|당좌차월")   # 06과 같은 규칙(보정 후)
EXCL = re.compile(r"리스|할인발행차금|상환할증금|대손|이자|미지급|매입|채권|차금")
AMBIG = re.compile(r"금융부채")
AMBIG_EXCL = re.compile(r"파생|리스|손익|매매")
KEY = re.compile(r"유동성|장기|당좌|차월|대출|금융|어음|전환|교환|신주|단기")
NAME_RULES = [re.compile(r"^단기차입금"), re.compile(r"^(유동성장기차입금|유동성장기부채|유동성차입금)"), re.compile(r"^(유동성사채|유동성장기사채)")]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def sections(bs):
    hdr = []
    for i, r in enumerate(bs):
        nm, aid = norm(r["account_nm"]), r.get("account_id", "")
        if nm == "유동부채" or aid == "ifrs-full_CurrentLiabilities":
            hdr.append((i, "C"))
        elif nm == "비유동부채" or aid == "ifrs-full_NoncurrentLiabilities":
            hdr.append((i, "N"))
        elif nm == "부채총계" or aid == "ifrs-full_Liabilities":
            hdr.append((i, "T"))
    sec, cur, hi = {}, "O", 0
    for i in range(len(bs)):
        while hi < len(hdr) and hdr[hi][0] <= i:
            cur = {"C": "C", "N": "N", "T": "O"}[hdr[hi][1]]
            hi += 1
        sec[i] = cur
    return sec, hdr


def main():
    E = list(csv.DictReader(open(OUTDIR / "E_보고서별.csv", encoding="utf-8-sig")))
    lst = []
    miss_names = Counter()
    miss_state = Counter()
    n_dbl = n_chk = 0
    n_name_gt = n_name_cmp = 0
    n_missing_ltd = 0
    for i, r in enumerate(E, 1):
        c, y, rep, fs = r["corp_code"], int(r["year"]), r["report"], r["fs_div"]
        e_a = float(r["E_A"]) if r["E_A"] not in ("", None) else None
        if (e_a is not None and e_a > 1) or r["자산이상"] == "True":
            lst.append({"종류": "E_A>1" if r["자산이상"] != "True" else "자산이상", "corp_code": c, "year": y, "report": rep, "fs": fs,
                        "E_A": r["E_A"], "자산총계": r["자산총계"], "유동차입합": r["유동차입합"], "유동차입행수": r["유동차입행수"]})
        if r["상태"] == "NOHDR":
            continue
        d = json.loads((FS_DIR / f"{c}_{y}_{REP_CODE[rep]}_{fs}.json").read_text(encoding="utf-8"))["list"]
        bs = sorted([x for x in d if x.get("sj_div") == "BS"], key=lambda x: int(x["ord"]))
        sec, hdr = sections(bs)
        # 점검 2
        cur_total = next((num(x["thstrm_amount"]) for x in bs if norm(x["account_nm"]) == "유동부채" or x.get("account_id") == "ifrs-full_CurrentLiabilities"), None)
        num_c = float(r["유동차입합"])
        if cur_total and cur_total > 0 and r["상태"] == "DEBT":
            n_chk += 1
            if num_c > cur_total * 1.001:
                n_dbl += 1
                if len(lst) < 400:
                    lst.append({"종류": "차입합>유동부채", "corp_code": c, "year": y, "report": rep, "fs": fs, "E_A": r["E_A"],
                                "자산총계": r["자산총계"], "유동차입합": r["유동차입합"], "유동차입행수": r["유동차입행수"]})
        # 점검 3: 유동 구간에서 DEBT·AMBIG 규칙에 안 잡힌 '차입 성격 후보' 이름
        found_extra = False
        for j, x in enumerate(bs):
            if sec[j] != "C":
                continue
            nm = norm(x["account_nm"])
            if DEBT.search(nm) and not EXCL.search(nm):
                continue
            if AMBIG.search(nm) and not AMBIG_EXCL.search(nm):
                continue
            if KEY.search(nm) and not EXCL.search(nm):
                miss_names[nm] += 1
                if re.match(r"^(유동성장기부채|유동성장기|장기부채의유동|당좌차월|유동성부채)", nm):
                    found_extra = True
        if found_extra:
            n_missing_ltd += 1
            miss_state[r["상태"]] += 1
        # 점검 4
        name_sum = 0.0
        for j, x in enumerate(bs):
            nm = norm(x["account_nm"])
            if any(p.search(nm) for p in NAME_RULES):
                name_sum += num(x["thstrm_amount"]) or 0.0
        if name_sum > 0 and r["상태"] != "NOHDR":
            n_name_cmp += 1
            if num_c + 1 < name_sum:
                n_name_gt += 1
        if i % 4000 == 0:
            print(f"  {i:,}개 읽음")
    L = []
    L.append(f"점검 1) E_A>1 {sum(1 for x in lst if x['종류']=='E_A>1')}건, 자산이상 {sum(1 for x in lst if x['종류']=='자산이상')}건 (목록 저장)")
    L.append(f"점검 2) 상태 DEBT이고 유동부채 머리행 금액이 있는 {n_chk:,}건 중 유동차입합이 유동부채보다 큰 건: {n_dbl:,}건")
    L.append(f"점검 3) 위치 방식 규칙(차입·사채·금융부채)에 안 잡힌 유동 구간의 '차입 성격 후보' 이름(상위 30):")
    for nm, n in miss_names.most_common(30):
        L.append(f"     {nm:34s} {n:,}")
    L.append(f"   그중 '유동성장기부채'·'당좌차월' 등 차입으로 봐야 할 이름이 있는 보고서 {n_missing_ltd:,}건, 그 보고서의 현재 상태: {dict(miss_state)}")
    L.append(f"점검 4) 파일럿 이름 규칙 합이 0보다 큰 {n_name_cmp:,}건 중 위치 방식 분자가 이름 규칙 합보다 작은 건: {n_name_gt:,}건")
    text = "\n".join(L)
    print(text)
    (OUTDIR / "E_검산_요약.txt").write_text(text, encoding="utf-8")
    with open(OUTDIR / "E_검산_목록.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["종류", "corp_code", "year", "report", "fs", "E_A", "자산총계", "유동차입합", "유동차입행수"])
        w.writeheader()
        w.writerows(lst)


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───
