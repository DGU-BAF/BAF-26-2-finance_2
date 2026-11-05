"""제조업 전체 선별 조회: 후보 기업마다 사전기간 핵심 보고서가 DART에 있는지 확인한다.

이 스크립트는 "누구를 분석 표본에 넣을지"를 정하기 위한 **존재 여부 조회**만 한다.
ICR 같은 결과값은 계산하지 않고, 보고서 안의 숫자도 읽지 않는다. (결과를 보고 표본을 고르는 일을 막기 위함)

하는 일
  1. outputs/01_파일럿/기업개황_상장사전체.csv에서 제조업(업종코드 앞 2자리 10~34) 기업을 모두 대상으로 삼는다.
     법인구분(Y·K·N·E)이나 결산월로 거르지 않는다. 코넥스는 2026-11-04에 분석 대상에서 제외하기로 확정(A2)했지만,
     코넥스 117곳은 이미 조회해 저장해 둔 응답을 그대로 재사용하므로 조회 대상에서는 빼지 않는다(추가 호출이 거의 없음).
     분석 대상에서 빼는 일은 결과 정리 단계에서 한다. 비12월 결산 처리(A2의 나머지)는 아직 결정 전이라 조회는 전부 해 둔다. (이름 표시가 스팩·지주인 기업도 지우지 않고 표시만 한다)
  2. 조회 순서는 **시드를 고정해 무작위로 섞은 순서**다(config.SEED). 중간에 멈춰도 지금까지 조회된 기업이
     알파벳·번호 순서가 아니라 무작위 부분집합이 되도록 하기 위해서다.
  3. 기업마다 아래 CHECK의 보고서가 있는지 조회한다. (제안 선별 규칙: 2019 사업보고서 + 2021 반기보고서)
       연결 재무제표를 먼저 묻고, 없으면(상태 013) 별도를 묻는다. (01_파일럿/02_재무제표_수집과 같은 규칙)
  4. 응답은 data/raw/DART_파일럿/fs/ 에 저장한다. 이미 있으면 다시 요청하지 않는다. 본 수집 때 그대로 재사용된다.
  5. 끝나면(또는 중간에 멈추면) 지금까지의 결과를 법인구분별로 요약해 출력하고 csv 3개를 저장한다.

이 스크립트가 정하지 않는 것
  - 선별 규칙(A8 등)은 확정되지 않았다. 여기서는 "제안 규칙을 통과하는지"를 표시만 한다.
  - 비12월 결산을 쓸지(A2의 나머지), 업종 범위(A1), 표본 크기와 멈춤 규칙은 정하지 않는다.

호출 수와 시간(추정)
  기업 약 2,250곳 × 보고서 2개 × (연결이 비어 별도로 다시 묻는 경우 포함 평균 약 1.5) ≈ 6,750건.
  호출 사이 0.4초 대기 + 서버 응답 시간이라 대략 1.5~2시간. 일일 요청 한도는 가이드에 기간 단위가 없어서 모른다.
  한도(상태 020)에 걸리면 그 자리에서 멈추고, 내일 같은 명령을 다시 실행하면 이어서 한다.

실행 (PowerShell, 본인 인증키는 이 창에서만 설정. 키를 파일·채팅에 적지 않는다)
  cd "C:\\Users\\SAMSUNG\\OneDrive\\바탕 화면\\공모전_26-2 BAF\\BAF-26-2-finance_2\\BAF-26-2-finance_2\\Corp\\src\\05_제조업_선별"
  $env:DART_API_KEY = "본인 인증키"
  python -X utf8 01_제조업_선별_수집.py --dry-run          # 호출 수만 계산(요청 안 보냄, 키 필요 없음)
  python -X utf8 01_제조업_선별_수집.py --limit 30          # 앞의 30곳만 시험 조회(키 필요)
  python -X utf8 01_제조업_선별_수집.py                     # 전체 조회
  python -X utf8 01_제조업_선별_수집.py --summary-only      # 저장된 응답만으로 결과를 다시 계산(요청 안 보냄)
  Ctrl+C로 멈추면 그때까지의 결과를 저장하고 요약한다.
"""
import argparse
import csv
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_파일럿"))   # config.py, dart_api.py를 불러오기 위해

import config  # noqa: E402
from dart_api import CACHEABLE_STATUSES, FatalApiStatus, LimitExceeded, get_json  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

COMPANY = config.OUT / "기업개황_상장사전체.csv"
OUTDIR = config.OUT.parent / "03_제조업_선별"
TARGET = OUTDIR / "제조업_선별대상.csv"
LOG = OUTDIR / "제조업_선별_수집로그.csv"
RESULT = OUTDIR / "제조업_선별_결과_기업별.csv"
FS_DIR = config.RAW / "fs"

