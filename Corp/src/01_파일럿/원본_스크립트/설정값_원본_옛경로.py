"""파일럿 설정. 값을 바꾸면 사전 고정 문서의 변경 기록에도 적는다."""
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw"          # OpenDART 원본 응답 (수정하지 않는다)
OUT = BASE / "out"          # 점검 결과표

# 수집 연도: 후행 4분기 합산(TTM)을 위해 2018부터
YEARS = list(range(2018, 2025))

# 보고서 코드 (OpenDART 개발가이드)
REPORTS = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}

# 연결 우선, 없으면 별도 (사전 고정 문서 3절). 한 기업 안에서 섞지 않는지는 03에서 점검
FS_ORDER = ["CFS", "OFS"]

# 호출 간 대기(초). 요청 제한(일반적으로 20,000건 안팎에서 오류 020)은 가이드에 기간 단위가 없음
SLEEP = 0.4

# 01: company.json을 확인해 볼 무작위 기업 수 (업종코드 체계를 보기 위한 표본)
N_COMPANY_PROBE = 150

# 02: 파일럿 대상 기업 수
N_PILOT = 40

# 무작위 시드 (재현용)
SEED = 20261102

# 제조업 업종코드 접두어. induty_code의 체계/자릿수는 가이드에 설명이 없어서
# 01을 실행해 실제 값을 본 뒤 직접 채운다. None이면 02가 실행을 거부한다.
# 예(확인 전 가정이므로 그대로 쓰지 말 것): KSIC 계열이라면 ("10","11",...,"33")
# 2026-11-02 01단계(기업개황 150곳) 결과로 채움: induty_code는 한국표준산업분류(KSIC) 계열이며 3~5자리,
# 앞 2자리가 대분류 단위. 제조업 = 앞 2자리 10~34. 근거와 한계는 사전 고정 문서 3절·A1 참고(팀 확인 필요).
MANUFACTURING_PREFIXES = tuple(str(i) for i in range(10, 35))

# 계정 매핑 규칙(첫 추정). (재무제표 구분, 정규식). 계정명의 공백을 모두 지운 뒤 비교한다.
# 03 점검과 04 예시표가 같은 규칙을 쓴다. 파일럿 결과를 보고 여기서 고친다.
ACCOUNT_PATTERNS = {
    "assets": ("BS", r"^자산총계$"),
    "revenue": ("IS|CIS", r"^(매출액|수익\(매출액\)|영업수익)"),
    "op_income": ("IS|CIS", r"^영업이익"),
    "interest_exp": ("IS|CIS", r"^이자비용"),
    "fin_cost": ("IS|CIS", r"^(금융비용|금융원가)"),
    "interest_paid_cf": ("CF", r"이자.{0,2}지급"),
    "st_borrow": ("BS", r"^단기차입금"),
    "cur_ltd": ("BS", r"^(유동성장기차입금|유동성장기부채|유동성차입금)"),
    "cur_bond": ("BS", r"^(유동성사채|유동성장기사채)"),
}

# 지주회사·스팩 표시용 이름 규칙 (표시만 하고 자동 삭제하지 않는다)
FLAG_NAME_PATTERNS = {
    "spac": r"스팩|SPAC|제\s*\d+\s*호",
    "holding": r"홀딩스|지주|Holdings",
}
