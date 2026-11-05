"""fnlttXbrl(재무제표 원본파일 XBRL) 시험: 주석(이자비용 등)이 2018~2020년 파일에도 들어 있는지 요청 5건으로 확인한다.

왜 하나
  주요 재무제표 응답(fnlttSinglAcntAll)에는 주석이 없고, 웹의 주석 도구는 2022년(조회)·2023년(일괄)부터만 제공된다.
  남은 후보가 접수번호별 XBRL 압축파일(fnlttXbrl)이다. 가이드(2019019)는 주석 포함 여부와 제공 연도를 말하지 않으므로 직접 받아 본다.

시험 대상 (규칙으로 고정, 결과를 보고 고르지 않는다)
  outputs/05_계정확보/이자분모_후보_비교_연간.csv(2019·2020 사업보고서의 세 분모 후보)에서
   A. 이자비용 값과 금융비용 값이 둘 다 있는 기업 중 corp_code가 가장 작은 기업의 2020 사업보고서  (기준용)
   B. 이자비용 줄이 없고 금융비용 값이 있는 기업 중 corp_code가 가장 작은 기업의
        2018·2019·2020 사업보고서, 2020 반기보고서                                                (핵심: 주석에서 이자비용이 나오나? 옛 연도도 되나? 분기도 되나?)
  합계 요청 5건. 접수번호(rcept_no)는 이미 저장된 응답에서 읽는다. 키는 환경변수에서만 읽는다.

하는 일
  - 압축파일을 data/raw/DART_파일럿/xbrl_test/에 저장하고, 압축을 풀지 않고 메모리에서 읽는다(외부 파일을 실행하지 않음).
  - 파일 목록, 요소 이름 중 'Interest'·'FinanceCost'를 포함한 것과 횟수, 'DisclosureOf'(주석 설명 블록) 개수를 센다.
  - 결과를 화면과 outputs/05_계정확보/xbrl_시험_결과.txt에 쓴다.

실행 (PowerShell, 인증키는 이 창의 환경변수로 이미 설정되어 있어야 함)
  python -X utf8 04_XBRL_시험.py --dry-run   # 어떤 기업·접수번호를 쓸지만 출력(요청 안 보냄, 키 필요 없음)
  python -X utf8 04_XBRL_시험.py             # 실제 요청 5건
"""
import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))
import config  # noqa: E402
from dart_api import ApiError, FatalApiStatus, LimitExceeded, get_bytes  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

CMP = config.BASE / "outputs" / "05_계정확보" / "이자분모_후보_비교_연간.csv"
LOG = config.BASE / "outputs" / "04_본수집" / "본수집_로그.csv"
OUTDIR = config.BASE / "outputs" / "05_계정확보"
XDIR = config.RAW / "xbrl_test"
FS_DIR = config.RAW / "fs"
MAX_MEMBER = 80_000_000


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pick_firms():
    rows = list(csv.DictReader(open(CMP, encoding="utf-8-sig")))
    rows.sort(key=lambda r: (r["corp_code"], r["year"]))
    a = next(r for r in rows if r["year"] == "2020" and num(r["이자비용"]) is not None and num(r["금융비용"]) is not None)
    b = next(r for r in rows if r["year"] == "2020" and r["이자비용"] == "" and num(r["금융비용"]) is not None)
    return a, b


def rcept(corp, year, rep_code):
    """저장된 응답에서 접수번호를 읽는다. (연결 우선)"""
    for fs in ("CFS", "OFS"):
        p = FS_DIR / f"{corp}_{year}_{rep_code}_{fs}.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("status") == "000" and d.get("list"):
                return d["list"][0]["rcept_no"], fs
    return None, None


def targets():
    a, b = pick_firms()
    t = [("A", a["corp_code"], a["회사명"], 2020, "11011"),
         ("B", b["corp_code"], b["회사명"], 2018, "11011"),
         ("B", b["corp_code"], b["회사명"], 2019, "11011"),
         ("B", b["corp_code"], b["회사명"], 2020, "11011"),
         ("B", b["corp_code"], b["회사명"], 2020, "11012")]
    out = []
    for g, corp, name, year, code in t:
        rn, fs = rcept(corp, year, code)
        out.append({"그룹": g, "corp_code": corp, "회사명": name, "year": year, "reprt_code": code, "rcept_no": rn, "fs": fs})
    return out


def local(tag):
    return tag.rsplit("}", 1)[-1]


