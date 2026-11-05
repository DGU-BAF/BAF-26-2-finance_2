"""국내 선행연구 PDF에서 '상장폐지·생존편의' 관련 문장이 어느 쪽에 있는지 확인한다. (A9 근거 점검용)

하는 일: Corp/논문/상장 vs 상장폐지/ 안의 PDF에서 글자를 뽑아, 아래 확인 목록의 말이 몇 쪽에 나오는지 출력한다.
읽기만 한다. 아무 파일도 만들지 않는다. 뽑은 글자는 저장하지 않는다(논문 저작권).

실행: python -X utf8 논문_원문_확인.py
필요: pip install pymupdf

주의
- 쪽수는 'PDF 파일 안의 쪽'이다. 학술지 쪽수와 다를 수 있다(예: 김성환·김미나 PDF 6쪽 = 학술지 1258쪽).
- 일부 PDF는 한글 띄어쓰기가 사라진 채 추출된다(예: 이석근 외 2016). 그래서 확인 말은 공백을 지운 글자에서 찾는다.
- '찾지 못함'은 추출된 글자에서 못 찾았다는 뜻이다. 표나 그림 속 글자는 확인하지 못한다.
"""
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

sys.stdout.reconfigure(encoding="utf-8")

PAPERS = Path(__file__).resolve().parents[2] / "논문" / "상장 vs 상장폐지"

# (PDF 파일 이름의 일부, 논문 설명, 확인할 말 목록). 확인 말은 공백을 지운 글자에서 찾는다.
CHECKS = [
    ("감사인의 평판", "김성환·김미나(2014) 대한경영학회지 27(8)",
     ["상장폐지기업도포함", "불균형패널", "재무자료를구할수없는기업은제외", "생존자편의를제거"]),
    ("한국증권시장에서의 장기성과", "정형찬(2007) Asia-Pacific J. of Financial Studies 36(2)",
     ["생존편의(survivorbias)를최소화", "Delisted", "하향편의"]),
    ("상장폐지기업의 상장폐지전", "이석근·조광희·양동훈(2016) 회계저널 25(2)",
     ["28,224", "자본완전잠식", "회계정보미비", "폐업으로인하여"]),
    ("상장폐지기업 예측모형", "배기수·정설희(2011) 세무회계연구 30",
     ["상장공시시스템", "Kis－ValueⅢ", "81개"]),
    ("최고경영자의 특성", "장지영·김지령(2015) 회계ㆍ세무와 감사 연구 57(1)",
     ["상장폐지및관리대상", "생존편의문제가제기"]),
    ("통화정책과_기업_재무", "조상섭·배기수(2026) 상업경영연구 40(2)",
     ["TS2000", "균형패널", "이자비용을매출액", "상장폐지", "생존"]),
    ("미 연준의 긴축", "도영웅(2026) 국제경제연구 32(3)",
     ["Value Search", "하위5%", "상장폐지", "생존"]),
]


def squeeze(text):
    return re.sub(r"\s+", "", text)


def main():
    if not PAPERS.exists():
        sys.exit(f"논문 폴더가 없습니다: {PAPERS}")
    for key, label, phrases in CHECKS:
        hit = [p for p in PAPERS.glob("*.pdf") if key in p.name]
        print("=" * 70)
        print(label)
        if not hit:
            print("  PDF를 찾지 못함(폴더에 있는지, 이름에 아래 말이 들어 있는지 확인):", key)
            continue
        doc = fitz.open(hit[0])
        pages = [squeeze(pg.get_text()) for pg in doc]
        print(f"  파일: {hit[0].name} | PDF {len(doc)}쪽")
        for ph in phrases:
            target = squeeze(ph)
            found = [i + 1 for i, t in enumerate(pages) if target in t]
            print(f"  - '{ph}': " + (f"PDF {found}쪽" if found else "찾지 못함"))


if __name__ == "__main__":
    main()