# 선별에 쓰는 보고서 (제안 규칙: 2019 사업보고서 + 2021 반기보고서). 규칙이 바뀌면 여기만 고친다.
CHECK = [(2019, "FY"), (2021, "H1")]
LABEL = {(2019, "FY"): "2019_사업보고서", (2021, "H1"): "2021_반기보고서"}


def build_targets():
    """제조업 기업 목록을 만들고, 시드 고정 무작위 순서를 매긴다."""
    with open(COMPANY, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    manu = [r for r in rows if r["induty_code"][:2] in config.MANUFACTURING_PREFIXES]
    manu.sort(key=lambda r: r["corp_code"])                 # 같은 시드면 같은 순서가 되도록 먼저 정렬
    random.Random(config.SEED).shuffle(manu)
    for i, r in enumerate(manu, 1):
        r["조회순서"] = i
        r["이름표시"] = ",".join(k for k, pat in config.FLAG_NAME_PATTERNS.items() if re.search(pat, r["corp_name"]))
    return manu


def save_targets(firms):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cols = ["조회순서", "corp_code", "corp_name", "stock_code", "corp_cls", "induty_code", "acc_mt", "이름표시"]
    with open(TARGET, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(firms)


def fetch_report(corp, year, rep_code, fs, allow_api):
    """보고서 한 건을 (응답, 출처)로 돌려준다. 출처: cache / api / missing"""
    path = FS_DIR / f"{corp}_{year}_{rep_code}_{fs}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "cache"
    if not allow_api:
        return None, "missing"
    data = get_json("fnlttSinglAcntAll.json",
                    {"corp_code": corp, "bsns_year": str(year), "reprt_code": rep_code, "fs_div": fs})
    if data.get("status") in CACHEABLE_STATUSES:        # 000, 013만 저장 (오류 응답은 저장하지 않는다)
        FS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(config.SLEEP)
    return data, "api"


def collect(firms, allow_api):
    """기업별로 CHECK의 보고서를 조회(또는 저장본 읽기)하고 로그 행 목록을 돌려준다."""
    log = []
    started = time.time()
    n_api = 0
    try:
        for i, firm in enumerate(firms, 1):
            for year, rep in CHECK:
                for fs in config.FS_ORDER:                    # 연결(CFS) 먼저, 없으면 별도(OFS)
                    data, src = fetch_report(firm["corp_code"], year, config.REPORTS[rep], fs, allow_api)
                    if data is None:                           # 저장도 없고 요청도 못 하는 경우
                        break
                    n_api += src == "api"
                    status = data.get("status")
                    log.append({"corp_code": firm["corp_code"], "year": year, "report": rep, "fs_div": fs,
                                "status": status, "source": src})
                    if status == "000":
                        break                                  # 연결에 자료가 있으면 별도는 묻지 않음
                    if status != "013":
                        print(f"  {firm['corp_code']} {year} {rep} {fs}: 상태 {status} {data.get('message')}")
                        break
            if allow_api and i % 50 == 0:
                spent = time.time() - started
                left = (len(firms) - i) * spent / i
                print(f"  {i}/{len(firms)} 기업 처리 (요청 {n_api}건, 경과 {spent/60:.0f}분, 남은 시간 약 {left/60:.0f}분)")
    except LimitExceeded as exc:
        print(str(exc))
    except FatalApiStatus as exc:
        print("중단:", exc)
    except KeyboardInterrupt:
        print("\nCtrl+C로 멈췄습니다. 지금까지의 결과를 저장합니다. 같은 명령을 다시 실행하면 이어서 합니다.")
    return log


def per_firm(firms, log):
    """기업별로 '그 보고서가 조회되었는가'를 정리한다. 조회완료 = CHECK의 보고서 모두에 대해 응답을 얻은 기업."""
    got = {}       # (corp, year, report) -> 응답을 얻은 마지막 상태
    used = {}      # (corp, year, report) -> 자료가 있었던 재무제표 구분(CFS/OFS)
    for r in log:
        got[(r["corp_code"], int(r["year"]), r["report"])] = r["status"]
        if r["status"] == "000":
            used[(r["corp_code"], int(r["year"]), r["report"])] = r["fs_div"]
    rows = []
    for f in firms:
        key = lambda k: (f["corp_code"], k[0], k[1])
        done = all(key(k) in got for k in CHECK)
        row = {"조회순서": f["조회순서"], "corp_code": f["corp_code"], "회사명": f["corp_name"], "현재_법인구분": f["corp_cls"],
               "업종코드": f["induty_code"], "결산월": f["acc_mt"], "이름표시": f["이름표시"], "조회완료": done}
        for k in CHECK:
            row[LABEL[k] + "_있음"] = (key(k) in used) if done else ""
            row[LABEL[k] + "_구분"] = used.get(key(k), "")
        row["제안규칙_통과(2019사업+2021반기)"] = (all(key(k) in used for k in CHECK)) if done else ""
        rows.append(row)
    return rows


def pct(a, b):
    return "-" if not b else f"{a/b:.0%}"


def summarize(firms, log):
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

    done = [r for r in rows if r["조회완료"]]
    pkey = "제안규칙_통과(2019사업+2021반기)"
    print("\n" + "=" * 66)
    print("제조업 선별 조회 결과 (제안 규칙: 2019 사업보고서 + 2021 반기보고서가 모두 조회됨)")
    print("=" * 66)
    print(f"대상 {len(rows):,}곳 중 조회 완료 {len(done):,}곳, 아직 조회 전 {len(rows)-len(done):,}곳")
    if len(done) < len(rows):
        print("※ 조회 전인 기업이 있어 아래 숫자는 부분 결과입니다(조회 순서가 무작위라 부분집합도 무작위 표본입니다).")
    print()
    print(f"{'법인구분(현재)':<14}{'조회완료':>8}{'2019 사업':>10}{'2021 반기':>10}{'둘 다(통과)':>12}{'통과율':>8}")
    for cls in ["Y", "K", "N", "E"]:
        g = [r for r in done if r["현재_법인구분"] == cls]
        a = sum(1 for r in g if r[LABEL[(2019, "FY")] + "_있음"] is True)
        b = sum(1 for r in g if r[LABEL[(2021, "H1")] + "_있음"] is True)
        c = sum(1 for r in g if r[pkey] is True)
        print(f"{cls:<14}{len(g):>8}{a:>10}{b:>10}{c:>12}{pct(c, len(g)):>8}")
    a = sum(1 for r in done if r[LABEL[(2019, "FY")] + "_있음"] is True)
    b = sum(1 for r in done if r[LABEL[(2021, "H1")] + "_있음"] is True)
    c = sum(1 for r in done if r[pkey] is True)
    print(f"{'전체':<14}{len(done):>8}{a:>10}{b:>10}{c:>12}{pct(c, len(done)):>8}")
    nd = [r for r in done if r["결산월"] != "12"]
    print(f"\n비12월 결산(조회 완료 중): {len(nd)}곳, 그중 통과 {sum(1 for r in nd if r[pkey] is True)}곳")
    print("연결/별도(통과 기업의 2019 사업보고서):", dict(Counter(r[LABEL[(2019, 'FY')] + '_구분'] for r in done if r[pkey] is True)))
    print("\n저장:", _show(TARGET), "|", _show(RESULT), "|", _show(LOG))
    print("이 결과는 'DART API가 보고서를 응답으로 주는가'만 보여줍니다. 선별 규칙의 확정과 표본 결정은 아직 아닙니다.")


def _show(path):
    """화면에 보여 줄 경로(Corp 안이면 Corp 기준 상대경로)."""
    try:
        return str(path.relative_to(config.BASE))
    except ValueError:
        return str(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="호출 수만 계산하고 요청은 보내지 않는다")
    ap.add_argument("--summary-only", action="store_true", help="저장된 응답만으로 결과를 계산한다(요청 안 보냄)")
    ap.add_argument("--limit", type=int, default=None, help="조회 순서의 앞에서 N곳만 처리한다(시험용)")
    args = ap.parse_args()

    firms = build_targets()
    save_targets(firms)
    todo = firms[: args.limit] if args.limit else firms

    cached = sum(1 for f in todo for y, rep in CHECK for fs in config.FS_ORDER
                 if (FS_DIR / f"{f['corp_code']}_{y}_{config.REPORTS[rep]}_{fs}.json").exists())
    n_calls = len(todo) * len(CHECK)
    print(f"제조업 대상 {len(firms):,}곳 중 이번에 처리할 곳 {len(todo):,}곳 × 보고서 {len(CHECK)}개 = {n_calls:,}건")
    print(f"(연결이 비어 별도로 다시 묻는 경우까지 최대 {n_calls*2:,}건, 이미 저장된 응답 {cached:,}개는 다시 요청하지 않음)")
    print(f"조회 순서는 시드 {config.SEED}로 고정한 무작위 순서입니다. 목록: {_show(TARGET)}")
    if args.dry_run:
        return

    allow_api = not args.summary_only
    if allow_api:
        print("DART에 조회를 시작합니다 (인증키가 환경변수에 있어야 합니다). 중간에 멈춰도 같은 명령으로 이어집니다.")
    log = collect(todo, allow_api)
    summarize(todo, log)


if __name__ == "__main__":
    main()
