# 모바일 앱(React Native + Expo)

> 2026-10 기준 최신 Expo SDK 58(React Native 0.88, React 19.3). SDK 55부터 New Architecture는 끌 수 없다. 프로젝트 SDK 버전을 먼저 보고, 다르면 docs.expo.dev의 해당 버전 문서를 본다. 라이브러리는 `npx expo install <pkg>`로 설치해 SDK와 맞는 버전을 받는다(`npm install`은 버전 불일치의 흔한 원인).

## 1. 개발 환경 선택
| 상황 | 선택 |
|---|---|
| 처음 화면 몇 개 시험, Expo SDK 기본 모듈만 | Expo Go |
| 네이티브 모듈 추가(결제, 소셜 로그인 SDK 등), 출시 예정 | **Development build**(`expo-dev-client`) — 출시 앱과 같은 네이티브 구성 |
| 네이티브 코드 직접 수정 필요 | Config plugin으로 먼저 해결. 안 되면 prebuild(CNG)로 생성한 폴더를 고치지 말고 플러그인을 쓴다 — `ios/`·`android/`를 커밋하고 손으로 고치면 SDK 업그레이드가 매우 비싸진다 |

확인은 iOS 시뮬레이터(이 환경의 시뮬레이터 도구)로, Android 고유 동작(뒤로가기 버튼, 키보드, 그림자)은 Android 에뮬레이터 또는 실기기로 따로 본다. 시뮬레이터는 성능을 대표하지 않는다 — 성능 판단은 실기기 + 릴리스 빌드.

## 2. 내비게이션(Expo Router)
- 파일 기반 라우팅(`app/` 폴더). 웹 Next.js와 사고방식이 비슷하다.
- 구조 예: `app/_layout.tsx`(루트 Stack) → `app/(tabs)/_layout.tsx`(Tabs) → `app/(tabs)/index.tsx`. 모달은 Stack 화면에 `presentation: 'modal'`.
- **인증 분기**: 로그인 여부로 그룹(`(auth)`, `(app)`)을 나누고 루트 레이아웃에서 보호. Expo Router의 보호 라우트(`<Stack.Protected guard={isLoggedIn}>`)를 쓴다(클라이언트 내비게이션 차단일 뿐, 데이터 권한은 서버에서). 화면마다 `useEffect`로 리다이렉트하면 깜빡임과 뒤로가기 버그가 생긴다.
- 딥링크는 라우트 구조가 곧 URL이다. 라우트 이름을 바꾸면 기존 링크(푸시 알림, 공유 링크)가 깨진다.
- 탭 안 스택 상태는 탭을 옮겨도 유지된다. "탭 다시 누르면 맨 위로"는 사용자가 기대하는 동작이니 확인.

## 3. 레이아웃·스타일 함정
- **Safe area**: `react-native-safe-area-context`의 `SafeAreaView`/`useSafeAreaInsets`. 노치·홈 인디케이터·Android 제스처 바에 버튼이 가려지는 것이 1순위 버그.
- **키보드**: 입력 화면은 키보드가 입력·버튼을 가리는지 반드시 확인. `KeyboardAvoidingView`(iOS `behavior="padding"`) 또는 `react-native-keyboard-controller` [확인 필요].
- 웹 CSS와 다르다: 기본 `flexDirection: 'column'`, 상속되는 스타일은 `Text` 안에서만, 모든 텍스트는 `<Text>` 안에. 그림자는 플랫폼별(iOS shadow*, Android elevation, 새 아키텍처는 `boxShadow` 지원 [RN 버전 확인]).
- NativeWind: 2026-10 기준 v4가 안정판, Tailwind v4 기반 v5는 프리릴리스 [확인 필요: 프로젝트에 어느 버전을 쓸지]. 웹 Tailwind 클래스가 전부 동작하지는 않는다(예: 일부 hover·grid). 안 되는 클래스는 `StyleSheet`로.
- 목록은 `ScrollView` + `map` 금지(전부 렌더). `FlatList`, 길거나 무거우면 FlashList. `keyExtractor`에 안정된 ID.
- 다크 모드·글꼴 크기 확대(접근성 설정)에서 깨지는지 확인.

