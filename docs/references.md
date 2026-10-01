# 참고문헌과 확인 수준

논문 PDF는 저작권 문제로 레포에 포함하지 않았다. 확인 수준: **본문** = 본문을 열어 해당 주장과 맥락을 확인 / **본문 일부** = 일부 절만 확인 / **초록** = 초록·검색 요약 수준 / **팀 문서 기재** = 팀 문서에 적혀 있으나 이 레포 작업 중 미확인.

방법론 문헌은 결과 수치가 아니라 **구조만 원용**하며 계산은 우리 자료로 새로 했다. 어떤 선행연구도 우리 식(사전 평균으로 고정한 단기부채 노출도 × Post, 업종·연도 고정효과)과 같은 사양은 아니며, 여러 연구의 구조를 조합한 설계이다.

| 문헌 | 이번 연구에서의 쓰임 | 확인 수준 |
|---|---|---|
| 한국은행(2021), 「이자보상배율 취약기업 증가 배경 및 시사점」 | ICR 분해(수익성·차입금의존도·평균차입비용) 배경 | 팀 문서 기재 |
| 통계청, 「이용자용 통계정보보고서: 기업경영분석」 | 차입금의존도 = 차입금 ÷ 총자산 정의, ICR 정의 | 본문 |
| Ippolito, Ozdagli & Perez-Orive (2018, JME) | 금리 노출 지표의 총자산 분모, 단기차입 효과 불분명, 이자부담 지표, 양쪽 1% winsorize | 본문 |
| Almeida 외 (2012, CFR) | 사전에 고정한 만기구조 노출도 × 충격 이후 비교 | 본문(워킹페이퍼) |
| Jeenas (2019, 워킹페이퍼) | 레버리지·유동성 × 충격 설계 | 본문 |
| Ottonello & Winberry (2020, Econometrica) | 고정효과·교차항·winsorize 관행 | 본문 |
| Card & Krueger (1994) | 이중차분의 고전적 적용 | 본문(NBER 워킹페이퍼) |
| Roth, Sant'Anna, Bilinski & Poe (2023, J. Econometrics) | 사전추세 검정의 한계와 검정력 진단 | 본문 |
| Cameron, Gelbach & Miller (2008, REStat) | 소표본 군집 추론, wild cluster bootstrap | 본문 |
| Callaway, Goodman-Bacon & Sant'Anna (2024, NBER WP 32117) | 연속형 노출도 이중차분 해석의 한계: 처치받지 않은 집단이 없을 때 인과 해석에 더 강한 가정이 필요 | 본문 일부(식별·TWFE 해석 절; 실증·부록 미확인) |
| Chen & Roth (2024, QJE) | log-like 변환(asinh 등) 효과는 %효과로 읽지 않는다. 음수 outcome은 이 논문 범위 밖 | 본문 일부(초록·2절) |
| Cohn, Liu & Wardlaw (2022, JFE) | 0 이상 count형 변수에서 log(1+y) 회귀의 문제, Poisson 권고 | 본문 일부(초록·서론) |
| Roodman, MacKinnon, Nielsen & Webb (2019, Stata Journal), boottest | 정식 wild cluster bootstrap 도구 | 존재 확인, 본문 미확인 |
| MacKinnon & Webb (2018), The Wild Bootstrap for Few (Treated) Clusters, QED WP 1364 | wild bootstrap의 한계(처치 군집이 적은 경우) | 제목·초록 수준 |
| Adams, Hayunga, Mansi, Reeb & Verardi (2019, Financial Management) | 다변량 극단값 식별과 로버스트 추정 | 초록 |
| Mullahy & Norton (2024, OBES); Bellemare & Wichman (2020, OBES) | 변환 회귀·asinh 해석 | 초록 |
| Federal Reserve FEDS Note (2020-12-03), Interest Coverage Ratios | ICR을 변환 없이 임계값·분위 회귀로 다룬 사례(기업 단위) | 웹페이지 |
| Bartram, Brown & Minton (2010, JFE) | 환율 노출의 가격전가·헤지 | 초록 |
| Cinelli, Forney & Pearl (2022) | 좋은 통제와 나쁜 통제 | 초록 |
| Bräuning, Fillat & Joaquim (2023, Boston Fed) | 유동자산과 금리인상 반응 | 초록 |
| 이익노(2006), 한국은행 조사통계월보 76권 8호(2022.8), KIET 산업경제 2021.11, 이서진·유종민(2023) | 산업연관 가격전가모형 원형과 업종별 전가 실증 | 팀 문서 기재 |
