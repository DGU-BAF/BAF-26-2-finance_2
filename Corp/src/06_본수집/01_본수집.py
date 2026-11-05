# 이 파일은 노트북 '01_본수집.ipynb'에서 자동 생성되었습니다. 직접 수정하지 마세요.
# 수정은 노트북에서 하고, 변환은 Corp/scripts/노트북에서_py_만들기.py로 합니다.

# ─── 06 · 본수집 (선별 통과 기업의 2018~2024Q3 재무제표 원본 저장) ───


# ─── 준비 — 불러오기와 경로 ───


"""본 수집: 선별을 통과한 기업의 2018~2024Q3 분기 재무제표 원본을 DART에서 받아 저장한다.

이 스크립트는 **원본 응답을 저장**하고 "보고서가 있었는가"만 기록한다.
ICR·노출도 같은 결과값은 계산하지 않고 보고서 안의 숫자도 읽지 않는다. (결과를 보고 표본을 고르는 일을 막기 위함)
계정 매핑·분기 환원·연결/별도 규칙은 수집이 끝난 뒤 정제 단계에서 한다. (응답 전체를 저장하므로 나중에 바꿀 수 있다)

수집 대상 (2026-11-05 사용자 결정: 시드 유지, 전수 목표 + 마감 시각, 범위 2018~2024Q3)
  - 선별 결과(03_제조업_선별)에서 '2019 사업보고서 + 2021 반기보고서가 둘 다 조회된' 기업
  - 그중 A2 확정에 따라 12월 결산만, 현재 법인구분 N(코넥스) 제외, 코넥스 선별 대상 중 '코넥스' 집단(117곳) 제외
    (A2 적용 후 1,321곳이어야 한다. 아래 실행 때 숫자가 다르면 화면에 경고한다)
  - 지주회사 표시 기업(21곳)은 수동 검토 전이므로 지우지 않고 받는다.
  - 순서: 선별 때의 시드(config.SEED) 무작위 순서를 그대로 쓴다. 기업 하나를 끝까지(27개 보고서) 받고 다음 기업으로 간다.
    그래서 어디서 멈춰도 '완료된 기업'은 무작위 부분표본이다.

수집 보고서: 2018~2023년 각 4개(1분기 11013, 반기 11012, 3분기 11014, 사업 11011) + 2024년 3개(사업보고서 제외) = 27개.
  규칙(사전 고정 문서 3절): 연결(CFS)을 먼저 묻고 없으면(013) 별도(OFS). 보고서마다 이 규칙을 그대로 적용한다.
  선별 때 이미 받은 응답과 파일럿 응답은 다시 요청하지 않는다(data/raw/DART_파일럿/fs/).

멈춤 규칙: 전수(1,321곳)가 목표이고, --until로 준 마감 시각이 되면 그 기업을 끝낸 뒤 멈춘다.
  요청 제한(020)에 걸려도 멈춘다. 결과를 보고 멈추지 않는다.
  같은 명령을 다시 실행하면 저장된 응답은 건너뛰고 이어서 한다.

실행 (PowerShell, 본인 인증키는 이 창에서만 설정. 키를 파일·채팅에 적지 않는다)
  cd "C:\\Users\\SAMSUNG\\OneDrive\\바탕 화면\\공모전_26-2 BAF\\BAF-26-2-finance_2\\BAF-26-2-finance_2\\Corp\\src\\06_본수집"
  $env:DART_API_KEY = "본인 인증키"
  python -X utf8 01_본수집.py --dry-run                      # 요청 수만 계산(요청 안 보냄, 키 필요 없음)
  python -X utf8 01_본수집.py --limit 5                      # 앞의 5곳만 시험 수집(키 필요)
  python -X utf8 01_본수집.py --until 2026-11-08T23:00       # 마감 시각까지 수집
  python -X utf8 01_본수집.py --summary-only                 # 저장된 응답만으로 결과표를 다시 계산(요청 안 보냄)
  Ctrl+C로 멈추면 그때까지의 결과를 저장하고 요약한다.
"""
import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
try:
    HERE = HERE      # .py로 실행할 때
except NameError:
    HERE = Path.cwd()                           # 노트북에서 실행할 때(노트북이 있는 폴더)
sys.path.insert(0, str(HERE.parent / "01_파일럿"))   # config.py, dart_api.py를 불러오기 위해
import config  # noqa: E402
from dart_api import ApiError, CACHEABLE_STATUSES, FatalApiStatus, LimitExceeded, get_json  # noqa: E402


