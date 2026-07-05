# PRD — 여객자동차 운수사업법 법령 아카이브 (law_collector)

> **문서 목적**: 이 저장소를 처음 보는 개발자·AI가 즉시 구조를 파악하고,
> 트러블슈팅과 기능 업데이트를 신속하게 수행할 수 있도록 하는 단일 참조 문서.
>
> **최종 갱신**: 2026-07-05 (코드 기준 커밋 `44f4c02`)

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
├── README.md                   ← 사용자용 안내 (⚠ §6.1: 일부 내용이 구버전 구조 기준)
├── requirements.txt            ← Python 의존성 (requests 하나뿐)
├── .env.example                ← API 키 템플릿 (LAW_API_KEY)
├── .env                        ← 실제 API 키 (⚠ §6.2: 현재 git에 커밋되어 있음)
├── fetch_laws.log              ← 실행 로그 (git에 커밋됨, run.sh/워크플로우가 함께 커밋)
├── .github/workflows/
│   └── fetch_laws.yml          ← 반기 자동 수집 워크플로우
├── scripts/
│   ├── fetch_laws.py           ← 수집 스크립트 본체 (단일 파일, 외부 의존성 requests뿐)
│   ├── run.sh                  ← 로컬 원스텝 실행 (env 로드 → 수집 → git push)
│   └── admrul_body.txt         ← 과거 디버깅 산출물 (API 원시 응답 확인용, 실행과 무관)
└── docs/                       ← 수집 결과물 (출력 전용 디렉토리)
    ├── README.md               ← 구버전(날짜 폴더 도입 전) 인덱스 잔재
    ├── manifest.json           ← 구버전 manifest 잔재
    ├── law/ admrul/ ordin/     ← 구버전(날짜 폴더 도입 전) 수집 파일 잔재
    └── {YYYYMMDD}/             ← ★ 현행 구조: 수집 실행일별 스냅샷 폴더
        ├── README.md           ← 해당 날짜 인덱스 (자동 생성)
        ├── manifest.json       ← 해당 날짜 변동 감지 기록 { "일련번호": "시행일자" }
        ├── law/                ← 법령 (법률·시행령·시행규칙) *.md
        ├── admrul/             ← 행정규칙 (훈령·예규·고시) *.md
        └── ordin/              ← 자치법규 (조례·규칙) *.md
```

- 2026-07-01 기준 규모: **총 382건** (법령 4 / 행정규칙 7 / 자치법규 371)
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
| `TODAY` | `datetime.now().strftime("%Y%m%d")` | **러너 로컬 시간 기준** (§6.7 주의) |

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

- `safe_filename()`: Windows 금지 문자(`\/:*?"<>|`)를 `_`로 치환, 100자 절단
- 파일명 = 법령명 그대로 (한글, 공백 포함) → GitHub 웹에서는 정상, 일부 도구에서 URL 인코딩 필요

### 4.6 실행 경로 2가지 (로직이 각각 별도 구현임에 주의)

| | 로컬 (`scripts/run.sh`) | GitHub Actions (`fetch_laws.yml`) |
|---|---|---|
| API 키 | `.env` 파일 또는 환경변수 | `secrets.LAW_API_KEY` |
| 트리거 | 수동 | cron `0 0 1 1 *`, `0 0 1 7 *` (UTC) + 수동 dispatch |
| 커밋 조건 | `git status --porcelain docs/` 비어있지 않으면 | `git diff --cached --quiet` 실패하면 |
| 커밋 대상 | `docs/ fetch_laws.log` | `docs/ fetch_laws.log` |
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

## 6. 알려진 이슈 / 코드-문서 불일치 (트러블슈팅 전 필독)

> AI가 이 저장소를 수정할 때 혼란을 일으키는 지점들. **버그처럼 보여도 아래에 해당하면
> 의도된 동작이거나 알려진 잔재이니 문맥을 확인하고 손댈 것.**

### 6.1 README.md가 구버전 구조 기준
루트 `README.md`는 `docs/law/`, `docs/.manifest.json` 등 **날짜 폴더 도입 전** 구조를 설명한다.
현행 구조는 `docs/{YYYYMMDD}/...` + `docs/{YYYYMMDD}/manifest.json`이다 (§2).
`docs/` 바로 아래의 `law/ admrul/ ordin/ manifest.json README.md`는 구버전 잔재.

### 6.2 `.env`(API 키)가 git에 커밋되어 있음 — 보안 이슈
`.gitignore`가 없어서 `.env`가 커밋 `fb2501b`부터 추적 중이다. **수정 시 권장 절차**:
```bash
echo -e ".env\n.DS_Store\nfetch_laws.log\n__pycache__/" > .gitignore
git rm --cached .env
# 키가 이미 공개됐다면 open.law.go.kr에서 키 재발급
```
(과거 이력에서 완전히 지우려면 `git filter-repo` 필요 — 협업자 있으면 조율 필수)

### 6.3 유령 서브모듈 `law_collector` (gitlink)
루트에 `law_collector`라는 mode `160000` 엔트리가 커밋되어 있다 (`.gitmodules` 없음).
과거 중첩 클론 상태에서 `git add .` 하며 들어간 잔재. clone 시 빈 폴더가 생기고,
일부 도구에서 "submodule not initialized" 경고가 난다. 제거: `git rm --cached law_collector`

### 6.4 워크플로우 `force_refresh`가 무의미
`fetch_laws.yml`의 force refresh 스텝은 `docs/law docs/admrul docs/ordin docs/.manifest.json`
(구버전 경로)을 삭제한다. 현행 스크립트는 `docs/{오늘}/`을 쓰므로 **효과 없음**.
같은 날 강제 재수집을 원하면 `rm -rf docs/$(date +%Y%m%d)` 후 재실행하면 된다.

