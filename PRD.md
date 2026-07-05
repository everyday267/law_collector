# PRD — 여객자동차 운수사업법 법령 아카이브 (law_collector)

> **문서 목적**: 이 저장소를 처음 보는 개발자·AI가 즉시 구조를 파악하고,
> 트러블슈팅과 기능 업데이트를 신속하게 수행할 수 있도록 하는 단일 참조 문서.
>
> **최종 갱신**: 2026-07-05 — §6의 이슈 상당수를 이 문서와 같은 PR에서 수정함 (§10 변경 이력 참조)

---

## 1. 프로젝트 개요

### 1.1 목적
법제처 **국가법령정보 Open API**(open.law.go.kr)를 이용해 **여객자동차 운수사업 관련
법령·행정규칙·자치법규**를 주기적으로 수집하여 **Markdown 파일로 아카이브**하는 저장소.

### 1.2 핵심 사용 시나리오
- **반기 1회 자동 수집**: GitHub Actions가 매년 1/1, 7/1 자동 실행 → 변경분 커밋/푸시
- **수동 수집**: 로컬에서 `bash scripts/run.sh` 한 줄 실행 (수집 → 커밋 → 푸시)
- **아카이브 열람**: `docs/{YYYYMMDD}/README.md` 인덱스에서 법령별 Markdown 링크로 탐색

### 1.3 비목표 (Out of Scope)
- 법령 본문의 의미 분석·요약 (원문 보존만 수행)
- 실시간 변경 감지 (반기 스냅샷 방식)
- 데이터베이스 저장 (Git 저장소 자체가 스토리지이자 버전 이력)

---

## 2. 폴더 구조

```
law_collector/
├── PRD.md                      ← 이 문서
├── README.md                   ← 사용자용 안내
├── requirements.txt            ← Python 의존성 (requests 하나뿐)
├── .gitignore                  ← .env / fetch_laws.log / .DS_Store 등 제외
├── .env.example                ← API 키 템플릿 (LAW_API_KEY)
├── .env                        ← 실제 API 키 (로컬 전용, git 미추적)
├── fetch_laws.log              ← 실행 로그 (로컬 전용, git 미추적)
├── .github/workflows/
│   └── fetch_laws.yml          ← 반기 자동 수집 워크플로우
├── scripts/
│   ├── fetch_laws.py           ← 수집 스크립트 본체 (단일 파일, 외부 의존성 requests뿐)
│   └── run.sh                  ← 로컬 원스텝 실행 (env 로드 → 수집 → git push)
└── docs/                       ← 수집 결과물 (출력 전용 디렉토리)
    └── {YYYYMMDD}/             ← 수집 실행일(KST)별 스냅샷 폴더
        ├── README.md           ← 해당 날짜 인덱스 (자동 생성)
        ├── manifest.json       ← 해당 날짜 변동 감지 기록 { "일련번호": "시행일자" }
        ├── law/                ← 법령 (법률·시행령·시행규칙) *.md
        ├── admrul/             ← 행정규칙 (훈령·예규·고시) *.md
        └── ordin/              ← 자치법규 (조례·규칙) *.md
```

- 2026-07-01 기준 규모: **총 382건** (법령 4 / 행정규칙 7 / 자치법규 371)
- 날짜 폴더 도입(`5599d44`) 이전의 구버전 산출물(`docs/law` 등 직속 폴더)은
  2026-07-05 정리됨 — 과거 파일이 필요하면 git 이력에서 복원.
- 날짜 폴더 방식은 커밋 `5599d44`("의도 C - 날짜별 manifest 분리")에서 도입됨.
  **날짜가 바뀌면 무조건 전체 재수집**(새 폴더 생성), **같은 날 재실행 시에만** manifest로 스킵.

---

## 3. 시스템 아키텍처 / 데이터 흐름

