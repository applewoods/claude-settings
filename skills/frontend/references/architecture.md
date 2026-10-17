# 아키텍처: 구조·경계·데이터·상태

> 기준 버전: Next.js 16.x(App Router), React 19. 2026-10 공식 문서 기준. 프로젝트 버전이 다르면 해당 버전 문서를 다시 확인한다.

## 1. 폴더 구조

**원칙: 기능(feature) 가까이 둔다.** 파일 종류별(`components/`, `hooks/`, `utils/`)로만 나누면 기능 하나 고칠 때 폴더 다섯 개를 돈다.

```
app/                      # 라우팅만. 얇게 유지
  (marketing)/            # 라우트 그룹: URL에 안 나타남, 레이아웃 분리용
  (app)/dashboard/
    page.tsx              # 데이터 읽고 기능 컴포넌트 조립
    loading.tsx  error.tsx
    _components/          # 이 라우트에서만 쓰는 것(_ 접두사 = 라우트 아님)
components/ui/            # shadcn/ui 생성물. 직접 고쳐도 되지만 고친 이유를 주석으로
features/<기능>/          # 기능별: components, actions.ts, queries.ts, schema.ts
lib/                      # 기능과 무관한 공용(유틸, db 클라이언트, auth)
```

| 규모 | 구조 |
|---|---|
| 데모(화면 5개 이하) | `app/` + `components/` + `lib/`로 충분. `features/`는 과하다 |
| 기능이 여러 개, 사람이 둘 이상 | 위처럼 `features/`로 묶는다 |
| 웹+앱 함께 | 모노레포(`apps/web`, `apps/mobile`, `packages/shared`)로 타입·Zod 스키마·API 클라이언트를 공유. UI 컴포넌트는 공유하지 않는 편이 싸다(웹 DOM과 RN 뷰가 달라서) |

흔한 실수
- `lib/utils.ts`가 1000줄이 됨 → 기능에 속하는 함수는 기능 폴더로.
- 서버 전용 코드(DB, 비밀키)를 클라이언트가 import → 서버 전용 모듈 맨 위에 `import 'server-only'`를 둬서 빌드 에러로 막는다.

## 2. 서버/클라이언트 컴포넌트 경계

App Router에서 컴포넌트는 기본이 서버 컴포넌트다. `'use client'`는 **경계 선언**이라, 그 파일이 import하는 모든 것이 클라이언트 번들에 들어간다.

| 필요한 것 | 컴포넌트 |
|---|---|
| DB·비밀키·서버 전용 API, 큰 라이브러리로 렌더(마크다운 파싱 등) | 서버 |
| `useState`·`useEffect`·이벤트 핸들러·브라우저 API(`window`, `localStorage`) | 클라이언트 |
| 둘 다 | 서버가 데이터를 읽고, 상호작용 부분만 클라이언트 자식으로 분리 |

패턴
- **잎에 `'use client'`**: 페이지 전체가 아니라 `LikeButton`, `SearchInput`에만.
- **children으로 서버 컴포넌트를 클라이언트 안에 넣기**: 클라이언트 컴포넌트는 서버 컴포넌트를 import할 수 없지만 `children`/props로 받을 수는 있다. 모달·탭 래퍼에 쓴다.
- **props는 직렬화 가능해야 한다**: 서버→클라이언트로 함수·클래스 인스턴스를 넘길 수 없다(Server Action은 예외). 원시값·평범한 객체·배열·`Date`·`Map`·`Set`·Promise는 넘어간다.
- **서버에서 가져온 데이터를 통째로 넘기지 않는다**: 클라이언트 props는 HTML/RSC 페이로드에 그대로 노출된다. 필요한 필드만 골라 넘긴다(DTO). 비밀번호 해시·내부 ID가 새는 흔한 경로다.

하이드레이션 불일치(콘솔 경고)의 흔한 원인: 렌더 중 `Date.now()`/`Math.random()`, `typeof window` 분기, 브라우저 확장, 잘못된 HTML 중첩(`<p>` 안의 `<div>`). 시간·로케일 의존 값은 클라이언트에서 마운트 후 그리거나 서버에서 고정해 넘긴다.

## 3. 데이터 패칭·캐싱·재검증

### 먼저 확인할 것: 어느 캐시 모델인가
Next.js 16부터 **Cache Components**(`next.config`의 `cacheComponents: true`)가 도입됐고, 2026-10 문서 기준 `create-next-app` 기본값으로 켜져 있다. 켜져 있는지에 따라 규칙이 다르다.

| | Cache Components 켜짐(새 앱 기본) | 꺼짐(이전 모델) |
|---|---|---|
| 기본 동작 | 아무것도 캐시하지 않음. 런타임 데이터는 `<Suspense>` 안에서 스트리밍 | 라우트 단위로 정적/동적 결정, `fetch` 옵션·`export const revalidate`로 제어 |
| 캐시하는 법 | 함수·컴포넌트 맨 위 `'use cache'` + `cacheLife('hours')` + `cacheTag('posts')` | `fetch(url, { next: { revalidate, tags } })`, `unstable_cache` |
| 문서 | nextjs.org/docs/app/getting-started/caching | 같은 문서의 "Previous Model" 가이드 |

