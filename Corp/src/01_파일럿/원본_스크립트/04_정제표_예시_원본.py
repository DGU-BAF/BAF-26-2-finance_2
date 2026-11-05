"""예시용: 내려받은 원자료(raw/fs)를 '기업×분기' 표로 바꿔 본다. **검증 전이며 분석에 그대로 쓰지 않는다.**

원자료(JSON)는 보고서 한 건마다 계정이 수백 줄 들어 있어 그대로는 분석할 수 없다. 이 스크립트는
(1) 계정명 규칙(config.ACCOUNT_PATTERNS)으로 필요한 계정을 고르고, (2) 분기 값으로 환원하고
(Q1~Q3는 3개월 값, Q4 = 연간 - 3분기 누적), (3) 차입비중과 후행 4분기 ICR을 예시로 계산한다.
계수·회귀는 계산하지 않는다.

실행: python -X utf8 04_example_table.py   (02 수집이 끝난 뒤 권장. 수집 중이면 읽지 못한 파일은 건너뜀)
출력: out/example_clean_table.csv, out/example_tables.xlsx
"""
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import config
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")

FILE_RE = re.compile(r"^(\d{8})_(\d{4})_(\d{5})_(CFS|OFS)\.json$")
REP_BY_CODE = {v: k for k, v in config.REPORTS.items()}
UNIT = 1_000_000  # 표시 단위: 백만원
QUARTER_SOURCE = [(1, "Q1"), (2, "H1"), (3, "Q3"), (4, "FY")]
REPORT_LABEL = {"Q1": "1분기", "H1": "반기", "Q3": "3분기", "FY": "사업(연간)"}
FLOWS = ["revenue", "op_income", "interest_exp", "fin_cost"]
STOCKS = ["assets", "st_borrow", "cur_ltd", "cur_bond"]


def parse_amount(text):
    if text is None:
        return None
    s = str(text).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def ord_key(row):
    try:
        return int(row.get("ord", "0") or 0)
    except ValueError:
        return 0


def find(rows, target):
    sj, pat = config.ACCOUNT_PATTERNS[target]
    sj_re, nm_re = re.compile(sj), re.compile(pat)
    hits = [
        r
        for r in rows
        if sj_re.fullmatch(r.get("sj_div", "")) and nm_re.search(re.sub(r"\s+", "", r.get("account_nm", "")))
    ]
    if not hits:
        return None
    hits.sort(key=ord_key)
    r = hits[0]
    return {"name": r.get("account_nm"), "amt": parse_amount(r.get("thstrm_amount")), "cum": parse_amount(r.get("thstrm_add_amount"))}


def load_reports(raw_dir):
    reports, skipped = {}, 0
    for path in sorted(Path(raw_dir).glob("*.json")):
        m = FILE_RE.match(path.name)
        if not m:
            continue
        corp, year, code, fs = m.groups()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            skipped += 1  # 수집 중인 파일 등
            continue
        if data.get("status") != "000":
            continue
        reports[(corp, int(year), REP_BY_CODE.get(code, code))] = (fs, data.get("list", []))
    return reports, skipped


def build_firm_rows(corp, meta, reports):
    recs = []
    years = sorted({y for (c, y, _r) in reports if c == corp})
    for y in years:
        rep = {k: reports.get((corp, y, k)) for k in ("Q1", "H1", "Q3", "FY")}
        fs_set = {v[0] for v in rep.values() if v}
        for qi, rkey in QUARTER_SOURCE:
            if not rep[rkey]:
                continue
            fs, rows = rep[rkey]
            rec = {
                "corp": corp, "name": meta.get("corp_name", ""), "cls": meta.get("corp_cls", ""),
                "induty": meta.get("induty_code", ""), "year": y, "q": qi, "fs": fs, "fs_mixed": len(fs_set) > 1,
            }
            for t in STOCKS:
                x = find(rows, t)
                rec[t] = x["amt"] if x else None
            for t in FLOWS:
                x = find(rows, t)
                if rkey != "FY":
                    rec[t] = x["amt"] if x else None  # 1분기·반기·3분기 보고서의 당기금액 = 3개월 값(가이드)
                else:
                    annual = x["amt"] if x else None
                    cum = None
                    if rep["Q3"]:
                        x3 = find(rep["Q3"][1], t)
                        cum = x3["cum"] if x3 else None
                    if cum is None and all(rep[k] for k in ("Q1", "H1", "Q3")):
                        parts = [find(rep[k][1], t) for k in ("Q1", "H1", "Q3")]
                        if all(p and p["amt"] is not None for p in parts):
                            cum = sum(p["amt"] for p in parts)
                    rec[t] = annual - cum if annual is not None and cum is not None else None
            # 연도 합계 점검용 값(3개월 값 합 대비 3분기 누적)
            recs.append(rec)
    recs.sort(key=lambda r: (r["year"], r["q"]))
    return recs


