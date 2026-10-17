# 테스트

## 1. 무엇을 얼마나
**원칙: 사용자가 겪는 동작을 테스트한다. 구현 세부(상태 이름, 내부 함수 호출 횟수)를 테스트하면 리팩터링할 때마다 깨지고 버그는 못 잡는다.**

| 층 | 대상 | 도구 | 데모 | 출시 |
|---|---|---|---|---|
| 정적 | 타입, 린트 | `tsc --noEmit`, ESLint(+ `jsx-a11y`) | 필수 | 필수(CI) |
| 단위 | 순수 함수: 검증 스키마, 포맷터, 계산, 리듀서 | Vitest(웹), Jest(Expo 기본) | 복잡한 로직만 | 필수 |
| 컴포넌트 | 상호작용 있는 컴포넌트: 폼, 필터, 조건부 렌더 | Testing Library(`@testing-library/react`, RN은 `@testing-library/react-native`) | 선택 | 핵심 컴포넌트 |
| E2E | 돈·데이터가 걸린 핵심 흐름 3~10개: 가입·로그인, 결제, 핵심 생성·수정 | Playwright(웹), Maestro(앱) [앱 E2E 도구는 확인 필요] | 수동 확인으로 대체 | 필수(CI) |
| 시각 회귀 | 디자인 시스템 컴포넌트 | Playwright 스크린샷, Storybook+Chromatic | 불필요 | 디자인 시스템이 있을 때만 |

비율보다 **"이 테스트가 없으면 어떤 버그가 출시되나"**로 판단한다. 대답이 없으면 쓰지 않는다.

## 2. 서버 컴포넌트·Server Action 테스트
- **async 서버 컴포넌트는 Vitest/Jest 컴포넌트 테스트로 렌더하기 어렵다**(Next.js 문서도 E2E를 권한다). → 데이터 함수·Server Action 로직은 단위 테스트, 렌더링 결과는 E2E.
- Server Action은 `FormData`를 만들어 직접 호출해 단위 테스트할 수 있다. 인증·DB는 의존성 주입이나 모듈 모킹.

## 3. 좋은 테스트 쓰는 법
- 쿼리 우선순위: `getByRole`(이름 포함) > `getByLabelText` > `getByText` > `getByTestId`. Role로 못 찾으면 접근성 문제일 가능성이 크다.
- 사용자 조작은 `userEvent`(`fireEvent`보다 실제에 가깝다). `await user.click(...)`.
- 비동기는 `findBy*`/`waitFor`. 임의의 `sleep`은 느리고 불안정하다.
- 네트워크 모킹은 MSW(Mock Service Worker)로 HTTP 수준에서 — fetch 함수를 직접 모킹하는 것보다 실제와 가깝고 테스트·개발·스토리북에서 재사용된다.
- 4가지 상태(로딩·빈·에러·성공)를 각각 한 번씩.
- **버그를 고칠 때는 먼저 그 버그로 실패하는 테스트를 쓰고 고친다.** 재발 방지의 가장 싼 방법.

## 4. Playwright E2E 기준
- 선택자는 `getByRole`/`getByLabel`. CSS 클래스·DOM 구조 선택자는 Tailwind 클래스만 바꿔도 깨진다.
- 자동 대기(web-first assertion: `await expect(locator).toBeVisible()`)를 쓰고 `waitForTimeout`은 쓰지 않는다.
- 로그인은 매 테스트마다 UI로 하지 않는다: 셋업 단계에서 한 번 로그인해 `storageState`를 저장하고 재사용.
- 테스트끼리 데이터를 공유하지 않는다(각자 만들고 지운다). 순서 의존 테스트는 병렬 실행 시 깨진다.
- 모바일 뷰포트 프로젝트(예: iPhone 기기 프리셋)를 하나 넣는다 — 모바일 우선 원칙의 자동 확인.
- 개발 서버가 아니라 빌드 결과(`next build && next start`)로 돌린다(CI). 개발 모드에만 있는 동작 차이 때문.
- 불안정한(flaky) 테스트는 재시도로 덮지 말고 원인(경쟁 상태, 공유 데이터, 고정 대기)을 고친다.

## 5. 흔한 실수
- 스냅샷 테스트를 대량으로: 아무도 diff를 읽지 않고 `-u`로 갱신한다. 작은 직렬화 값에만.
- shadcn/ui·라이브러리 자체를 테스트: 남의 코드다. 내 조합·조건만.
- 커버리지 숫자를 목표로: 80%를 채우려 쓴 테스트는 대부분 의미 없다. 핵심 경로 커버를 본다.
- 모킹을 너무 많이 해서 테스트가 모킹만 검증.

## 6. 최소 설정(새 프로젝트, 출시 예정)
1. `tsc --noEmit` + ESLint를 CI에.
2. Vitest + Testing Library + MSW (Expo는 `jest-expo` 프리셋 [SDK 버전별 확인]).
3. Playwright, 핵심 흐름 3개부터, 데스크톱 + 모바일 뷰포트.
4. PR마다 위 세 가지가 통과해야 머지.
