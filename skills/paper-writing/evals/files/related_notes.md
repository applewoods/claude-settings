# 관련연구 메모 (내가 읽고 정리한 것)

- [P1] Lee et al., 2021, IEEE JBHI — 허리 착용 IMU, 임계값 + SVM. SisFall에서 평가. 일상생활 오경보는 보고 안 함.
- [P2] Gomez and Ruiz, 2022, Sensors — 손목 가속도계, CNN-LSTM 지도학습. SisFall, MobiAct. 피험자 단위 분할 안 하고 무작위 분할.
- [P3] Chen et al., 2023, UbiComp — 스마트폰 IMU로 활동 인식(HAR)에 SimCLR식 대조 학습 사전학습. 낙상은 다루지 않음.
- [P4] Novak et al., 2023, Pervasive Health — 손목 가속도계, 오토인코더 기반 이상 탐지로 낙상 검출. 레이블 적게 씀. 오경보 24시간 기준 보고.
- [P5] Tanaka and Ito, 2024, IMWUT — 여러 착용 위치(허리·손목·발목) IMU에 masked autoencoder 사전학습, HAR 벤치마크. 낙상은 부록에 소규모 실험만.

우리 논문: 손목 가속도계 + 대조 학습 사전학습 + 선형 헤드, 피험자 단위 분할, 일상생활 오경보 평가.
