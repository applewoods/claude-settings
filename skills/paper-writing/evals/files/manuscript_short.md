# FallNet: Contrastive Pretraining for Wrist-Worn Fall Detection

## Abstract
We propose FallNet, a contrastive pretraining framework for wrist-worn fall detection. FallNet significantly outperforms CNN-LSTM on SisFall and MobiAct, achieving 0.893 and 0.851 Macro-F1, and reduces false alarms by 15% in daily living. FallNet is the first self-supervised fall detector and can run on commodity smartwatches.

## 1. Introduction
Falls are a major cause of injury among older adults. Existing detectors rely on thresholds and produce many false alarms. We propose FallNet, which pretrains an encoder with a contrastive objective on wrist accelerometer data. Our contributions are: (1) a contrastive pretraining module, (2) a subject-wise negative sampling strategy, and (3) a lightweight linear head.

## 4. Results
Table 2 shows that FallNet outperforms CNN-LSTM on both datasets (SisFall 0.893 vs 0.861; MobiAct 0.845 vs 0.832). This is because contrastive pretraining learns user-invariant features. Table 3 shows false alarms decreased from 4.1 to 3.7 per 24 h. Table 4 shows that removing contrastive pretraining drops performance to 0.802.

## 5. Limitations
In future work, we will collect more data and test on more devices.

## Notes to self
- Venue: IEEE Sensors Journal, deadline tomorrow
- 영어 문장 일부는 ChatGPT로 다듬음