```
[SEARCH_KEYWORDS] × [3개 target(law/admrul/ordin)]
        │  lawSearch.do (목록 조회, 페이지네이션 display=100)
        ▼
  전체 목록 수집 → deduplicate() (type+일련번호 기준 중복 제거)
        │
        ▼
  manifest 비교 (docs/{오늘}/manifest.json)
        │  시행일자 동일 → 스킵 / 변경·신규 → 본문 조회
        ▼
  lawService.do (본문 조회, XML)
        │
        ▼
  xml_to_markdown() — 4단계 폴백 파서 (§4.3)
        │
        ▼
  docs/{오늘}/{target}/{법령명}.md 저장
        │
        ▼
  manifest.json 저장 + README.md 인덱스 생성
        │
        ▼
  git add docs/ fetch_laws.log → commit → push
  (run.sh 또는 GitHub Actions — 변경 0건이면 커밋 스킵)
```

---

## 4. 상세 사양

### 4.1 API 사양 (실측 확정값 — 임의로 바꾸지 말 것)

- **Base URL**: `https://www.law.go.kr/DRF`
- **공통 파라미터**: `OC={API_KEY}` (등록 이메일 ID 부분), `type=XML`
- **엔드포인트**:
  - `lawSearch.do` — 목록 검색: `target`, `query`, `display=100`(최대), `page`
  - `lawService.do` — 본문 조회: `target` + 아래 `body_key` 파라미터

`fetch_laws.py`의 `TARGET_META` — **각 target별 XML 태그/파라미터가 서로 다르며, 실제 응답을 확인해 확정한 값**:

| target | 목록 item 태그 | 목록 ID 태그 | 본문 조회 파라미터 | 이름 태그 | 비고 |
|---|---|---|---|---|---|
| `law` (법령) | `law` | `법령일련번호` | `MST` | `법령명한글` | |
| `admrul` (행정규칙) | `admrul` | `행정규칙일련번호` | **`ID`** (MST 아님!) | `행정규칙명` | |
| `ordin` (자치법규) | **`law`** (ordin 아님!) | `자치법규일련번호` | `MST` | `자치법규명` | `지자체기관명` 추가 수집 |

⚠ **주의**: `ordin` 목록 응답의 item 태그가 `law`인 것, `admrul` 본문 파라미터가 `ID`인 것은
API의 실제 동작이다. 과거 이 불일치 때문에 본문 수집이 안 되는 버그가 있었음
(커밋 `57d5335` "본문수집 안되는 문제 해결", `47f711e` "자치법류 파싱문제 수정").

### 4.2 수집 설정 (`fetch_laws.py` 상단 상수)

| 상수 | 값 | 의미 |
|---|---|---|
| `API_KEY` | `os.environ["LAW_API_KEY"]` | 미설정 시 즉시 `KeyError`로 크래시 |
| `SEARCH_KEYWORDS` | `["여객자동차", "노선버스", "준공영제"]` | 키워드 추가 시 여기만 수정 |
| `DELAY_SEC` | 0.5초 | API 호출 간 대기 (과호출 방지) |
| `RETRIES` | 3회 | `ConnectionError`에 한해 2s/4s/6s 백오프 재시도 |
| `TODAY` | `datetime.now(KST).strftime("%Y%m%d")` | **KST 고정** (러너가 UTC여도 한국 날짜) |

### 4.3 XML → Markdown 변환 (`xml_to_markdown`) — 4단계 폴백

법령 유형별로 XML 구조가 달라 순차 폴백으로 파싱한다. **본문이 비는 문제가 생기면
이 4단계 중 어디서 걸리는지부터 확인할 것.**

1. **자치법규 정형**: `<조문>` 컨테이너 하위 `<조>` → `조제목`/`조내용`.
   `조내용`이 "제N장/절"로 시작하면 장·절 헤딩(`###`) 처리, "제N조(제목)" 패턴은 정규식으로 분리.
2. **법령 정형**: `root.iter("조문")` → `조문번호/조문제목/조문내용` + 중첩된 `항→호→목` 계층.
3. **행정규칙 폴백**: `<조문내용>` 통짜 텍스트를 "제N조(제목)" 정규식으로 분할.
4. **최후 폴백**: 위 모두 비면 `기본정보`/이름 태그 제외한 모든 텍스트 노드를 긁어옴.

