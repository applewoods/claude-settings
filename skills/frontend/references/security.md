# 프론트엔드 보안

> 서버 쪽(인증 구현, 세션 저장, API 권한, CORS 설계)은 `backend` 스킬, DB 권한·RLS는 `database` 스킬. 여기는 브라우저·앱·Next.js 경계에서 프론트엔드가 책임지는 것.

## 0. 데모에도 지키는 최소선
- 비밀값(API 키, DB URL, 서비스 롤 키)을 **클라이언트 번들에 넣지 않는다.** `NEXT_PUBLIC_*`, `EXPO_PUBLIC_*` 접두사 변수는 빌드 결과에 문자열로 박혀 **누구나 볼 수 있다.** 앱 바이너리도 풀면 보인다.
- 권한 확인은 서버에서. 버튼을 숨기는 것은 보안이 아니다.
- `dangerouslySetInnerHTML`에 사용자 입력을 그대로 넣지 않는다.

## 1. XSS
React는 `{text}`를 자동 이스케이프한다. 구멍은 이스케이프를 우회하는 곳에 있다.
| 위험 지점 | 대책 |
|---|---|
| `dangerouslySetInnerHTML` | 꼭 필요하면 DOMPurify(서버면 `isomorphic-dompurify` 등)로 정제. 마크다운은 HTML 허용을 끈 렌더러(react-markdown 기본값) |
| `href={userUrl}` | `javascript:` URL이 실행된다. `http(s):`/`mailto:`만 허용하도록 검사 |
| 사용자 입력이 들어간 `<script>`·JSON-LD | `JSON.stringify(data).replace(/</g, '\\u003c')` — `<`를 6글자 시퀀스 `\u003c`(역슬래시 u 0 0 3 c)로 바꿔 `</script>`로 태그를 닫지 못하게 한다 |
| `eval`, `new Function`, `setTimeout(string)` | 쓰지 않는다 |
| 서드파티 스크립트 | 그 스크립트는 페이지 권한 전체를 가진다. 필요한 것만, 가능하면 SRI·CSP로 제한 |

## 2. 인증 토큰 보관
| 환경 | 권장 | 이유 / 피할 것 |
|---|---|---|
| 웹(Next.js) | **`HttpOnly; Secure; SameSite=Lax`(또는 `Strict`) 쿠키**에 세션 ID 또는 토큰 | JS가 못 읽으므로 XSS로 토큰을 훔칠 수 없다. `localStorage`에 액세스·리프레시 토큰 저장은 XSS 한 번에 탈취된다 |
| 웹, 외부 API가 Bearer 토큰을 요구 | 토큰은 서버(Route Handler/Server Action)에 두고 프록시(BFF 패턴) | 브라우저에 토큰을 내리지 않는다 |
| Expo 앱 | **`expo-secure-store`**(iOS Keychain, Android Keystore) | `AsyncStorage`는 암호화되지 않는다. Expo는 크기 제한을 강제하지 않지만 일부 iOS 버전이 약 2048바이트 넘는 값을 거부한 적이 있다(공식 문서) — 큰 값은 넣지 말고 쓰기 실패를 `try/catch` |
| 앱의 리프레시 토큰 | SecureStore + 짧은 액세스 토큰(메모리) | 동시 401 시 갱신 요청이 여러 번 나가지 않게 한 번만(단일 Promise 공유) |

- 쿠키 기반이면 **CSRF**를 생각한다. Server Action은 Origin 헤더를 Host와 비교하는 보호가 있다(Next.js 문서). 직접 만든 Route Handler의 POST는 `SameSite` 쿠키 + Origin 확인 또는 CSRF 토큰.
- 로그아웃 시 서버 세션 무효화 + 쿠키 삭제 + 클라이언트 캐시(TanStack Query `queryClient.clear()`) 비우기. 공용 기기에서 이전 사용자 데이터가 보이는 사고가 흔하다.
- 인증 라이브러리를 직접 만들지 않는다. 선택은 `backend` 스킬.

