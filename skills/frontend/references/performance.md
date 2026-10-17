# 성능

> 적용 범위: 데모는 "눈에 띄게 느리지 않은가"만 본다. 아래 예산·측정은 **출시 서비스일 때**.

## 1. 예산(Core Web Vitals, 실사용자 75번째 백분위수 기준)
| 지표 | 좋음 | 나쁨 | 주로 무엇이 나쁘게 하나 |
|---|---|---|---|
| LCP(가장 큰 콘텐츠 표시) | ≤ 2.5초 | > 4초 | 느린 서버 응답, 늦게 발견되는 히어로 이미지, 렌더 차단 CSS·폰트, 클라이언트 렌더링 |
| INP(입력 반응) | ≤ 200ms | > 500ms | 긴 JS 작업(>50ms), 큰 리렌더, 하이드레이션 중 클릭 |
| CLS(레이아웃 밀림) | ≤ 0.1 | > 0.25 | 크기 없는 이미지·광고·임베드, 늦게 들어오는 배너, 폰트 교체 |

보조 기준(실험실 측정용, 우리 팀 목표치): TTFB ≤ 0.8초, 첫 화면 JS(압축 후) ≤ 약 200KB [팀 기준. 공식 기준 아님].

**측정은 두 종류를 구분한다.**
- 실험실(Lighthouse, Chrome DevTools Performance): 원인 찾기용. 모바일 + CPU 4배 감속으로 본다. 개발 서버(`next dev`)는 느리고 최적화가 꺼져 있으니 **`next build && next start`로 측정**한다.
- 실사용자(Vercel Speed Insights, `useReportWebVitals`, CrUX): 출시 후 진짜 판정. 실험실 점수 100이어도 실사용 INP가 나쁠 수 있다.

## 2. 렌더링 전략 고르기
| 페이지 | 전략 |
|---|---|
| 모두에게 같고 드물게 바뀜(소개, 문서, 블로그) | 정적(빌드 시 프리렌더) |
| 모두에게 같지만 자주 바뀜(상품 목록) | 캐시 + 시간/태그 재검증(`'use cache'` + `cacheLife`/`cacheTag`) |
| 사람마다 다름(대시보드) | 정적 셸 + 개인 데이터는 `<Suspense>`로 스트리밍 |
| 로그인 뒤 상호작용이 매우 많은 도구(에디터, 캔버스) | 셸만 서버, 본체는 클라이언트(`next/dynamic`) |

Next.js 16 Cache Components에서는 위가 한 페이지 안에서 섞인다(Partial Prerendering). 핵심은 **비동기 작업을 트리 아래쪽으로 내려 정적 셸을 최대화**하는 것.

## 3. 번들
- 분석: `@next/bundle-analyzer` 또는 Turbopack용 분석 명령 [확인 필요: 프로젝트 Next 버전의 명령 이름]. Expo 앱은 Expo Atlas [확인 필요: 현재 SDK에서의 사용법].
- 큰 것이 `'use client'` 파일에 들어가면 그대로 브라우저로 간다. 마크다운 파서, 날짜 라이브러리, 차트, 하이라이터는 서버 컴포넌트에서 쓰거나 `next/dynamic`으로 필요할 때 로드.
- 아이콘 라이브러리는 개별 import(`lucide-react`는 이름 import로 트리셰이킹됨). 배럴 파일(`index.ts`에서 전부 re-export)은 트리셰이킹을 망칠 수 있다. Next.js는 일부 패키지를 `optimizePackageImports`로 처리한다.
- `moment`·`lodash` 전체 import 금지 → `date-fns`/`Intl`, 개별 함수 또는 네이티브.
- 서드파티 스크립트(분석, 채팅 위젯)가 INP의 흔한 범인. `next/script`의 `strategy="lazyOnload"` 또는 `@next/third-parties`.

## 4. 이미지
- 웹은 `next/image`: 크기(`width`/`height` 또는 `fill` + 크기 있는 부모)를 반드시 준다 → CLS 방지.
- **LCP 이미지(첫 화면 히어로)는 우선 로드한다.** Next.js 16 문서 권장: `loading="eager"` 또는 `fetchPriority="high"`(대부분 이것으로 충분), 필요하면 `preload`. `priority`는 16에서 deprecated(15 이하에서는 `priority`). 기본이 lazy라 안 주면 LCP가 늦어진다. 반대로 첫 화면 아래 이미지에 주면 대역폭 낭비.
- Next.js 16부터 `images.qualities` 기본값이 `[75]`다. 다른 `quality`를 쓰려면 `next.config`에 허용 목록을 추가한다(안 하면 가장 가까운 값으로 바뀐다).
- `sizes`를 정확히: `fill`·반응형 이미지에 `sizes`가 없으면 모바일에서도 큰 이미지를 받는다.
- 사용자 업로드 이미지는 업로드 시 리사이즈·WebP/AVIF 변환(서버·스토리지 쪽).
- 앱은 `expo-image`(캐시·placeholder 지원). 원격 이미지는 크기를 고정한다.

## 5. 폰트
- `next/font`로 자체 호스팅: 외부 요청 없음, `size-adjust` 폴백으로 CLS 감소.
- 굵기는 실제 쓰는 것만. 한글 웹폰트는 용량이 커서(전체 글리프 수 MB) 서브셋·가변 폰트·`unicode-range` 분할 버전(예: Pretendard의 dynamic subset)을 쓴다.
- 앱은 `expo-font`, 스플래시를 폰트 로드까지 유지.

## 6. 런타임(INP)
- 입력마다 무거운 계산·필터링 → `useDeferredValue` 또는 `startTransition`으로 긴급하지 않은 업데이트 분리.
- 긴 목록은 가상화(수백 개 이상), 앱은 FlatList 대신 FlashList를 고려.
- 리렌더 원인은 추측하지 말고 React DevTools Profiler("Highlight updates")로 확인.
- 애니메이션은 `transform`/`opacity`만(레이아웃 속성 애니메이션은 매 프레임 레이아웃 계산). 앱은 Reanimated(UI 스레드).

## 7. 네트워크
- 워터폴 제거가 대부분의 LCP 개선이다: 서버에서 병렬로 가져오고(`Promise.all`), 클라이언트 연쇄 요청(A 응답 후 B 요청)을 없앤다.
- `<Link>` 프리페치가 기본으로 동작한다. 수백 개 링크 목록에서는 프리페치 비용도 고려 [버전별 기본값 확인 필요].
- API 응답은 화면에 필요한 필드만. 1MB JSON을 받아 10개만 그리는 경우가 흔하다.

## 흔한 실수
- 개발 서버에서 재고 "느리다"고 판단.
- 모든 컴포넌트에 `useMemo`를 둘러 성능이 좋아졌다고 착각(측정 없음).
- 스켈레톤 크기가 실제 콘텐츠와 달라 로딩 후 CLS 발생.
