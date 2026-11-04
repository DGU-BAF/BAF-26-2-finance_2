# 제조업 40개 업종의 이자 부담은 어떻게 달라졌을까?

ICR(이자보상배율)은 영업이익을 이자비용으로 나눈 값이다. 3배라면 영업이익이 그해 이자비용의 세 배라는 뜻이다. 한 행은 한 업종의 한 해다.

2018~2020년과 2022~2023년을 비교하면 40개 업종 중 38개에서 이자비용이 늘었지만, ICR이 하락한 곳은 24개였다. 이 프로젝트는 **어느 업종에서 무엇이 변했는지**, 그리고 **긴축 전의 단기차입 의존도로 그 차이를 설명할 수 있는지**를 따로 살폈다.

## 처음이라면 이 순서로

1. [06 · 이자비용과 영업이익이 함께 늘어난 업종에서는 무슨 일이 있었을까?](research_inventory_v1/06_cross_chat_verification.ipynb) — 이자와 이익이 함께 증가해도 업종별 결과가 갈렸다는 사실부터 본다.
2. [01 · 단기차입이 많았던 업종은 이자 감당 능력이 더 떨어졌을까?](analysis_v1/01_analysis.ipynb) — 유동성을 함께 고려한 M2에서 예상했던 악화 관계를 확인할 수 있었는지 읽는다.
3. [10 · 반도체 때문에 전체 결과가 달라졌을까?](semiconductor_v1/10_semiconductor.ipynb) — 전체 업종에 대한 추정과 한 업종 내부의 변화를 구분하는 사례다.

## 질문별 분석 노트

- [01 · 단기차입이 많았던 업종은 이자 감당 능력이 더 떨어졌을까?](analysis_v1/01_analysis.ipynb)
- [02 · 긴축기라는 구분 대신 실제 기준금리를 쓰면 어떨까?](rate_model_v1/02_rate_level.ipynb)
- [03 · ICR이 유난히 크거나 작은 여섯 관측치가 결론을 바꿀까?](trim_sensitivity_v1/03_trim_sensitivity.ipynb)
- [04 · 실제 금리 모형의 양의 관계도 여섯 관측치에 민감할까?](rate_trim_v1/04_rate_trim.ipynb)
- [05 · 이자비용이 늘면 상환능력은 항상 떨어질까?](mechanism_v1/05_mechanism.ipynb)
- [06 · 이자비용과 영업이익이 함께 늘어난 업종에서는 무슨 일이 있었을까?](research_inventory_v1/06_cross_chat_verification.ipynb)
- [07 · 만기와 연도를 더 잘게 나누면 놓친 차이가 보일까?](development_v2/07_development.ipynb)
- [08 · 업종별 경기를 비교할 수 있는 자료는 어디까지 있을까?](cycle_input_audit/08_cycle_input_audit.ipynb)
- [09 · 각 업종의 생산·출하 변화를 고려하면 결론이 달라질까?](cycle_control_v1/09_cycle_controls.ipynb)
- [10 · 반도체 때문에 전체 결과가 달라졌을까?](semiconductor_v1/10_semiconductor.ipynb)

각 노트북에 기존 실행 출력이 저장되어 있다. 코드의 # 주석을 따라 읽고, 출력 바로 아래에서 숫자와 그림 해석을 확인할 수 있다.
