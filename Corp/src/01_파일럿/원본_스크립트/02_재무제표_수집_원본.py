"""2단계: 파일럿 기업을 층화 무작위로 뽑고 재무제표 전체(fnlttSinglAcntAll)를 받아 저장한다.

실행: python -X utf8 02_pilot_fetch.py --dry-run     (호출 수만 계산)
      python -X utf8 02_pilot_fetch.py               (실제 수집, 이미 받은 파일은 건너뜀)
회귀·계수는 계산하지 않는다. 오직 자료 추출만 한다.
"""
import argparse
import csv
import json
import random
import sys
import time
from collections import defaultdict

import config
from dart_api import CACHEABLE_STATUSES, FatalApiStatus, LimitExceeded, get_json

sys.stdout.reconfigure(encoding="utf-8")


def load_company_table(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def is_manufacturing(code, prefixes):
    return any(code.startswith(p) for p in prefixes)


def stratified_sample(rows, n, seed):
    """(법인구분, 업종코드 앞 2자리)별로 섞은 뒤 돌아가며 한 개씩 뽑는다. 결과(ICR 등)는 쓰지 않는다."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["corp_cls"], r["induty_code"][:2])].append(r)
    rng = random.Random(seed)
    keys = sorted(groups)
    for k in keys:
        rng.shuffle(groups[k])
    picked = []
    while len(picked) < n and any(groups[k] for k in keys):
        for k in keys:
            if groups[k] and len(picked) < n:
                picked.append(groups[k].pop())
    return picked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-file", default=str(config.OUT / "company_probe.csv"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not config.MANUFACTURING_PREFIXES:
        sys.exit(
            "config.MANUFACTURING_PREFIXES가 비어 있습니다. 01을 실행해 induty_code 값을 확인한 뒤 직접 채우세요."
        )

    rows = load_company_table(args.company_file)
    manu = [r for r in rows if is_manufacturing(r["induty_code"], config.MANUFACTURING_PREFIXES)]
    print(f"기업개황이 있는 기업 {len(rows)}개 중 제조업 {len(manu)}개")
    # 자동 제외는 하지 않고 표시만 한다(사전 고정 문서 3절: 최종 판단은 수동)
    flagged = [r for r in manu if r["name_flags"]]
    print(f"이름 기준 지주/스팩 표시 {len(flagged)}개 (표본에서 자동 삭제하지 않음, 수동 검토)")
    nonDec = [r for r in manu if r["acc_mt"] != "12"]
    print(f"결산월이 12월이 아닌 기업 {len(nonDec)}개 (포함 여부는 사전 고정 문서 A2에서 결정)")

    sample = stratified_sample(manu, config.N_PILOT, config.SEED)
    if not sample:
        sys.exit("제조업으로 분류된 기업이 없습니다. MANUFACTURING_PREFIXES와 induty_code 값을 다시 확인하세요.")
    config.OUT.mkdir(exist_ok=True)
    with open(config.OUT / "pilot_sample.csv", "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sample[0].keys()))
        writer.writeheader()
        writer.writerows(sample)
    print(f"파일럿 표본 {len(sample)}개 저장: out/pilot_sample.csv")

    n_calls = len(sample) * len(config.YEARS) * len(config.REPORTS)
    print(
        f"최대 호출 수: {len(sample)}개 × {len(config.YEARS)}년 × {len(config.REPORTS)}보고서 = {n_calls:,}건"
        f" (연결에 자료가 없어 별도로 다시 부르면 최대 {n_calls * len(config.FS_ORDER):,}건)"
    )
    if args.dry_run:
        return

    config.RAW.mkdir(exist_ok=True)
    (config.RAW / "fs").mkdir(exist_ok=True)
    log_rows = []
    try:
        for i, firm in enumerate(sample, 1):
            for year in config.YEARS:
                for rep_name, rep_code in config.REPORTS.items():
                    for fs in config.FS_ORDER:
                        path = config.RAW / "fs" / f"{firm['corp_code']}_{year}_{rep_code}_{fs}.json"
                        if path.exists():
                            data = json.loads(path.read_text(encoding="utf-8"))
                            cached = True
                        else:
                            data = get_json(
                                "fnlttSinglAcntAll.json",
                                {
                                    "corp_code": firm["corp_code"],
                                    "bsns_year": str(year),
                                    "reprt_code": rep_code,
                                    "fs_div": fs,
                                },
                            )
                            if data.get("status") in CACHEABLE_STATUSES:
                                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                            cached = False
                            time.sleep(config.SLEEP)
                        status = data.get("status")
                        log_rows.append(
                            {
                                "corp_code": firm["corp_code"],
                                "year": year,
                                "report": rep_name,
                                "fs_div": fs,
                                "status": status,
                                "n_rows": len(data.get("list", [])) if status == "000" else 0,
                                "cached": cached,
                            }
                        )
                        if status == "000":
                            break  # 연결이 있으면 별도는 부르지 않는다
                        if status != "013":  # 013(조회 데이터 없음)이면 다음 구분으로, 그 외는 기록하고 멈춤
                            print(f"  {firm['corp_code']} {year} {rep_name} {fs}: 상태 {status} {data.get('message')}")
                            break
            print(f"  {i}/{len(sample)} 기업 완료")
    except LimitExceeded as exc:
        print(str(exc))
    except FatalApiStatus as exc:
        print("중단:", exc)
    finally:
        if log_rows:
            with open(config.OUT / "fetch_log.csv", "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(log_rows[0].keys()))
                writer.writeheader()
                writer.writerows(log_rows)
            print("수집 로그 저장: out/fetch_log.csv")


if __name__ == "__main__":
    main()