### Cache Components에서의 판단 기준
- **모두에게 같은 데이터, 잠깐 오래돼도 됨**(상품 목록, 블로그) → `'use cache'` + `cacheLife` + `cacheTag`. 정적 셸에 들어가 CDN에서 바로 나간다.
- **요청마다 달라야 함**(장바구니, 알림) → 캐시하지 않고 `<Suspense fallback>`으로 감싼다. 감싸지 않으면 개발 오버레이가 blocking-route 경고를 띄운다.
- **쿠키·헤더·`searchParams`를 읽음** → 그 컴포넌트만 `<Suspense>` 안으로. 값을 꺼내 인자로 넘기면 그 아래는 `'use cache'` 가능(인자가 캐시 키가 됨).
- **`await params`를 레이아웃 꼭대기에서 하지 않는다** → 그 레이아웃 전체가 정적 셸에서 빠진다. 쓰는 곳 가까이에서 await.
- `cacheLife`는 항상 명시한다(없으면 `default` 프로필). `seconds` 같은 짧은 수명은 프리렌더에서 빠진다.
- 서버리스에서 `'use cache'` 런타임 캐시는 인스턴스 메모리라 오래 안 남는다. 공유 캐시가 필요하면 `'use cache: remote'`(캐시 핸들러 필요). 배포가 바뀌면 캐시는 새로 시작한다.

### 변경 후 재검증
| 함수 | 어디서 | 동작 | 쓰는 경우 |
|---|---|---|---|
| `updateTag(tag)` | Server Action만 | 즉시 만료 | 사용자가 방금 바꾼 걸 바로 봐야 함(내 글 작성 후 목록) |
| `revalidateTag(tag, 'max')` | Server Action, Route Handler | stale-while-revalidate | 약간 늦어도 됨, CMS 웹훅 |
| `revalidatePath(path)` | 같음 | 경로 전체 무효화 | 태그를 모를 때만. 태그가 더 정밀하다 |

> `revalidateTag`의 두 번째 인자(프로필)는 Next.js 16 문서 기준 권장 형태다. 15 이하 프로젝트는 인자 하나다.

### 요청 중복 제거·워터폴
- 같은 요청 안에서 같은 데이터를 여러 컴포넌트가 읽으면 `React.cache()`로 감싼 함수를 공유한다(ORM 직접 호출은 `fetch`처럼 자동 중복 제거가 안 된다).
- 서로 독립된 요청은 `await` 를 줄줄이 쓰지 말고 `Promise.all` 또는 각각 다른 `<Suspense>`로 병렬화. 순차 await 3개 × 200ms = 600ms.

### 클라이언트 데이터(TanStack Query)
- 쓰는 곳: Expo 앱 전부, 웹의 무한 스크롤·폴링·실시간에 가까운 화면, 클라이언트에서만 아는 조건으로 조회.
- 쿼리 키는 배열로 계층화(`['posts', { status, page }]`)하고 키 팩토리 한 곳에서 만든다. 무효화가 쉬워진다.
- `staleTime` 기본값 0이면 포커스·마운트마다 다시 요청한다. 데이터 성격에 맞게 30초~5분 등으로 정한다.
- 서버 데이터를 Zustand·Context로 복사하지 않는다. 캐시가 두 개가 되면 반드시 어긋난다.

## 4. 상태 관리 선택

순서대로 물어보고 처음 "예"에서 멈춘다.
1. 서버에서 온 데이터인가? → 서버 컴포넌트 / TanStack Query.
2. URL에 있어야 공유·새로고침·뒤로가기가 되나? → `searchParams`(웹), 라우트 파라미터(앱). 타입 안전하게 쓰려면 `nuqs` 같은 도구 [버전 확인 필요].
3. 폼 입력인가? → `useActionState` 또는 React Hook Form.
4. 한 컴포넌트(와 자식 한두 단계)만 쓰나? → `useState`/`useReducer`, props.
5. 멀리 떨어진 여러 컴포넌트가 쓰고 드물게 바뀌나(테마, 로그인 사용자)? → Context.
6. 자주 바뀌고 많은 컴포넌트가 구독하나(에디터, 장바구니 UI)? → Zustand(선택자로 구독해 불필요한 리렌더 방지).

흔한 실수
- Context 값에 매 렌더 새 객체를 넣어 모든 구독자가 리렌더. 값이 자주 바뀌면 Context를 쪼개거나 Zustand로.
- `useEffect(() => setX(f(y)), [y])` → 렌더 중 `const x = f(y)`.
- prop을 state 초기값으로 복사한 뒤 prop이 바뀌어도 반영 안 됨 → 복사하지 말거나, 리셋이 목적이면 `key`를 바꾼다.

## 5. 메모이제이션
- React Compiler가 켜져 있으면(Next.js 16+: `next.config`의 최상위 `reactCompiler: true` + `babel-plugin-react-compiler`, 15는 `experimental.reactCompiler`) `useMemo`/`useCallback`/`memo`를 손으로 거의 쓰지 않는다. 설정해야 켜지고, 빌드가 약간 느려진다.
- 꺼져 있으면: 측정(React DevTools Profiler)해서 느린 곳에만. 미리 다 감싸는 것은 코드만 복잡하게 한다.