### 6.5 워크플로우의 "exit code 2" 주석은 거짓
`fetch_laws.yml`에 "종료 코드 2 = 변경 없음"이라는 주석과 `exit_code` output이 있으나,
스크립트는 변경 없어도 `sys.exit(0)`이다. `exit_code` output은 아무 데서도 사용되지 않는다.

### 6.6 본문 수집 실패 항목이 manifest에 기록됨 (잠재 버그)
`main()`에서 `new_manifest[mst] = date`를 **본문 수집 시도 전에** 기록한다.
`fetch_body()`가 실패해 파일이 저장되지 않아도, 그날 다른 항목이 1건이라도 변경되면
manifest가 저장된다 → **같은 날 재실행 시 실패 항목이 "미변경"으로 스킵되어 파일이 영구 누락**된다.
- 증상: 인덱스 README에는 있는데 `.md` 파일이 없음 / 로그에 "본문 수집 실패"
- 임시 해결: `docs/{오늘}/manifest.json`에서 해당 일련번호 항목 삭제 후 재실행
- 근본 수정: `new_manifest[mst] = date`를 `save_markdown` 성공 후로 이동

### 6.7 날짜 폴더가 러너 로컬 시간 기준
`TODAY = datetime.now()` — GitHub Actions 러너는 **UTC**이므로 KST 00:00~08:59에 수동 실행하면
폴더 날짜가 한국 기준 전날로 찍힌다. (정기 cron은 00:00 UTC = 09:00 KST라 실질 문제 없음.)
KST 고정이 필요하면 `datetime.now(ZoneInfo("Asia/Seoul"))`로 수정.

### 6.8 동명 법규 파일명 충돌 가능
파일명이 법령명만으로 결정되므로, **지자체가 다른데 조례명이 완전히 같으면** 같은 파일에
덮어써진다 (마지막 수집분만 남음). 인덱스에는 지역명이 표기되지만 파일은 하나다.
수정 시 `safe_filename(item["name"] + ("_" + item["region"] if item["region"] else ""))` 형태 권장.

### 6.9 `fetch_laws.log`가 커밋 대상에 포함됨
매 실행마다 로그가 바뀌어 diff가 발생 → "변경 0건"이어도 로그 때문에 커밋이 생길 수 있고,
로컬/원격 양쪽에서 실행하면 **로그 파일 충돌**이 난다 (과거 커밋 `d831cc4` "로그 충돌 해결"이 그 흔적).
`.gitignore` 처리 권장 (§6.2와 함께).

### 6.10 `run.sh`의 .env 로드 방식 한계
`export $(grep -v '^#' .env | xargs)` — 값에 공백·`#`·따옴표가 있으면 깨진다.
OC값은 보통 영숫자라 실사용 문제는 없지만, .env에 다른 변수를 추가할 때 주의.

### 6.11 `scripts/admrul_body.txt`
과거 디버깅 중 API 원시 응답/에러를 저장해둔 파일. 실행 로직과 무관하며 삭제해도 된다.
(내용 중 `httpsL//` 오타로 인한 `MissingSchema` 트레이스백은 디버깅 흔적일 뿐이다.)

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

§6.6의 잠재 버그. `docs/{오늘}/manifest.json`에서 해당 일련번호를 지우고 재실행하거나,
날짜 폴더 전체를 지우고 전량 재수집.

### 7.5 git push 실패

| 증상 | 원인 | 해결 |
|---|---|---|
| `! [rejected] ... non-fast-forward` | 원격에 다른 커밋 존재 (Actions와 로컬 동시 실행 등) | `git pull --rebase origin main` 후 재푸시. 로그 파일 충돌이면 §6.9 참고 (`.gitignore` 처리로 근본 해결) |
| `fatal: could not read Username` (Actions) | `permissions: contents: write` 누락 또는 보호 브랜치 | 워크플로우 permissions 확인 (현재 설정돼 있음), 브랜치 보호 규칙 확인 |
| run.sh에서 push는 되는데 커밋이 안 됨 | docs/ 밖 파일만 변경됨 | run.sh는 `docs/` 변경만 감지함 — 의도된 동작 |

### 7.6 GitHub Actions 관련

| 증상 | 원인 | 해결 |
|---|---|---|
| 정기 실행이 안 됨 | 저장소 60일 이상 커밋 없으면 GitHub이 schedule 워크플로우 자동 비활성화 | Actions 탭에서 워크플로우 재활성화(Enable). 반기 실행 특성상 발생 가능성 높음 — 주기적 확인 필요 |
| Fetch laws 스텝 빨간불인데 워크플로우는 성공 | `continue-on-error: true` | Step Summary와 `fetch_laws.log` 끝부분 확인 (Summary 스텝이 tail -20을 출력함) |
| Secret 등록했는데 키 인식 안 됨 | Secret 이름 불일치 | 정확히 `LAW_API_KEY`여야 함 |
| force_refresh 해도 전체 재수집 안 됨 | §6.4 — 구버전 경로 삭제라 무의미 | 같은 날 재수집은 해당 날짜 폴더 삭제로 대체 |
| Summary 건수가 0으로 나옴 | Summary 스텝이 구버전 경로(`docs/law` 등)를 셈 | `docs/*/law` 등 날짜 폴더 포함 glob으로 수정 필요 (인지된 불일치) |

### 7.7 파일명·인코딩

| 증상 | 원인 | 해결 |
|---|---|---|
| 같은 이름 조례가 하나만 남음 | §6.8 파일명 충돌 | 파일명에 지역명 포함하도록 수정 |
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
