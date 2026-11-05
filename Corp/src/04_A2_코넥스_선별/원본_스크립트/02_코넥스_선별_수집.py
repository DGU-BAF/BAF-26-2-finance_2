"""A2 코넥스 선별: 코넥스 제조업 기업과 비교용 코스닥 기업의 사전기간 보고서가 DART에 있는지 조회한다.

하는 일
  1. outputs/02_코넥스_선별/코넥스_선별대상_제조업.csv (01_선별대상_만들기.ipynb가 만든 명단)를 읽는다.
  2. 기업마다 사전기간(2019Q1~2021Q2)에 필요한 보고서 10개를 DART에서 조회한다.
       2019: 1분기·반기·3분기·사업 / 2020: 같음 / 2021: 1분기·반기
     연결 재무제표를 먼저 묻고, 없으면(상태 013) 별도를 묻는다. (01_파일럿/02_재무제표_수집과 같은 규칙)
  3. 응답은 data/raw/DART_파일럿/fs/ 에 저장한다. 이미 있으면 다시 요청하지 않는다(재실행하면 이어서 진행).
  4. 끝나면 판정 지표 M과 규칙 결과를 화면에 출력하고 결과 csv 2개를 저장한다.

ICR 같은 결과값은 계산하지 않는다. "보고서가 있는가"만 본다.

판정 규칙(수집 전에 고정한 것, 01_선별대상_만들기.ipynb 2절과 같다. 50%, 20곳은 임의 기준)
  분모 = 2019 사업보고서가 조회되는 코넥스 기업
  분자 = 그중 2019 1분기·반기·3분기 보고서가 모두 조회되는 기업
  M = 분자 / 분모.  M >= 50% 이면 코넥스 포함, 미만이면 제외. 분모가 20곳 미만이면 규칙을 적용하지 않는다.

실행 (PowerShell, 본인 인증키는 이 창에서만 설정)
  cd ...\\Corp\\src\\04_A2_코넥스_선별
  $env:DART_API_KEY = "본인 인증키"
  python -X utf8 02_코넥스_선별_수집.py --dry-run     # 호출 수만 계산(요청 안 보냄, 키 필요 없음)
  python -X utf8 02_코넥스_선별_수집.py               # 실제 조회
  python -X utf8 02_코넥스_선별_수집.py --summary-only  # 이미 저장된 응답만으로 결과 다시 계산(요청 안 보냄)
"""
import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))   # config.py, dart_api.py를 불러오기 위해

import config  # noqa: E402
from dart_api import CACHEABLE_STATUSES, FatalApiStatus, LimitExceeded, get_json  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

OUTDIR = config.OUT.parent / "02_코넥스_선별"
TARGET = OUTDIR / "코넥스_선별대상_제조업.csv"
LOG = OUTDIR / "코넥스_선별_수집로그.csv"
RESULT = OUTDIR / "코넥스_선별_결과_기업별.csv"
FS_DIR = config.RAW / "fs"

NEED = [(2019, "Q1"), (2019, "H1"), (2019, "Q3"), (2019, "FY"),
        (2020, "Q1"), (2020, "H1"), (2020, "Q3"), (2020, "FY"),
        (2021, "Q1"), (2021, "H1")]
THRESHOLD = 0.5      # 임의 기준
MIN_DENOM = 20       # 임의 기준