- 부칙은 별도로 `<부칙>/<부칙내용>` 처리.
- 머리말 메타(법령번호·공포일자·시행일자·지자체)는 `자치법규기본정보` 우선, 이후 공용 태그 폴백.

### 4.4 변동 감지 (manifest)

- 파일: `docs/{YYYYMMDD}/manifest.json`, 형식 `{ "일련번호(mst)": "시행일자(YYYYMMDD)" }`
- 판단: `manifest.get(mst) != new_date` → 변경으로 간주하고 본문 재수집
- **변경 0건이면** `sys.exit(0)`로 종료하며 manifest/인덱스도 안 씀 → git 변경 없음 → 커밋 스킵
- 날짜 폴더가 새로 생기는 날은 manifest가 없으므로 **전량 신규 수집** (설계 의도)

### 4.5 파일명 규칙

- `item_filename()`: `법령명 (지자체명).md` — 지자체가 다른 동명 조례의 덮어쓰기 방지.
  지자체 정보가 없는 법령·행정규칙은 법령명만 사용. 저장과 인덱스 링크가 같은 함수를 씀
- `safe_filename()`: Windows 금지 문자(`\/:*?"<>|`)를 `_`로 치환, 100자 절단
- 한글·공백 포함 파일명 → GitHub 웹에서는 정상, 일부 도구에서 URL 인코딩 필요

### 4.6 실행 경로 2가지 (로직이 각각 별도 구현임에 주의)

| | 로컬 (`scripts/run.sh`) | GitHub Actions (`fetch_laws.yml`) |
|---|---|---|
| API 키 | `.env` 파일 또는 환경변수 | `secrets.LAW_API_KEY` |
| 트리거 | 수동 | cron `0 0 1 1 *`, `0 0 1 7 *` (UTC) + 수동 dispatch |
| 커밋 조건 | `git status --porcelain docs/` 비어있지 않으면 | `git diff --cached --quiet` 실패하면 |
| 커밋 대상 | `docs/` | `docs/` |
| 커밋 메시지 | `chore: 법령 수집 {일시} (변경 N건)` | 동일 형식 |

⚠ 커밋/푸시 로직이 **두 곳에 중복 구현**되어 있으므로 수정 시 양쪽 모두 반영해야 한다.

---

## 5. 실행 방법

### 5.1 최초 설정
```bash
# 1. open.law.go.kr 회원가입 → OPEN API 신청 (법령+행정규칙+자치법규 모두 체크)
#    → 승인 후 OC값(=등록 이메일의 @ 앞부분) 수령
# 2.
cp .env.example .env    # LAW_API_KEY=발급받은키 입력
pip install -r requirements.txt
```

### 5.2 수집 실행
```bash
bash scripts/run.sh          # 수집 + 커밋 + push 원스텝
# 또는 스크립트만:
export LAW_API_KEY=키값
python scripts/fetch_laws.py
```

### 5.3 GitHub Actions
- 저장소 Settings → Secrets → `LAW_API_KEY` 등록 필수
- Actions 탭 → "법령 자동 수집" → Run workflow로 수동 실행 가능
- `force_refresh` 입력값은 현재 실질 동작 안 함 (§6.4)

---

## 6. 알려진 이슈 이력 (2026-07-05 일괄 수정됨)

> 아래 이슈들은 이 문서 최초 작성 시 발견되어 **같은 PR에서 수정 완료**된 것들이다.
> 과거 커밋/날짜 폴더를 다룰 때 참고용으로 남긴다. 미해결 항목은 ⚠ 표시.

### 6.1 ✅ README.md가 구버전 구조 기준 → 갱신됨
루트 `README.md`가 날짜 폴더 도입 전 구조(`docs/law/`, `docs/.manifest.json`)를 설명하고
있었음. 현행 `docs/{YYYYMMDD}/` 구조로 갱신했고, 구버전 산출물 잔재
(`docs/law` `docs/admrul` `docs/ordin` `docs/README.md` `docs/manifest.json`)도 삭제함.
과거 파일은 git 이력(커밋 `44f4c02` 이전)에서 복원 가능.