## 4. 데이터·오프라인
| 요구 | 선택 |
|---|---|
| 온라인 전제, 잠깐 끊겨도 마지막 화면은 보여야 함 | TanStack Query + 캐시 영속화(persister) + `onlineManager`를 NetInfo에 연결 |
| 오프라인에서 작성·수정하고 나중에 동기화 | 로컬 DB(`expo-sqlite`, 필요하면 동기화 엔진) + 변경 큐. **충돌 규칙(마지막 쓰기 승리? 서버 우선?)을 먼저 정한다** — 정하지 않으면 데이터가 조용히 사라진다 |
| 작은 설정값(테마, 온보딩 완료) | AsyncStorage 또는 MMKV |
| 토큰·비밀 | `expo-secure-store`(`security.md`) |

- 앱이 백그라운드에서 돌아오면 데이터 갱신(`AppState` → TanStack Query `focusManager`).
- 낙관적 업데이트는 모바일에서 더 중요하다(네트워크가 느리다). 실패 시 롤백 + 알림.
- 오프라인 지원은 비용이 크다. 데모에서는 "오프라인입니다" 배너 + 재시도 버튼으로 충분.

## 5. 빌드·배포·OTA
- **EAS Build**: 클라우드에서 iOS/Android 바이너리. 프로필(`eas.json`)을 `development`/`preview`(내부 테스트)/`production`으로 나눈다.
- **EAS Update(OTA)**: JS·스타일·이미지만 바꿀 수 있다. 네이티브 코드·네이티브 의존성·권한·SDK 버전 변경은 새 빌드 + 스토어 심사가 필요.
  - `runtimeVersion`은 "이 업데이트가 맞는 네이티브 버전"이다. 네이티브가 바뀌었는데 같은 runtimeVersion으로 업데이트를 보내면 빌드에 없는 네이티브 코드를 호출해 에러가 난다(`expo-updates`가 이전 업데이트로 되돌리려 시도하지만 믿지 않는다). 정책 고르기: `appVersion`은 네이티브 변경 시 앱 버전 올리기를 잊으면 사고, `fingerprint`는 네이티브에 영향 주는 변경을 자동 감지해 안전하지만 빌드가 더 자주 필요. **출시 서비스는 `fingerprint` 권장.**
  - 출시 서비스: 채널을 나눠(preview → production) 먼저 내부에서 받고, 점진 배포(rollout 비율)로 내보낸다. 롤백은 이전 안정 업데이트를 다시 게시(republish).
  - 스토어 정책상 OTA로 앱의 주요 목적·기능을 바꾸면 안 된다. 버그 수정·작은 개선용 [각 스토어 최신 가이드라인 확인 필요].
- **버전**: 스토어용 버전(`version`)과 빌드 번호는 EAS의 자동 증가(`autoIncrement`) 사용 권장 [확인 필요].
- **출시 전**: 릴리스 빌드로 실기기 확인(개발 빌드에서는 안 보이는 크래시가 있다), 권한 요청 문구(`infoPlist` 사용 목적 설명 — 비어 있으면 iOS 심사 거절), 크래시 리포팅(Sentry 등), 앱 아이콘·스플래시·개인정보 처리방침 URL.

## 6. 성능
- JS 스레드를 막는 계산(큰 JSON 파싱, 정렬)은 렌더 밖으로. 애니메이션·제스처는 Reanimated + Gesture Handler(UI 스레드).
- 이미지는 `expo-image`(디스크 캐시, 크기 지정).
- 첫 화면: 스플래시를 폰트·인증 확인 끝날 때까지 유지(`expo-splash-screen`)하고, 그동안 필요한 것만 로드.
- 릴리스 빌드에서 측정. 개발 모드는 수 배 느리다.

## 7. 웹과 코드 공유
- 공유할 것: 타입, Zod 스키마, API 클라이언트, 순수 로직, 쿼리 키·훅(TanStack Query는 양쪽에서 동작).
- 공유하지 않을 것: 화면·레이아웃 컴포넌트(DOM vs Native, 내비게이션이 다르다). 억지로 공유하면 양쪽 다 어색해진다.
- 모바일 앱이 쓸 API는 Server Action이 아니라 Route Handler 또는 별도 백엔드(`backend` 스킬)로.
