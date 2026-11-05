"""1단계: 상장사 목록을 만들고, 표본 일부의 기업개황을 받아 업종코드 체계를 확인한다.

실행: python -X utf8 01_corp_list.py            (표본 N_COMPANY_PROBE개만 기업개황 조회)
      python -X utf8 01_corp_list.py --all      (상장사 전체 기업개황 조회, 호출 수가 많음)
"""
import argparse
import csv
import io
import json
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

import config
from dart_api import CACHEABLE_STATUSES, FatalApiStatus, LimitExceeded, get_bytes, get_json

sys.stdout.reconfigure(encoding="utf-8")


def parse_corp_code_zip(zip_bytes):
    """corpCode.xml ZIP → [{corp_code, corp_name, stock_code, modify_date}]"""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = zf.namelist()[0]
        root = ET.fromstring(zf.read(name))
    rows = []
    for node in root.findall("list"):
        rows.append(
            {
                "corp_code": (node.findtext("corp_code") or "").strip(),
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "stock_code": (node.findtext("stock_code") or "").strip(),
                "modify_date": (node.findtext("modify_date") or "").strip(),
            }
        )
    return rows


def name_flags(name):
    flags = [k for k, pat in config.FLAG_NAME_PATTERNS.items() if re.search(pat, name)]
    return ",".join(flags)


def write_csv(path, rows, fields):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="상장사 전체의 기업개황을 조회")
    args = parser.parse_args()

    config.RAW.mkdir(exist_ok=True)
    config.OUT.mkdir(exist_ok=True)
    (config.RAW / "company").mkdir(exist_ok=True)

    zip_path = config.RAW / "corpCode.zip"
    if zip_path.exists():
        zip_bytes = zip_path.read_bytes()
    else:
        zip_bytes = get_bytes("corpCode.xml", {})
        zip_path.write_bytes(zip_bytes)
    rows = parse_corp_code_zip(zip_bytes)
    listed = [r for r in rows if r["stock_code"]]
    print(f"전체 법인 {len(rows):,}개 → 종목코드가 있는 상장사 {len(listed):,}개")
    write_csv(config.OUT / "listed_all.csv", listed, ["corp_code", "corp_name", "stock_code", "modify_date"])

    targets = list(listed)
    if not args.all:
        random.Random(config.SEED).shuffle(targets)
        targets = targets[: config.N_COMPANY_PROBE]
    print(f"기업개황(company.json) 조회 대상 {len(targets):,}개 (이미 받은 것은 건너뜀)")

    table = []
    try:
        for i, row in enumerate(targets, 1):
            cache = config.RAW / "company" / f"{row['corp_code']}.json"
            if cache.exists():
                data = json.loads(cache.read_text(encoding="utf-8"))
            else:
                data = get_json("company.json", {"corp_code": row["corp_code"]})
                if data.get("status") in CACHEABLE_STATUSES:
                    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                time.sleep(config.SLEEP)
            if data.get("status") != "000":
                print(f"  {row['corp_code']} 상태 {data.get('status')} {data.get('message')}")
                continue
            table.append(
                {
                    "corp_code": row["corp_code"],
                    "corp_name": row["corp_name"],
                    "stock_code": row["stock_code"],
                    "corp_cls": data.get("corp_cls", ""),
                    "induty_code": str(data.get("induty_code", "")).strip(),
                    "acc_mt": data.get("acc_mt", ""),
                    "name_flags": name_flags(row["corp_name"]),
                }
            )
            if i % 25 == 0:
                print(f"  {i}/{len(targets)}")
    except LimitExceeded as exc:
        print(str(exc))
    except FatalApiStatus as exc:
        sys.exit(f"중단: {exc}")

    fields = ["corp_code", "corp_name", "stock_code", "corp_cls", "induty_code", "acc_mt", "name_flags"]
    out_name = "company_all.csv" if args.all else "company_probe.csv"
    write_csv(config.OUT / out_name, table, fields)
    print(f"\n저장: out/{out_name} ({len(table)}개)")

    # 업종코드 체계를 눈으로 확인하기 위한 요약
    from collections import Counter

    print("\n[법인구분 corp_cls] (Y 유가, K 코스닥, N 코넥스, E 기타)")
    print(Counter(r["corp_cls"] for r in table))
    print("\n[결산월 acc_mt]")
    print(Counter(r["acc_mt"] for r in table))
    print("\n[induty_code 자릿수]")
    print(Counter(len(r["induty_code"]) for r in table))
    print("\n[induty_code 앞 2자리 분포]")
    print(sorted(Counter(r["induty_code"][:2] for r in table).items()))
    print("\n[이름 기반 표시(스팩/지주)]")
    print(Counter(r["name_flags"] or "없음" for r in table))
    print("\n다음 단계: out 폴더의 CSV에서 induty_code 값을 직접 보고 config.MANUFACTURING_PREFIXES를 채우세요.")
    print("(분류 체계와 자릿수는 가이드에 설명이 없어서 값으로 확인해야 합니다.)")


if __name__ == "__main__":
    main()