### 6.2 ✅ `.env`(API 키)가 git에 커밋되어 있음 → 추적 해제됨
`.gitignore`를 추가하고 `git rm --cached .env` 처리함 (로컬 파일은 유지).
⚠ **잔여 조치**: 키가 과거 커밋 이력(`fb2501b`~)에 그대로 남아 있으므로,
저장소가 공개라면 open.law.go.kr에서 **키 재발급 권장**. 이력에서 완전 삭제하려면
`git filter-repo`가 필요하다 (협업자 있으면 조율 필수).

### 6.3 ✅ 유령 서브모듈 `law_collector` (gitlink) → 제거됨
과거 중첩 클론 상태에서 `git add .`로 들어간 mode `160000` 엔트리. `git rm --cached`로 제거함.

### 6.4 ✅ 워크플로우 `force_refresh`가 무의미 → 수정됨
구버전 경로를 삭제하던 스텝을 **오늘(KST) 날짜 폴더 삭제**로 변경 —
이제 force_refresh는 "같은 날 전체 재수집 강제"로 동작한다.

### 6.5 ✅ 워크플로우의 "exit code 2" 주석은 거짓 → 정리됨
스크립트는 변경이 없어도 `sys.exit(0)`이다. 거짓 주석, 사용되지 않는 `exit_code` output,
실패를 가리던 `continue-on-error: true`를 모두 제거함. 이제 수집 실패 시 워크플로우가
빨간불이 되고 커밋 스텝은 실행되지 않는다 (Summary는 `if: always()`라 로그 확인 가능).

### 6.6 ✅ 본문 수집 실패 항목이 manifest에 기록됨 → 수정됨
`new_manifest[mst] = date` 기록을 **저장 성공 후로 이동**함. 이제 본문 수집에 실패한
항목은 manifest에 남지 않아, 같은 날 재실행하면 실패분만 자동 재시도된다.
실패 건수는 `failed_count`로 로그 마지막에 집계된다.
(수정 전 증상: 인덱스에는 있는데 `.md` 파일이 없고 재실행해도 "미변경 스킵"됨 —
구버전 날짜 폴더에서 이 증상을 보면 이 버그가 원인이다.)

### 6.7 ✅ 날짜 폴더가 러너 로컬 시간 기준 → KST 고정
`TODAY`와 인덱스의 수집일시가 `ZoneInfo("Asia/Seoul")` 기준으로 고정됨.
run.sh와 워크플로우의 커밋 타임스탬프도 `TZ=Asia/Seoul`로 통일.

### 6.8 ✅ 동명 법규 파일명 충돌 가능 → 수정됨
`item_filename()` 도입 — 자치법규는 `조례명 (지자체명).md` 형식으로 저장되어
지자체가 다른 동명 조례가 덮어쓰지 않는다. 저장·인덱스 링크가 같은 함수를 사용.
⚠ **주의**: 기존 날짜 폴더(20260701 이전)의 파일명은 지역명이 없는 구형식 그대로다.
다음 수집부터 신형식이 적용되며, 폴더가 날짜별로 분리되므로 충돌은 없다.

### 6.9 ✅ `fetch_laws.log`가 커밋 대상에 포함됨 → 제외됨
run.sh·워크플로우의 `git add`에서 제거하고 `.gitignore` 처리함.
(과거 로컬/원격 동시 실행 시 로그 파일 충돌의 원인이었음 — 커밋 `d831cc4` 참조.)

### 6.10 ✅ `run.sh`의 .env 로드 방식 한계 → 개선됨
`export $(grep ... | xargs)` 방식을 `set -a; source .env; set +a`로 교체 —
값에 공백·특수문자가 있어도 안전하다.

### 6.11 ✅ `scripts/admrul_body.txt` → 삭제됨
과거 디버깅용 API 원시 응답 저장 파일. 실행 로직과 무관하여 삭제함.
API 응답 구조를 확인해야 할 때는 §7.3의 curl 명령을 사용할 것.

---

## 7. 발생 가능한 오류와 해결 방법

### 7.1 실행 즉시 크래시