## 3. Next.js 경계
- **Server Action·Route Handler마다 인증·권한을 다시 확인.** `proxy.ts`(16 이전 `middleware.ts`)는 matcher가 바뀌거나 액션이 다른 라우트로 옮겨지면 조용히 빠진다(공식 문서 경고). proxy는 "로그인 안 됐으면 리다이렉트" 같은 빠른 1차 처리용.
- 데이터 접근을 한 곳(DAL, Data Access Layer: `lib/dal.ts`)에 모으고 거기서 권한을 확인하면 빠뜨리기 어렵다.
- 서버 전용 모듈에 `import 'server-only'`. 클라이언트가 import하면 빌드가 실패해 비밀이 새지 않는다.
- 클라이언트 컴포넌트로 넘기는 props = 공개 데이터. DB 행을 통째로 넘기지 않는다.
- Server Action 인자로 받은 ID는 사용자가 바꿀 수 있다. "이 ID의 소유자가 현재 사용자인가"를 확인(IDOR 방지).
- 오픈 리다이렉트: `?next=` 같은 리다이렉트 대상은 문자열 검사(`/`로 시작, `//` 아님)만으로는 부족하다 — `/\evil.com`은 브라우저가 `//evil.com`으로 해석해 외부로 나간다. `new URL(next, 내사이트origin)`으로 파싱해 `url.origin === 내사이트origin`인지 비교하고, 통과하면 `url.pathname + url.search`만 쓴다.

## 4. 보안 헤더·CSP (출시 서비스일 때)
| 헤더 | 값(출발점) |
|---|---|
| `Content-Security-Policy` | 아래 참고 |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload`(HTTPS 확정 후) |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | 안 쓰는 기능 끄기: `camera=(), microphone=(), geolocation=()` |
| `frame-ancestors`(CSP) | `'none'` 또는 `'self'` — 클릭재킹 방지(`X-Frame-Options` 대체) |

CSP 판단 기준
- **정적 헤더 CSP**(`next.config`의 `headers()`): 설정이 쉽고 정적 렌더링을 유지. 하지만 Next.js 인라인 스크립트 때문에 `script-src`에 `'unsafe-inline'`이 필요해 XSS 방어력이 약하다.
- **nonce 기반 CSP**(proxy에서 요청마다 nonce 생성): 강력하지만 **모든 페이지가 동적 렌더링**이 되고 CDN 캐시를 못 쓴다. 민감한 서비스(결제, 의료, 관리자)에서.
- 처음엔 `Content-Security-Policy-Report-Only`로 깨지는 곳을 모은 뒤 적용한다. 분석·지도·결제 SDK 도메인을 빠뜨려 운영에서 기능이 죽는 일이 흔하다.
- 구체 설정은 Next.js 문서의 Content Security Policy 가이드를 프로젝트 버전에 맞게 확인.

## 5. 의존성·공급망
- `npm audit`/`pnpm audit`는 출시 전과 정기적으로. 경고를 다 고치려 하지 말고 **런타임(프로덕션 의존성)에 있는 high/critical**부터.
- 새 패키지 추가 전: 주간 다운로드, 마지막 배포일, 유지보수자 수, 이름 오타 사기(typosquatting) 확인.
- lockfile을 커밋하고 CI는 `npm ci`/`pnpm install --frozen-lockfile`.
- Next.js·React 보안 공지는 빠르게 패치한다(프레임워크 자체 취약점이 실제로 나왔다 [필요하면 최신 공지 확인]).

## 6. 앱(Expo) 고유
- 딥링크로 들어온 파라미터는 사용자 입력으로 취급(검증 후 사용). 인증 콜백은 가능하면 Universal Links/App Links.
- 로그에 토큰·개인정보를 찍지 않는다(출시 빌드에서 `console.log` 제거 또는 로거 레벨).
- OTA 업데이트(EAS Update)도 코드 배포다. 업데이트 서명(code signing)은 출시 서비스에서 고려 [확인 필요: EAS 문서].
