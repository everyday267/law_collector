# 여객자동차 운수사업법 법령 아카이브

법제처 국가법령정보 Open API를 이용하여  
**여객자동차 운수사업법** 관련 법령·행정규칙·자치법규를  
Markdown 파일로 자동 수집·보관하는 레포지토리입니다.

---

## 디렉토리 구조

```
docs/
  README.md          ← 자동 생성 인덱스 (법령 목록 + 링크)
  law/               ← 현행 법령 (법률·시행령·시행규칙)
  admrul/            ← 행정규칙 (훈령·예규·고시)
  ordin/             ← 자치법규 (시·도·시·군·구 조례)
scripts/
  fetch_laws.py      ← 수집 스크립트
.github/workflows/
  fetch_laws.yml     ← GitHub Actions (주 1회 자동 실행)
```

---

## 수집 대상

| 계층 | 예시 |
|---|---|
| 법률·시행령·시행규칙 | 여객자동차 운수사업법, 동 시행령/시행규칙 |
| 행정규칙 | 여객자동차 유가보조금 지급지침, 운임요율 조정요령 등 |
| 자치법규 | 전국 시·도·시·군·구 노선버스·여객운수 관련 조례 |

검색 키워드: `여객자동차`, `노선버스`, `준공영제`

---

## 설정 방법

### 1. API 키 발급

1. [국가법령정보 공동활용](https://open.law.go.kr) 접속
2. 회원가입 → **OPEN API 신청** (법령 + 행정규칙 + 자치법규 모두 신청)
3. 승인 후 **OC값(API Key)** 수령 (통상 1~2 영업일)

### 2. GitHub Secret 등록

```
레포지토리 → Settings → Secrets and variables → Actions
→ New repository secret
  Name:  LAW_API_KEY
  Value: (발급받은 OC값)
```

### 3. Actions 권한 설정

```
레포지토리 → Settings → Actions → General
→ Workflow permissions: Read and write permissions ✓
```

### 4. 최초 실행

```
Actions 탭 → 법령 자동 수집 → Run workflow → Run workflow
```

---

## 로컬 실행 (선택)

```bash
git clone https://github.com/{your-org}/law-collector.git
cd law-collector
pip install -r requirements.txt

# .env 또는 직접 export
export LAW_API_KEY="your_api_key_here"

python scripts/fetch_laws.py
```

---

## 자동 갱신 일정

- **반기 1회 (1월 1일 / 7월 1일 오전 9시 KST)** 자동 실행
- 이미 수집된 파일은 스킵 → **증분 수집** (변경된 법령만 업데이트)
- 전체 재수집이 필요한 경우: `Run workflow → force_refresh: true`

---

## 수집 결과 확인

수집 후 `docs/README.md`에서 전체 목록 및 각 법령 링크를 확인할 수 있습니다.

---

## 참고

- API 출처: [법제처 국가법령정보 공동활용](https://open.law.go.kr)
- 법령 저작권: 법제처 (공공저작물 자유이용허락)
- 문의: 법제처 Open API 이용문의 02-2109-6446

---

## 변동 감지 방식

```
docs/.manifest.json
  └── { "법령MST": "시행일자", ... }
```

- 수집 실행 시 API에서 받은 **시행일자**를 이전 기록과 비교
- 시행일자가 동일하면 본문 재수집 **스킵** → 파일 미수정 → 커밋 없음
- 시행일자가 달라진 건(개정) 또는 신규 건만 본문 재수집
- 이력은 `.manifest.json`에 자동 누적 (git 추적)