| 증상 | 원인 | 해결 |
|---|---|---|
| `KeyError: 'LAW_API_KEY'` | 환경변수 미설정 | `.env` 생성 또는 `export LAW_API_KEY=...`. Actions면 Secrets에 `LAW_API_KEY` 등록 |
| `ModuleNotFoundError: requests` | 의존성 미설치 | `pip install -r requirements.txt` |
| `[ERROR] LAW_API_KEY 가 설정되지 않았습니다` (run.sh) | `.env` 파일 없음 | `cp .env.example .env` 후 키 입력 |

### 7.2 수집 결과가 0건 / 비정상적으로 적음

**가장 흔한 원인은 API 키 문제다.** 법제처 API는 키가 무효/미승인이어도 HTTP 200으로
**HTML 에러 페이지**를 반환하는 경우가 있고, 이때 `ET.fromstring`이 실패하면
`api_get()`이 예외를 삼키고 `None`을 반환한다 → 로그에 `API 호출 실패 [lawSearch] ... : syntax error`
같은 워닝만 남고 **스크립트는 정상 종료**한다.

진단 절차:
```bash
# 1. 원시 응답 직접 확인 (XML이 와야 정상, HTML이 오면 키 문제)
curl -s "https://www.law.go.kr/DRF/lawSearch.do?OC=${LAW_API_KEY}&target=law&type=XML&query=여객자동차&display=5" | head -30
```
- HTML/로그인 페이지가 오면 → 키 오타, 미승인, 또는 해당 target(법령/행정규칙/자치법규) **권한 미신청**.
  open.law.go.kr에서 세 가지 모두 신청됐는지 확인 (승인에 1~2 영업일).
- 특정 target만 0건이면 → 그 target 권한만 빠졌거나 `TARGET_META` 태그 불일치 (§4.1).

| 증상 | 원인 | 해결 |
|---|---|---|
| 로그: `API 호출 실패 ... syntax error: line 1` | 응답이 XML 아님(HTML 에러 페이지) | 위 curl로 확인, 키/권한 점검 |
| 로그: `연결 끊김 ... 재시도` 반복 후 `재시도 초과` | 네트워크/서버 불안정 | 잠시 후 재실행. 빈발하면 `DELAY_SEC` 증가(0.5→1.0), `RETRIES` 증가 |
| `requests.exceptions.MissingSchema` | URL 오타 (`https://` 훼손) | `BASE_URL` 확인 |
| 목록은 나오는데 특정 유형만 본문 실패 | `body_key` 불일치 (admrul은 `ID`, 나머지는 `MST`) | §4.1 표 대조. API 스펙 변경 시 원시 XML을 직접 열어 태그 확인 |

### 7.3 본문 `.md` 파일이 비어 있거나 조문이 누락됨

원인: 해당 법령의 XML 구조가 4단계 폴백(§4.3) 어디에도 안 맞음. 과거 자치법규·행정규칙에서
실제 발생 (커밋 `57d5335`, `47f711e`).

진단:
```bash
# 문제 항목의 원시 XML을 받아 구조 확인 (일련번호는 docs/{날짜}/manifest.json 또는 로그에서)
curl -s "https://www.law.go.kr/DRF/lawService.do?OC=${LAW_API_KEY}&target=ordin&type=XML&MST=일련번호" > /tmp/body.xml
# admrul은 MST 대신 ID= 사용!
grep -o "<[^/>]*>" /tmp/body.xml | sort | uniq -c | sort -rn | head -20   # 태그 분포 확인
```
해결: 확인된 태그 구조에 맞춰 `xml_to_markdown()`에 폴백 단계를 추가하거나 기존 단계 수정.
**폴백 순서(자치법규 정형 → 법령 정형 → 행정규칙 통짜 → 최후)를 바꾸지 말고 조건을 좁혀서 추가할 것** —
앞 단계가 잘못 매칭되면 뒤 유형이 전부 깨진다.

### 7.4 "스킵(미변경)"인데 파일이 없음

2026-07-05 이후 코드에서는 발생하지 않는다 (§6.6 수정 — 실패 항목은 manifest에 기록되지 않고
재실행 시 자동 재시도됨). 그래도 발생한다면: `docs/{오늘}/manifest.json`에서 해당 일련번호를
지우고 재실행하거나, 날짜 폴더 전체를 지우고 전량 재수집. 구버전 날짜 폴더(20260701 이전)에서
이 증상이 보이는 것은 수정 전 버그의 흔적이니 정상이다.

