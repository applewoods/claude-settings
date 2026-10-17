# 폼·변경·낙관적 업데이트·에러 처리

## 1. 폼 도구 고르기
| 폼 | 선택 | 이유 |
|---|---|---|
| 필드 1~5개, 서버 검증으로 충분(로그인, 댓글) | `<form action={serverAction}>` + `useActionState` + `useFormStatus` | JS 로드 전에도 제출됨(점진적 향상), 코드 최소 |
| 필드 많음, 필드 간 의존, 실시간 검증, 동적 배열(주소 여러 개) | React Hook Form + Zod(`zodResolver`) | 비제어 입력이라 리렌더가 적고 검증 규칙을 선언적으로 |
| 여러 단계(위저드) | React Hook Form, 단계별 스키마 + 최종 스키마 | 단계 이동 시 값 유지 |
| Expo 앱 | React Hook Form + Zod (`Controller`로 RN 입력 연결) | RN에는 `<form action>`이 없다 |

**Zod 스키마 하나를 클라이언트·서버가 공유한다.** 클라이언트 검증은 UX용, 서버의 `schema.safeParse(...)`가 진짜 검증이다. (예시는 Zod 4 문법. Zod 3은 `parsed.error.flatten()`.) 서버에서 다시 검증하지 않으면 개발자 도구로 그냥 우회된다.

## 2. Server Action 작성 규칙
```ts
'use server'
export async function updateProfile(prev: State, formData: FormData): Promise<State> {
  const session = await getSession()            // 1. 인증: 매번 여기서 확인
  if (!session) return { error: '로그인이 필요합니다' }
  const parsed = ProfileSchema.safeParse(Object.fromEntries(formData)) // 2. 검증
  if (!parsed.success) return { fieldErrors: z.flattenError(parsed.error).fieldErrors, values: Object.fromEntries(formData) }
  // 3. 권한: 이 사용자가 이 리소스를 바꿀 수 있나 (id를 폼에서 받았다면 특히)
  await db.profile.update(...)
  updateTag(`profile:${session.userId}`)        // 4. 재검증
  return { ok: true }
}
```
- **Server Action은 공개 POST 엔드포인트다.** 페이지에 버튼이 안 보여도 누구나 호출할 수 있다. 인증·권한을 액션 안에서 확인한다. `proxy.ts`(구 middleware)만 믿지 않는다 — 공식 문서도 같은 경고를 한다.
- **예상된 실패(검증 실패, 중복 이메일)는 throw하지 말고 값으로 반환**해 폼에 표시한다. throw는 예상 못 한 에러용이고 에러 경계로 간다.
- 실패 시 사용자가 입력한 값을 돌려줘 다시 채운다. 다 지워지는 폼은 이탈의 주된 원인이다.
- `redirect()`는 내부적으로 throw하므로 `try/catch` 안에서 부르지 않는다(잡혀서 동작 안 함).

## 3. 제출 UX 체크
- 제출 중 버튼 비활성화 + 진행 표시(`useFormStatus().pending` 또는 `isSubmitting`). 중복 결제·중복 글의 원인.
- 에러 메시지는 필드 옆에, `aria-describedby`로 입력과 연결, 첫 에러 필드로 포커스 이동.
- 검증 시점: 처음엔 blur 또는 submit 때, 에러가 난 뒤에는 입력할 때마다(React Hook Form `mode: 'onTouched'` 등). 첫 글자부터 빨간 에러는 짜증을 낸다.
- 모바일: 알맞은 `type`/`inputMode`/`autoComplete`(`email`, `tel`, `one-time-code`)를 지정. 키보드가 바뀌고 자동완성이 된다.

## 4. 낙관적 업데이트
**언제 쓰나:** 성공 확률이 매우 높고, 되돌려도 사용자가 이해하는 작은 동작(좋아요, 체크, 순서 변경, 채팅 전송).
**쓰지 않는다:** 결제, 삭제(되돌리기 UI 없이), 서버가 값을 계산해 주는 것(재고, 가격), 실패가 잦은 것.

| 환경 | 방법 |
|---|---|
| 웹 + Server Action | `useOptimistic` — 액션이 끝나면 자동으로 실제 값으로 돌아간다 |
| TanStack Query | `onMutate`에서 `cancelQueries` → 이전 값 저장 → `setQueryData`, `onError`에서 복원, `onSettled`에서 `invalidateQueries` |

흔한 실수: 실패 시 롤백만 하고 사용자에게 알리지 않음 → 토스트로 "저장하지 못했습니다, 다시 시도" 표시. `cancelQueries`를 빼먹어 진행 중이던 재조회가 낙관적 값을 덮어씀.

## 5. 에러 경계
| 범위 | 도구 |
|---|---|
| 라우트 세그먼트 | `error.tsx`(클라이언트 컴포넌트). 루트 레이아웃 에러는 `global-error.tsx` |
| 컴포넌트 일부(위젯 하나가 실패해도 페이지는 살림) | Next.js 16.3+ `catchError`(`next/error`), 그 이하 버전은 `react-error-boundary` |
| 404 | `notFound()` + `not-found.tsx` |
| Expo Router | 라우트 파일에서 `ErrorBoundary` export [확인 필요: 현재 SDK 문서] |

- 복구 버튼은 `retry()`(다시 가져와 렌더)를 쓴다. `reset()`은 다시 가져오지 않아 서버 컴포넌트 에러는 못 고친다(Next.js 16.3 문서).
- 에러 경계는 **이벤트 핸들러·비동기 콜백의 에러를 잡지 못한다.** 그건 try/catch로 잡아 상태로 표시한다.
- 사용자에게는 무엇이 안 됐고 무엇을 하면 되는지를, 개발자에게는 로그(출시 서비스면 Sentry 등)를. 스택 트레이스를 화면에 보이지 않는다.
- 경계는 "실패해도 나머지가 쓸 만한 단위"로 둔다. 너무 위(앱 전체 하나)면 위젯 하나 실패에 화면 전체가 사라지고, 너무 잘게면 코드만 늘어난다.

## 6. 목록·페이지네이션·검색
- 검색 입력은 디바운스(200~300ms) 후 URL `searchParams`를 갱신 → 서버가 결과 렌더. 이전 요청 결과가 늦게 와서 덮어쓰는 경쟁 상태를 막는다(TanStack Query는 키가 달라 자동 해결, 직접 fetch면 `AbortController`).
- 커서 기반 페이지네이션이 오프셋보다 무한 스크롤에 맞다(중간 삽입 시 중복·누락 없음). API 설계는 `backend` 스킬.
- 빈 상태는 "결과 없음"과 "아직 데이터 없음(첫 사용)"을 구분해 다른 안내를 준다.
