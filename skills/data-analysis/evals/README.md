# data-analysis 평가 사례

- `evals.json`: 평가 사례. `set` 필드로 구분한다.
  - v1 (2026-10-19): 기본 함정(의사반복, 누수, 모델 비교, 결측). 기본 통계 지식만으로도 대부분 통과 → 기준선 측정용으로 보존.
  - v2 (2026-10-19): 사용자 압박과 스킬 고유 규칙(2단계 정규성 검정 금지, 다중 비교 보정, 튜닝 공정성·중첩 CV, 쌍체 비교 요구, 보고 형식)을 시험.
- `files/`: 입력 데이터. **모두 `make_eval_data.py`로 만든 합성 데이터다**(시드 고정, 표준 라이브러리만 사용). `model_summary.md`는 손으로 쓴 가상 표.
- 실행: `python3 make_eval_data.py` (이미 있는 파일은 건너뜀). 분석 실행 환경은 `~/claude-settings/.eval-venv`.
- 실행 결과는 저장소 밖 `~/claude-settings/eval-workspace/`(git 제외)에 쌓인다.