### 7.5 git push 실패

| 증상 | 원인 | 해결 |
|---|---|---|
| `! [rejected] ... non-fast-forward` | 원격에 다른 커밋 존재 (Actions와 로컬 동시 실행 등) | `git pull --rebase origin main` 후 재푸시. (`fetch_laws.log`는 이제 커밋되지 않으므로 로그 충돌은 발생하지 않음) |
| `fatal: could not read Username` (Actions) | `permissions: contents: write` 누락 또는 보호 브랜치 | 워크플로우 permissions 확인 (현재 설정돼 있음), 브랜치 보호 규칙 확인 |
| run.sh에서 push는 되는데 커밋이 안 됨 | docs/ 밖 파일만 변경됨 | run.sh는 `docs/` 변경만 감지함 — 의도된 동작 |

### 7.6 GitHub Actions 관련

| 증상 | 원인 | 해결 |
|---|---|---|
| 정기 실행이 안 됨 | 저장소 60일 이상 커밋 없으면 GitHub이 schedule 워크플로우 자동 비활성화 | Actions 탭에서 워크플로우 재활성화(Enable). 반기 실행 특성상 발생 가능성 높음 — 주기적 확인 필요 |
| Fetch laws 스텝 실패로 워크플로우 빨간불 | 수집 중 에러 (키/네트워크/파싱) | Summary 스텝(`if: always()`)의 `fetch_laws.log` tail 확인 후 §7.1~7.3으로 진단. 실패 시 커밋 스텝은 실행되지 않음 (의도된 동작) |
| Secret 등록했는데 키 인식 안 됨 | Secret 이름 불일치 | 정확히 `LAW_API_KEY`여야 함 |
| force_refresh 해도 전체 재수집 안 됨 | (2026-07-05 이전 버전) 구버전 경로 삭제라 무의미했음 | 현재는 오늘(KST) 날짜 폴더를 삭제하도록 수정됨 — 같은 날 전체 재수집 강제로 동작 |
| Summary 건수가 0으로 나옴 | (2026-07-05 이전 버전) 구버전 경로를 집계했음 | 현재는 최신 날짜 폴더(`docs/2*` 중 최신) 기준으로 집계함 |

### 7.7 파일명·인코딩

| 증상 | 원인 | 해결 |
|---|---|---|
| 같은 이름 조례가 하나만 남음 | (2026-07-05 이전 버전) 파일명에 지역명 미포함 | 현재는 `조례명 (지자체명).md` 형식이라 발생하지 않음. 구버전 날짜 폴더에서만 보이는 증상 |
| 파일명에 `？` 같은 전각 특수문자 | API가 반환한 원문 그대로 (safe_filename은 반각만 치환) | 정상. 필요 시 `safe_filename`에 전각 문자 치환 추가 |
| Windows에서 clone 실패/경로 오류 | 한글 장문 파일명 + 경로 260자 제한 | `git config --system core.longpaths true` |
| 한글 깨짐 | 응답 인코딩 | 스크립트는 `resp.encoding="utf-8"` 강제, 파일도 utf-8 저장 — 뷰어 인코딩 확인 |

---

## 8. 업데이트 가이드 (자주 있는 변경 요청별 수정 지점)

| 요청 | 수정 위치 | 방법 |
|---|---|---|
| 검색 키워드 추가/변경 | `fetch_laws.py` → `SEARCH_KEYWORDS` | 리스트에 추가. 중복 항목은 `deduplicate()`가 제거하므로 안전 |
| 수집 주기 변경 | `fetch_laws.yml` → `schedule.cron` | UTC 기준. 예: 분기별 = `"0 0 1 1,4,7,10 *"` |
| 새 법령 유형(target) 추가 | `fetch_laws.py` → `TARGET_META` | **반드시 실제 API 응답으로 item 태그·ID 태그·body_key를 실측**할 것 (§4.1의 함정). `build_index()`의 카테고리 목록에도 추가 |
| API 호출 속도 조정 | `DELAY_SEC`, `RETRIES` | 서버 부하/차단 시 늘림 |
| 출력 형식 변경 | `xml_to_markdown()`, `build_index()` | 폴백 순서 유지 주의 (§7.3) |
| 날짜 폴더 → 단일 폴더 회귀 | `TODAY_DIR` 관련 경로 | 커밋 `5599d44` 이전 방식 참고. README·워크플로우 경로도 함께 수정 |
| 커밋/푸시 동작 변경 | `run.sh` **와** `fetch_laws.yml` 둘 다 | 두 곳에 중복 구현되어 있음 (§4.6) |