def add_derived(recs):
    for i, r in enumerate(recs):
        comps = [r["st_borrow"], r["cur_ltd"], r["cur_bond"]]
        r["debt_ratio"], r["debt_note"] = None, ""
        if r["assets"] not in (None, 0):
            if all(c is None for c in comps):
                r["debt_note"] = "차입 관련 세 항목이 모두 없음(0인지 추출 실패인지 구분 불가)"
            else:
                absent = [n for n, c in zip(("단기차입금", "유동성장기부채", "유동성사채"), comps) if c is None]
                r["debt_ratio"] = sum(c or 0 for c in comps) / r["assets"] * 100
                r["debt_note"] = ("없는 항목을 0으로 처리: " + ", ".join(absent)) if absent else ""
        window = recs[i - 3 : i + 1] if i >= 3 else []
        consecutive = len(window) == 4 and all(
            window[k + 1]["year"] * 4 + window[k + 1]["q"] == window[k]["year"] * 4 + window[k]["q"] + 1 for k in range(3)
        )

        def ttm(key):
            if not consecutive or any(w[key] is None for w in window):
                return None
            return sum(w[key] for w in window)

        r["op_ttm"] = ttm("op_income")
        ie, fc = ttm("interest_exp"), ttm("fin_cost")
        r["int_ttm"], r["int_src"] = (ie, "이자비용") if ie is not None else ((fc, "금융비용(대용)") if fc is not None else (None, ""))
        r["icr"], r["icr_note"] = None, ""
        if r["op_ttm"] is None or r["int_ttm"] is None:
            r["icr_note"] = "후행 4분기 값이 연속으로 없음 또는 이자 항목 없음"
        elif r["int_ttm"] <= 0:
            r["icr_note"] = "이자 합계가 0 이하라 ICR 정의 불가"
        else:
            r["icr"] = r["op_ttm"] / r["int_ttm"]
            if r["int_src"].startswith("금융비용"):
                r["icr_note"] = "이자비용이 아니라 금융비용으로 계산(환손실 등 포함 가능)"
    return recs


def m(v):
    return None if v is None else round(v / UNIT, 1)