def load_target():
    with open(TARGET, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fetch_report(corp, year, rep_code, fs, allow_api):
    """보고서 한 건을 (응답, 출처)로 돌려준다. 출처: cache / api / missing"""
    path = FS_DIR / f"{corp}_{year}_{rep_code}_{fs}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "cache"
    if not allow_api:
        return None, "missing"
    data = get_json("fnlttSinglAcntAll.json",
                    {"corp_code": corp, "bsns_year": str(year), "reprt_code": rep_code, "fs_div": fs})
    if data.get("status") in CACHEABLE_STATUSES:        # 000, 013만 저장
        FS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(config.SLEEP)
    return data, "api"


def collect(firms, allow_api):
    """기업별로 필요한 보고서를 조회(또는 저장본 읽기)하고 로그 행 목록을 돌려준다."""
    log = []
    try:
        for i, firm in enumerate(firms, 1):
            for year, rep in NEED:
                for fs in config.FS_ORDER:                    # 연결(CFS) 먼저, 없으면 별도(OFS)
                    data, src = fetch_report(firm["corp_code"], year, config.REPORTS[rep], fs, allow_api)
                    if data is None:                           # 저장도 없고 요청도 못 하는 경우
                        break
                    status = data.get("status")
                    log.append({"corp_code": firm["corp_code"], "year": year, "report": rep, "fs_div": fs,
                                "status": status, "source": src})
                    if status == "000":
                        break
                    if status != "013":
                        print(f"  {firm['corp_code']} {year} {rep} {fs}: 상태 {status} {data.get('message')}")
                        break
            if allow_api and i % 10 == 0:
                print(f"  {i}/{len(firms)} 기업 완료")
    except LimitExceeded as exc:
        print(str(exc))
    except FatalApiStatus as exc:
        print("중단:", exc)
    return log


def per_firm(firms, log):
    """기업별로 '그 보고서가 조회되었는가'를 정리한다."""
    have = defaultdict(set)
    for r in log:
        if r["status"] == "000":
            have[r["corp_code"]].add((int(r["year"]), r["report"]))
    rows = []
    for f in firms:
        h = have[f["corp_code"]]
        q3 = all((2019, k) in h for k in ("Q1", "H1", "Q3"))
        rows.append({
            "집단": f["집단"], "corp_code": f["corp_code"], "회사명(DART)": f["회사명(DART)"], "출처": f["출처"],
            "동명모호": f["동명모호"],
            "FY2019_있음": (2019, "FY") in h,
            "분기3개_2019_있음": q3,
            "필요보고서_개수(10개중)": len(h & set(NEED)),
            "10개_모두_있음": set(NEED) <= h,
        })
    return rows


def metric(rows, group, drop_ambiguous=False):
    sel = [r for r in rows if r["집단"] == group and not (drop_ambiguous and r["동명모호"] == "Y")]
    denom = [r for r in sel if r["FY2019_있음"]]
    numer = [r for r in denom if r["분기3개_2019_있음"]]
    full = [r for r in sel if r["10개_모두_있음"]]
    return {"기업수": len(sel), "분모": len(denom), "분자": len(numer),
            "M": (len(numer) / len(denom)) if denom else None,
            "10개모두": len(full), "10개모두_비율": (len(full) / len(sel)) if sel else None}


def _show(path):
    """화면에 보여 줄 경로(Corp 안이면 Corp 기준 상대경로)."""
    try:
        return str(path.relative_to(config.BASE))
    except ValueError:
        return str(path)


def fmt(x):
    return "-" if x is None else f"{x:.0%}"


def summarize(firms, log, complete):
    rows = per_firm(firms, log)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    with open(RESULT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(LOG, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["corp_code", "year", "report", "fs_div", "status", "source"])
        w.writeheader()
        w.writerows(log)

    print("\n" + "=" * 60)
    print("A2 코넥스 선별 결과" + ("" if complete else "  (※ 일부 기업은 아직 조회 전이라 미완성)"))
    print("=" * 60)
    for label, g, drop in [("코넥스 (전체)", "코넥스", False), ("코넥스 (동명 모호 제외)", "코넥스", True), ("비교: 코스닥 40곳", "비교_코스닥", False)]:
        m = metric(rows, g, drop)
        print(f"[{label}] 기업 {m['기업수']}곳 | 2019 사업보고서 있음(분모) {m['분모']}곳 | 그중 2019 분기 3개 모두 있음(분자) {m['분자']}곳 "
              f"| M = {fmt(m['M'])} | 사전기간 10개 보고서 모두 있음 {m['10개모두']}곳({fmt(m['10개모두_비율'])})")
    m = metric(rows, "코넥스")
    m2 = metric(rows, "코넥스", True)
    print("\n[사전에 고정한 규칙: M >= 50% 이면 포함, 미만이면 제외, 분모 20곳 미만이면 규칙 적용 안 함(임의 기준)]")
    if not complete:
        print("→ 조회가 끝나지 않아 판정하지 않습니다. 같은 명령을 다시 실행하세요.")
    elif m["분모"] < MIN_DENOM:
        print(f"→ 분모 {m['분모']}곳으로 {MIN_DENOM}곳 미만이라 규칙을 적용하지 않습니다. 사용자가 판단하세요.")
    else:
        verdict = "포함" if m["M"] >= THRESHOLD else "제외"
        verdict2 = "포함" if (m2["M"] is not None and m2["M"] >= THRESHOLD) else "제외"
        print(f"→ 규칙 결과: 코넥스 {verdict}  (M = {fmt(m['M'])})")
        print(f"→ 동명 모호 기업을 빼고 다시 계산하면: 코넥스 {verdict2}  (M = {fmt(m2['M'])})" + ("  같은 결론" if verdict == verdict2 else "  ※ 결론이 다름, 해석 시 주의"))
    print()
    print("저장: " + _show(RESULT) + ", " + _show(LOG))
    print("이 결과는 '보고서가 조회되는가'만 보여줍니다. 코넥스 기업이 보고서를 제출했는지와 API 응답은 다를 수 있습니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="호출 수만 계산하고 요청은 보내지 않는다")
    ap.add_argument("--summary-only", action="store_true", help="저장된 응답만으로 결과를 계산한다(요청 안 보냄)")
    args = ap.parse_args()

    firms = load_target()
    n_calls = len(firms) * len(NEED)
    cached = sum(1 for f in firms for y, rep in NEED for fs in config.FS_ORDER
                 if (FS_DIR / f"{f['corp_code']}_{y}_{config.REPORTS[rep]}_{fs}.json").exists())
    print(f"대상 {len(firms)}곳 × 보고서 {len(NEED)}개 = {n_calls:,}건 (연결이 비면 별도까지 최대 {n_calls*2:,}건)")
    print(f"이미 저장된 응답 파일: {cached}개 (다시 요청하지 않음)")
    if args.dry_run:
        return

    allow_api = not args.summary_only
    if allow_api:
        print("DART에 조회를 시작합니다 (인증키가 환경변수에 있어야 합니다). 중간에 멈춰도 같은 명령으로 이어집니다.")
    log = collect(firms, allow_api)

    # 모든 기업의 필요한 보고서가 '조회 결과를 얻었는지' 확인 (013 포함)
    got = {(r["corp_code"], int(r["year"]), r["report"]) for r in log}
    complete = all((f["corp_code"], y, rep) in got for f in firms for y, rep in NEED)
    summarize(firms, log, complete)


if __name__ == "__main__":
    main()