### 8.1 수정 후 검증 체크리스트
1. `python scripts/fetch_laws.py` 실행 → `fetch_laws.log`에 ERROR/WARNING 없는지 확인
2. `docs/{오늘}/README.md` 인덱스의 건수·링크가 실제 파일과 일치하는지 확인
3. 유형별 샘플 1건씩(`law`/`admrul`/`ordin`) `.md` 열어 조문 구조가 온전한지 확인
4. 같은 날 재실행 → "미변경 스킵"으로 전량 스킵되고 커밋이 발생하지 않는지 확인

---

## 9. 참고

- API 포털: https://open.law.go.kr (가이드: https://open.law.go.kr/LSO/openApi/guideList.do)
- API 문의: 02-2109-6446
- 주요 이력 커밋: `5599d44`(날짜별 폴더 도입) · `57d5335`(본문 수집 버그 수정) · `47f711e`(자치법규 파싱 수정) · `d831cc4`(로그 충돌)

---

## 10. 변경 이력

### 2026-07-05 — PRD 작성 + 알려진 이슈 일괄 수정

**`scripts/fetch_laws.py`**
- [버그] 본문 수집 실패 항목이 manifest에 기록되어 같은 날 재실행 시 영구 누락되던 문제 수정
  — manifest 기록을 저장 성공 후로 이동, `failed_count` 집계·경고 로그 추가 (§6.6)
- [버그] 동명 조례 파일명 충돌 수정 — `item_filename()` 도입, 자치법규는 `조례명 (지자체명).md` (§6.8)
- [개선] 날짜 폴더·수집일시를 KST(`ZoneInfo("Asia/Seoul")`) 고정 — UTC 러너에서 날짜 어긋남 방지 (§6.7)
- [개선] XML 파싱 실패 시 응답 앞 200자를 로그에 남김 — API 키 무효 시 HTML 응답 진단 용이 (§7.2)

**`scripts/run.sh`**
- [개선] `.env` 로드를 `set -a; source .env; set +a`로 교체 (§6.10)
- [수정] `fetch_laws.log`를 커밋 대상에서 제외 (§6.9), 커밋 타임스탬프 `TZ=Asia/Seoul` 고정

**`.github/workflows/fetch_laws.yml`**
- [수정] `force_refresh`가 오늘(KST) 날짜 폴더를 삭제하도록 변경 — 실제로 동작하게 됨 (§6.4)
- [수정] 거짓 "exit code 2" 주석, 미사용 `exit_code` output, `continue-on-error` 제거 (§6.5)
- [수정] `fetch_laws.log` 커밋 제외, Summary 집계를 최신 날짜 폴더 기준으로 변경

**저장소 정리**
- [보안] `.gitignore` 추가, `.env` git 추적 해제 (⚠ 과거 이력에 키 잔존 — 재발급 권장, §6.2)
- [정리] 유령 서브모듈 `law_collector` gitlink 제거 (§6.3)
- [정리] `fetch_laws.log`, `.DS_Store` 추적 해제, `scripts/admrul_body.txt` 삭제 (§6.11)
- [정리] 구버전 산출물(`docs/law` `docs/admrul` `docs/ordin` `docs/README.md` `docs/manifest.json`) 삭제
  — 현행 `docs/{YYYYMMDD}/` 구조로 일원화, 과거 파일은 git 이력에서 복원 가능 (§6.1)
- [문서] `README.md`를 현행 날짜 폴더 구조로 갱신, `PRD.md`(이 문서) 신규 작성