def main():
    raw_dir = config.RAW / "fs"
    sample_path = config.OUT / "pilot_sample.csv"
    if not raw_dir.exists() or not sample_path.exists():
        sys.exit("raw/fs 또는 out/pilot_sample.csv가 없습니다. 02를 먼저 실행하세요.")
    with open(sample_path, encoding="utf-8-sig", newline="") as fh:
        meta = {r["corp_code"]: r for r in csv.DictReader(fh)}
    reports, skipped = load_reports(raw_dir)
    corps = sorted({c for (c, _y, _r) in reports})
    print(f"자료가 있는 보고서 {len(reports)}건, 기업 {len(corps)}곳 (읽지 못한 파일 {skipped}건)")

    all_rows = []
    summary = []
    for corp in corps:
        recs = add_derived(build_firm_rows(corp, meta.get(corp, {}), reports))
        all_rows.extend(recs)
        by_year = {}
        for r in recs:
            by_year.setdefault(r["year"], []).append(r)
        mismatch = 0
        for y, rs in by_year.items():
            if len(rs) == 4 and all(r["op_income"] is not None for r in rs):
                # Q4 = 연간 - 3분기 누적이므로, 합계가 연간과 다르면 3개월 값의 합이 3분기 누적과 다르다는 뜻
                rep_fy = reports.get((corp, y, "FY"))
                rep_q3 = reports.get((corp, y, "Q3"))
                if rep_fy and rep_q3:
                    annual = find(rep_fy[1], "op_income")
                    if annual and annual["amt"] is not None:
                        total = sum(r["op_income"] for r in rs)
                        if abs(total - annual["amt"]) > 0.005 * max(abs(annual["amt"]), 1):
                            mismatch += 1
        summary.append(
            {
                "기업코드": corp, "기업명": meta.get(corp, {}).get("corp_name", ""), "시장구분(현재)": meta.get(corp, {}).get("corp_cls", ""),
                "자료 있는 분기 수": len(recs),
                "이자비용 있는 분기": sum(r["interest_exp"] is not None for r in recs),
                "금융비용 있는 분기": sum(r["fin_cost"] is not None for r in recs),
                "차입비중 계산 가능 분기": sum(r["debt_ratio"] is not None for r in recs),
                "ICR 계산 가능 분기": sum(r["icr"] is not None for r in recs),
                "연결·별도 혼재 연도 수": len({r["year"] for r in recs if r["fs_mixed"]}),
                "연간 합계 불일치 연도 수": mismatch,
            }
        )

    headers = [
        "기업코드", "기업명", "시장구분(현재)", "업종코드", "연도", "분기", "재무제표", "연도 안 연결·별도 혼재",
        "자산총계(백만원)", "단기차입금", "유동성장기부채", "유동성사채", "차입비중(%)", "차입비중 비고",
        "매출액(분기)", "영업이익(분기)", "이자비용(분기)", "금융비용(분기)",
        "영업이익 후행4분기", "이자 후행4분기", "이자 출처", "ICR 후행4분기(배)", "ICR 비고",
    ]
    table = []
    for r in all_rows:
        table.append(
            [
                r["corp"], r["name"], r["cls"], r["induty"], r["year"], f"{r['q']}Q", "연결" if r["fs"] == "CFS" else "별도",
                "예" if r["fs_mixed"] else "", m(r["assets"]), m(r["st_borrow"]), m(r["cur_ltd"]), m(r["cur_bond"]),
                None if r["debt_ratio"] is None else round(r["debt_ratio"], 2), r["debt_note"],
                m(r["revenue"]), m(r["op_income"]), m(r["interest_exp"]), m(r["fin_cost"]),
                m(r["op_ttm"]), m(r["int_ttm"]), r["int_src"], None if r["icr"] is None else round(r["icr"], 2), r["icr_note"],
            ]
        )
    config.OUT.mkdir(exist_ok=True)
    with open(config.OUT / "example_clean_table.csv", "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(table)

    # 원자료 발췌: 네 보고서가 모두 있는 첫 기업-연도
    excerpt = []
    pick = None
    for corp in corps:
        for y in sorted({yy for (c, yy, _r) in reports if c == corp}, reverse=True):
            if all((corp, y, k) in reports for k in ("Q1", "H1", "Q3", "FY")):
                pick = (corp, y)
                break
        if pick:
            break
    if pick:
        corp, y = pick
        for k in ("Q1", "H1", "Q3", "FY"):
            fs, rows = reports[(corp, y, k)]
            for t, (sj, pat) in config.ACCOUNT_PATTERNS.items():
                sj_re, nm_re = re.compile(sj), re.compile(pat)
                for r in rows:
                    if sj_re.fullmatch(r.get("sj_div", "")) and nm_re.search(re.sub(r"\s+", "", r.get("account_nm", ""))):
                        excerpt.append([REPORT_LABEL[k], "연결" if fs == "CFS" else "별도", r.get("sj_div"), r.get("account_nm"), r.get("thstrm_amount"), r.get("thstrm_add_amount")])
                        break

    firms_ie = sum(1 for s in summary if s["이자비용 있는 분기"] > 0)
    firms_fc = sum(1 for s in summary if s["금융비용 있는 분기"] > 0)
    rows_no_debt = sum(1 for r in all_rows if r["debt_note"].startswith("차입 관련 세 항목"))
    firms_mismatch = sum(1 for s in summary if s["연간 합계 불일치 연도 수"] > 0)
    seen_text = (
        f"기업 {len(corps)}곳 중 '이자비용' 계정이 한 번이라도 있는 기업 {firms_ie}곳, '금융비용(금융원가)'이 있는 기업 {firms_fc}곳. "
        f"차입 관련 세 항목(단기차입금·유동성장기부채·유동성사채)이 모두 없는 행 {rows_no_debt}/{len(all_rows)}. "
        f"3개월 값의 합이 3분기 누적과 안 맞는 연도가 있는 기업 {firms_mismatch}곳."
    )

    wb = Workbook()
    ws0 = wb.active
    ws0.title = "읽는 법"
    pick_text = f"{meta.get(pick[0], {}).get('corp_name', pick[0])} {pick[1]}년" if pick else "(해당 없음)"
    notes = [
        ("이 파일의 성격", "내려받은 원자료를 분석용 표로 바꾼 **예시**입니다. 검증 전이므로 분석·논문에 그대로 쓰지 마세요."),
        ("만든 시각", datetime.now().strftime("%Y-%m-%d %H:%M") + f" · 자료가 있는 기업 {len(corps)}곳, 보고서 {len(reports)}건 (수집이 끝나지 않았다면 일부만 포함)"),
        ("원자료 그대로 못 쓰는 이유", "보고서 한 건마다 계정이 100~수백 줄이고, 1·2·3분기는 3개월 값과 누적 값이 따로 있고, 4분기는 따로 없어서 연간에서 빼야 합니다. 계정명도 기업마다 다릅니다(예: '유동성 장기부채'처럼 띄어쓰기가 다른 경우)."),
        ("분기 값 만들기", "1~3분기: 각 보고서의 당기금액(3개월). 4분기: 사업보고서 연간 - 3분기 누적. 재무상태표 항목(자산·차입금)은 해당 분기 말 값."),
        ("단위", "표의 금액은 백만원(원자료는 원 단위로 보임: 응답 한 건 기준). 단위가 기업마다 같은지는 아직 확인하지 못했습니다."),
        ("차입비중(%)", "(단기차입금 + 유동성장기부채 + 유동성사채) ÷ 자산총계 × 100. **해당 계정이 응답에 없으면 0으로 처리**했고 비고에 적었습니다. '없음=0'이 맞는지는 아직 검증하지 않았습니다(사전 고정 문서 A10)."),
        ("ICR(후행 4분기)", "후행 4분기 영업이익 ÷ 후행 4분기 이자. 이자비용 항목이 없으면 금융비용으로 대신했고 '이자 출처'에 표시했습니다. 이자가 0 이하이거나 4분기가 연속으로 없으면 비웁니다."),
        ("이번 수집분에서 보이는 것", seen_text),
        ("한 눈에 볼 문제", "(1) 이자비용 항목이 없는 기업이 있음 (2) 연결·별도가 섞인 연도가 있음 (3) 상장 전후나 폐지로 분기가 비는 기업이 있음 (4) 차입 항목 부재를 0으로 봐도 되는지 미검증"),
        ("원자료_발췌 시트", f"{pick_text}의 네 보고서에서 우리가 고른 계정 한 줄씩을 원문 그대로 보여 줍니다."),
        ("점검_요약 시트", "기업별로 무엇이 얼마나 구해졌는지 세어 둔 표입니다."),
        ("주의", "이 표는 파일럿 40곳 중 수집된 기업뿐이며 표본 대표성이 없습니다. 시장구분은 '현재' 기준이라 과거 상장 여부를 뜻하지 않습니다."),
    ]
    ws0.append(["항목", "내용"])
    for k, v in notes:
        ws0.append([k, v.replace("**", "")])
    ws0.column_dimensions["A"].width = 26
    ws0.column_dimensions["B"].width = 120
    for row in ws0.iter_rows(min_row=1):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws0["A1"].font = ws0["B1"].font = Font(bold=True)

    ws1 = wb.create_sheet("정제표_예시")
    ws1.append(headers)
    for row in table:
        ws1.append(row)
    ws1.freeze_panes = "F2"
    for i in range(1, len(headers) + 1):
        ws1.column_dimensions[get_column_letter(i)].width = 16
        ws1.cell(row=1, column=i).font = Font(bold=True)
        ws1.cell(row=1, column=i).fill = PatternFill("solid", fgColor="E6F1FB")
        ws1.cell(row=1, column=i).alignment = Alignment(wrap_text=True, vertical="center")
    ws1.column_dimensions["N"].width = 38
    ws1.column_dimensions["W"].width = 42

    ws2 = wb.create_sheet("원자료_발췌")
    ws2.append(["보고서", "재무제표", "구분(sj_div)", "계정명(원문)", "당기금액(원, 원문)", "당기누적금액(원, 원문)"])
    for row in excerpt:
        ws2.append(row)
    for i, w in enumerate([12, 10, 14, 28, 24, 24], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
        ws2.cell(row=1, column=i).font = Font(bold=True)

    ws3 = wb.create_sheet("점검_요약")
    if summary:
        ws3.append(list(summary[0].keys()))
        for s in summary:
            ws3.append(list(s.values()))
        for i in range(1, len(summary[0]) + 1):
            ws3.column_dimensions[get_column_letter(i)].width = 18
            ws3.cell(row=1, column=i).font = Font(bold=True)
            ws3.cell(row=1, column=i).alignment = Alignment(wrap_text=True)

    wb.save(config.OUT / "example_tables.xlsx")
    print(f"저장: out/example_clean_table.csv ({len(table)}행), out/example_tables.xlsx")
    print("점검 요약:")
    for s in summary:
        print(" ", s["기업명"], {k: v for k, v in s.items() if k not in ("기업코드", "기업명")})


if __name__ == "__main__":
    main()