# ─── 상수 — 입력·출력 경로와 규칙 값 ───


NET_WAIT_SEC = 30        # 네트워크 오류 시 다음 재시도까지 기다리는 시간
NET_MAX_WAITS = 60       # 연속 60번(약 30분) 실패하면 포기하고 결과를 저장한 뒤 멈춘다


class NetworkGaveUp(RuntimeError):
    """네트워크가 오래 돌아오지 않아 멈춤."""


if hasattr(sys.stdout, "reconfigure"):          # 노트북의 출력 창에는 이 함수가 없다
    sys.stdout.reconfigure(encoding="utf-8")
SELECT_RESULT = config.OUT.parent / "03_제조업_선별" / "제조업_선별_결과_기업별.csv"
KONEX_LIST = config.OUT.parent / "02_코넥스_선별" / "코넥스_선별대상_제조업.csv"
OUTDIR = config.OUT.parent / "04_본수집"
TARGET = OUTDIR / "본수집_대상.csv"
LOG = OUTDIR / "본수집_로그.csv"
RESULT = OUTDIR / "본수집_결과_기업별.csv"
FS_DIR = config.RAW / "fs"
PASS_COL = "제안규칙_통과(2019사업+2021반기)"      # 선별 결과 파일의 열 이름(옛 표현이지만 계산은 확정 규칙과 같다)
EXPECTED_N = 1321                                  # 2026-11-05 확인한 A2 적용 후 기업 수
REPORT_LIST = [(y, rep) for y in config.YEARS for rep in ("Q1", "H1", "Q3", "FY") if not (y == 2024 and rep == "FY")]
REP_ORDER = {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def build_targets():
    """선별 통과 + A2 적용 기업 목록을 선별 때의 무작위 순서로 돌려준다."""
    konex = {r["corp_code"] for r in read_csv(KONEX_LIST) if r["집단"] == "코넥스"}
    firms = []
    for r in read_csv(SELECT_RESULT):
        if r["조회완료"] != "True" or r[PASS_COL] != "True":
            continue
        if r["결산월"] != "12" or r["현재_법인구분"] == "N" or r["corp_code"] in konex:
            continue
        firms.append(r)
    firms.sort(key=lambda r: int(r["조회순서"]))
    return firms


def save_targets(firms):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cols = ["조회순서", "corp_code", "회사명", "현재_법인구분", "업종코드", "결산월", "이름표시",
            "2019_사업보고서_구분", "2021_반기보고서_구분"]
    with open(TARGET, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(firms)


def path_of(corp, year, rep, fs):
    return FS_DIR / f"{corp}_{year}_{config.REPORTS[rep]}_{fs}.json"


def cached_status(corp, year, rep, fs):
    """저장된 응답의 상태코드. 없으면 None."""
    p = path_of(corp, year, rep, fs)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("status")


def fetch_report(corp, year, rep, fs, allow_api):
    """보고서 한 건을 (응답, 출처)로 돌려준다. 출처: cache / api / missing"""
    p = path_of(corp, year, rep, fs)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")), "cache"
    if not allow_api:
        return None, "missing"
    data = get_json("fnlttSinglAcntAll.json",
                    {"corp_code": corp, "bsns_year": str(year), "reprt_code": config.REPORTS[rep], "fs_div": fs})
    if data.get("status") in CACHEABLE_STATUSES:        # 000, 013만 저장 (오류 응답은 저장하지 않는다)
        FS_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(config.SLEEP)
    return data, "api"


def fetch_with_wait(corp, year, rep, fs, allow_api):
    """네트워크 오류(와이파이 끊김 등)면 30초씩 기다리며 다시 시도한다. 약 30분 넘게 안 돌아오면 포기."""
    for n in range(NET_MAX_WAITS + 1):
        try:
            return fetch_report(corp, year, rep, fs, allow_api)
        except ApiError as exc:
            if n == NET_MAX_WAITS:
                raise NetworkGaveUp(str(exc))
            if n == 0:
                print(f"  [{datetime.now():%H:%M:%S}] 네트워크 오류: {exc} — {NET_WAIT_SEC}초 간격으로 재시도합니다(최대 {NET_MAX_WAITS * NET_WAIT_SEC // 60}분).")
            time.sleep(NET_WAIT_SEC)


def plan(firms):
    """아직 저장되지 않은 요청 수의 범위와 예상치를 계산한다(요청은 보내지 않는다)."""
    lo = hi = exp = 0
    for f in firms:
        both_ofs = f["2019_사업보고서_구분"] == "OFS" and f["2021_반기보고서_구분"] == "OFS"
        mixed = f["2019_사업보고서_구분"] != f["2021_반기보고서_구분"]
        per_req = 2.0 if both_ofs else (1.5 if mixed else 1.0)     # 연결을 먼저 물으므로 별도 기업은 2건이 필요
        for year, rep in REPORT_LIST:
            s_cfs = cached_status(f["corp_code"], year, rep, "CFS")
            if s_cfs == "000":
                continue
            if s_cfs == "013":                                      # 연결 없음 확인됨 → 별도만 남음
                if cached_status(f["corp_code"], year, rep, "OFS") is None:
                    lo += 1; hi += 1; exp += 1
                continue
            lo += 1; hi += 2; exp += per_req
    return lo, hi, exp


def collect(firms, allow_api, deadline):
    """기업별로 27개 보고서를 받아(또는 저장본을 읽어) 로그 행 목록과 멈춤 사유를 돌려준다."""
    log = []
    started = time.time()
    n_api = 0
    reason = "전수 처리 완료"
    try:
        for i, firm in enumerate(firms, 1):
            if allow_api and deadline and datetime.now() >= deadline:
                reason = f"마감 시각({deadline:%Y-%m-%d %H:%M}) 도달"
                break
            corp = firm["corp_code"]
            for year, rep in REPORT_LIST:
                for fs in config.FS_ORDER:                    # 연결(CFS) 먼저, 없으면 별도(OFS)
                    data, src = fetch_with_wait(corp, year, rep, fs, allow_api)
                    if data is None:
                        break
                    n_api += src == "api"
                    status = data.get("status")
                    log.append({"corp_code": corp, "year": year, "report": rep, "fs_div": fs,
                                "status": status, "source": src})
                    if status == "000":
                        break
                    if status != "013":
                        print(f"  {corp} {year} {rep} {fs}: 상태 {status} {data.get('message')}")
                        break
            if allow_api and i % 25 == 0:
                spent = time.time() - started
                print(f"  {i}/{len(firms)} 기업 처리 (요청 {n_api:,}건, 경과 {spent/60:.0f}분)")
    except LimitExceeded as exc:
        reason = "요청 제한(020)으로 중단"
        print(str(exc))
    except FatalApiStatus as exc:
        reason = "키·권한·서버 문제로 중단"
        print("중단:", exc)
    except NetworkGaveUp as exc:
        reason = "네트워크가 30분 넘게 복구되지 않아 중단"
        print("중단:", exc)
    except KeyboardInterrupt:
        reason = "Ctrl+C로 중단"
        print("\nCtrl+C로 멈췄습니다. 지금까지의 결과를 저장합니다. 같은 명령을 다시 실행하면 이어서 합니다.")
    return log, reason, n_api


def per_firm(firms, log):
    """기업별 정리: 완료 = 27개 보고서 모두에 대해 응답(자료 있음 또는 연결·별도 모두 없음)을 얻은 기업."""
    final = {}                                   # (corp, year, rep) -> (상태, 구분)
    for r in log:
        k = (r["corp_code"], int(r["year"]), r["report"])
        if r["status"] == "000" or k not in final:
            final[k] = (r["status"], r["fs_div"])
        elif final[k][0] != "000":
            final[k] = (r["status"], r["fs_div"])
    rows = []
    for f in firms:
        c = f["corp_code"]
        got = {k: v for k, v in final.items() if k[0] == c}
        done = all((c, y, rep) in got and (got[(c, y, rep)][0] == "000" or got[(c, y, rep)][1] == "OFS")
                   for y, rep in REPORT_LIST)
        hits = {(y, rep): got[(c, y, rep)][1] for y, rep in REPORT_LIST
                if (c, y, rep) in got and got[(c, y, rep)][0] == "000"}
        n_cfs = sum(1 for v in hits.values() if v == "CFS")
        n_ofs = sum(1 for v in hits.values() if v == "OFS")
        last = max(hits, key=lambda k: (k[0], REP_ORDER[k[1]])) if hits else None
        first = min(hits, key=lambda k: (k[0], REP_ORDER[k[1]])) if hits else None
        rows.append({"조회순서": f["조회순서"], "corp_code": c, "회사명": f["회사명"], "현재_법인구분": f["현재_법인구분"],
                     "업종코드": f["업종코드"], "이름표시": f["이름표시"], "수집완료": done,
                     "자료있는_보고서수": len(hits), "연결": n_cfs, "별도": n_ofs,
                     "연결별도_혼재": bool(n_cfs and n_ofs),
                     "첫_자료": f"{first[0]}{first[1]}" if first else "",
                     "마지막_자료": f"{last[0]}{last[1]}" if last else ""})
    return rows


def summarize(firms, log, reason, n_api):
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
    done = [r for r in rows if r["수집완료"]]
    print("\n" + "=" * 66)
    print("본 수집 결과 (자료가 있었는지만 기록. 숫자는 읽지 않았습니다)")
    print("=" * 66)
    print(f"멈춤 사유: {reason}")
    print(f"대상 {len(rows):,}곳 중 수집 완료 {len(done):,}곳, 미완료 {len(rows)-len(done):,}곳 (이번 새 요청 {n_api:,}건)")
    if len(done) < len(rows):
        print("※ 순서가 시드 고정 무작위이므로 완료된 기업은 무작위 부분표본입니다. 같은 명령으로 이어서 할 수 있습니다.")
    print("응답 상태:", dict(Counter(r["status"] for r in log)))
    print("출처:", dict(Counter(r["source"] for r in log)))
    print(f"연결·별도가 한 기업 안에서 섞인 기업(완료 기업 중): {sum(1 for r in done if r['연결별도_혼재'])}곳")
    print("법인구분별 완료:", dict(Counter(r["현재_법인구분"] for r in done)))
    print("\n저장:", _show(TARGET), "|", _show(RESULT), "|", _show(LOG))
    print("이 결과는 'DART가 보고서를 응답으로 주는가'만 보여줍니다. A8 판단·표본 확정은 정제 단계 뒤에 합니다.")


def _show(path):
    try:
        return str(path.relative_to(config.BASE))
    except ValueError:
        return str(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="요청 수만 계산하고 요청은 보내지 않는다")
    ap.add_argument("--summary-only", action="store_true", help="저장된 응답만으로 결과표를 계산한다(요청 안 보냄)")
    ap.add_argument("--limit", type=int, default=None, help="순서의 앞에서 N곳만 처리한다(시험용)")
    ap.add_argument("--until", default=None, help="마감 시각(예: 2026-11-08T23:00). 그 시각 이후 새 기업은 시작하지 않는다")
    args = ap.parse_args()

    deadline = datetime.fromisoformat(args.until) if args.until else None
    firms = build_targets()
    if len(firms) != EXPECTED_N:
        print(f"※ 경고: 대상이 {len(firms):,}곳입니다(2026-11-05 확인값 {EXPECTED_N:,}곳과 다름). 선별 결과·코넥스 목록 파일을 확인하세요.")
    save_targets(firms)
    todo = firms[: args.limit] if args.limit else firms

    lo, hi, exp = plan(todo)
    print(f"대상 {len(firms):,}곳 중 이번에 처리할 곳 {len(todo):,}곳 × 보고서 {len(REPORT_LIST)}개 (2018~2024Q3)")
    print(f"아직 저장되지 않은 요청: 최소 {lo:,}건 / 최대 {hi:,}건 / 예상 {exp:,.0f}건 (선별 때의 연결·별도 구분으로 계산한 예상치)")
    print(f"소요 시간 추정: 1건 약 0.5~0.6초 가정 시 {exp*0.5/3600:.1f}~{exp*0.6/3600:.1f}시간 (선별 파일 시각에서 거칠게 역산한 값이며 실측 아님)")
    print(f"조회 순서는 시드 {config.SEED}로 고정한 무작위 순서입니다. 목록: {_show(TARGET)}")
    if deadline:
        print(f"마감 시각: {deadline:%Y-%m-%d %H:%M}")
    if args.dry_run:
        return

    allow_api = not args.summary_only
    if allow_api:
        print("DART에 수집을 시작합니다 (인증키가 환경변수에 있어야 합니다). 중간에 멈춰도 같은 명령으로 이어집니다.")
    log, reason, n_api = collect(todo, allow_api, deadline)
    summarize(todo, log, reason, n_api)


if __name__ == "__main__":
    main()


# ─── 저장된 결과 미리보기 (맨 위 5행) ───


# ─── 읽는 법과 주의 ───
