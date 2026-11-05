"""OpenDART 호출 공통 모듈. 인증키는 환경변수 DART_API_KEY에서만 읽고 어디에도 쓰거나 출력하지 않는다."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://opendart.fss.or.kr/api/"


class LimitExceeded(RuntimeError):
    """요청 제한 초과(상태코드 020)."""


class ApiError(RuntimeError):
    pass


class FatalApiStatus(RuntimeError):
    """키·권한·서버 문제처럼 계속 호출해도 소용없는 상태코드. 응답을 저장하지 않고 즉시 멈춘다."""


# 010 등록되지 않은 키, 011 사용 중지 키, 012 접근 불가 IP, 100 부적절한 필드 값, 101 부적절한 접근,
# 800 시스템 점검, 900 정의되지 않은 오류, 901 키 사용 불가(개인정보 보유기간 만료) — 개발가이드 오류 코드 표
FATAL_STATUSES = {"010", "011", "012", "100", "101", "800", "900", "901"}


def api_key():
    key = os.environ.get("DART_API_KEY", "").strip()
    if len(key) != 40:
        raise SystemExit(
            "환경변수 DART_API_KEY(40자리)가 설정되어 있지 않습니다. README의 '인증키 설정'을 따르세요."
        )
    return key


def _open(path, params, timeout=60):
    query = urllib.parse.urlencode({**params, "crtfc_key": api_key()})
    req = urllib.request.Request(
        BASE_URL + path + "?" + query, headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:  # 주소에 키가 들어 있으므로 주소는 메시지에 넣지 않는다
        raise ApiError(f"HTTP {exc.code} ({path})") from None
    except urllib.error.URLError as exc:
        raise ApiError(f"네트워크 오류 ({path}): {exc.reason}") from None


def _with_retry(path, params, retries=3):
    for attempt in range(retries):
        try:
            return _open(path, params)
        except ApiError:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def get_json(path, params):
    raw = _with_retry(path, params)
    data = json.loads(raw.decode("utf-8"))
    status = data.get("status")
    if status == "020":
        raise LimitExceeded("요청 제한 초과(020). 오늘은 중단하고 이어서 실행하세요(결과는 저장되어 있습니다).")
    if status in FATAL_STATUSES:
        raise FatalApiStatus(f"상태 {status}: {data.get('message')} — 키/권한/서버를 확인하세요. 응답은 저장하지 않았습니다.")
    return data


# 저장(캐시)해도 되는 응답: 정상(000)과 '조회 데이터 없음'(013)뿐. 그 외는 저장하지 않는다
CACHEABLE_STATUSES = {"000", "013"}


def get_bytes(path, params):
    """corpCode.xml처럼 ZIP으로 오는 응답. 오류 시 JSON/XML 메시지가 오므로 검사한다."""
    raw = _with_retry(path, params)
    if not raw.startswith(b"PK"):
        text = raw[:300].decode("utf-8", errors="replace")
        if "020" in text:
            raise LimitExceeded("요청 제한 초과(020).")
        raise ApiError("ZIP이 아닌 응답이 왔습니다: " + text.replace("\n", " "))
    return raw