def inspect_zip(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = [(i.filename, i.file_size) for i in z.infolist()]
    info = {"files": names, "tags": Counter(), "n_elem": 0, "n_names": 0, "disclosure_blocks": 0, "interest_facts": []}
    inst = [n for n, s in names if n.lower().endswith(".xbrl")]
    if not inst:
        info["note"] = "확장자 .xbrl 파일 없음"
        return info
    name = inst[0]
    if dict(names)[name] > MAX_MEMBER:
        info["note"] = "인스턴스 파일이 너무 커서 건너뜀"
        return info
    with z.open(name) as fh:
        for ev, el in ET.iterparse(fh, events=("end",)):
            ln = local(el.tag)
            info["n_elem"] += 1
            info["tags"][ln] += 1
            if re.search(r"Interest|FinanceCost", ln, re.I) and (el.text or "").strip() and len(info["interest_facts"]) < 60:
                info["interest_facts"].append((ln, el.get("contextRef", ""), (el.text or "").strip()[:30]))
            el.clear()
    info["n_names"] = len(info["tags"])
    info["disclosure_blocks"] = sum(c for t, c in info["tags"].items() if t.startswith("DisclosureOf"))
    return info


def report(t, info, lines):
    lines.append(f"\n[{t['그룹']}] {t['회사명']}({t['corp_code']}) {t['year']} {t['reprt_code']} rcept_no={t['rcept_no']}")
    lines.append("  압축파일 구성: " + "; ".join(f"{n}({s:,}B)" for n, s in info["files"][:12]) + (" ..." if len(info["files"]) > 12 else ""))
    if "note" in info:
        lines.append("  " + info["note"])
        return
    lines.append(f"  요소 {info['n_elem']:,}개 / 서로 다른 요소 이름 {info['n_names']:,}개 / 'DisclosureOf…'(주석 설명 블록) {info['disclosure_blocks']}개")
    names = sorted((n, c) for n, c in info["tags"].items() if re.search(r"Interest|FinanceCost", n, re.I))
    lines.append("  Interest/FinanceCost 계열 요소: " + (", ".join(f"{n}×{c}" for n, c in names) if names else "없음"))
    for ln, ctx, val in info["interest_facts"][:12]:
        lines.append(f"    값 예) {ln} [{ctx}] = {val}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ts = targets()
    print("시험 대상 5건:")
    for t in ts:
        print(f"  [{t['그룹']}] {t['회사명']}({t['corp_code']}) {t['year']} 보고서코드 {t['reprt_code']} 접수번호 {t['rcept_no']} ({t['fs']})")
    if any(t["rcept_no"] is None for t in ts):
        print("※ 접수번호를 찾지 못한 건이 있습니다. 해당 보고서가 저장 응답에 없는 경우입니다(그 건은 요청하지 않음).")
    if args.dry_run:
        return
    XDIR.mkdir(parents=True, exist_ok=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    lines = ["fnlttXbrl 시험 결과 (주석에서 이자비용이 나오는지)"]
    for t in ts:
        if t["rcept_no"] is None:
            lines.append(f"\n[{t['그룹']}] {t['회사명']} {t['year']} {t['reprt_code']}: 접수번호 없음, 요청 안 함")
            continue
        try:
            raw = get_bytes("fnlttXbrl.xml", {"rcept_no": t["rcept_no"], "reprt_code": t["reprt_code"]})
        except (ApiError, LimitExceeded) as exc:
            lines.append(f"\n[{t['그룹']}] {t['회사명']} {t['year']} {t['reprt_code']} rcept_no={t['rcept_no']}: 파일을 받지 못함 → {exc}")
            continue
        except FatalApiStatus as exc:
            lines.append(f"\n중단: {exc}")
            break
        (XDIR / f"{t['corp_code']}_{t['year']}_{t['reprt_code']}.zip").write_bytes(raw)
        try:
            report(t, inspect_zip(raw), lines)
        except (zipfile.BadZipFile, ET.ParseError) as exc:
            lines.append(f"\n[{t['그룹']}] {t['회사명']} {t['year']} {t['reprt_code']}: 압축/XML 읽기 실패 → {exc}")
    text = "\n".join(lines)
    print(text)
    (OUTDIR / "xbrl_시험_결과.txt").write_text(text, encoding="utf-8")
    print("\n저장:", OUTDIR / "xbrl_시험_결과.txt")
    print("이 결과를 채팅에 붙여 주세요. (키는 이 출력에 들어 있지 않습니다)")


if __name__ == "__main__":
    main()
