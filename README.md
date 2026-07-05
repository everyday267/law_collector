# 여객자동차 운수사업법 법령 아카이브

법제처 국가법령정보 Open API를 이용하여  
여객자동차 운수사업법 관련 법령·행정규칙·자치법규를  
Markdown 파일로 수집·보관하는 레포지토리입니다.

---

## 디렉토리 구조

```
docs/
  {YYYYMMDD}/       ← 수집 실행일(KST)별 스냅샷 폴더
    README.md       ← 자동 생성 인덱스
    manifest.json   ← 변동 감지 기록 { "일련번호": "시행일자" }
    law/            ← 현행 법령 (법률·시행령·시행규칙)
    admrul/         ← 행정규칙 (훈령·예규·고시)
    ordin/          ← 자치법규 (시·도·시·군·구 조례)
scripts/
  fetch_laws.py     ← 수집 스크립트
  run.sh            ← 원스텝 실행 (수집 + push)
.env.example        ← API 키 설정 템플릿
PRD.md              ← 상세 사양·트러블슈팅·업데이트 가이드
```

---

## 최초 설정 (1회만)

### 1. API 키 발급
1. [open.law.go.kr](https://open.law.go.kr) 접속 → 회원가입
2. OPEN API 신청 → 법령 + 행정규칙 + 자치법규 모두 체크
3. 승인 후 이메일로 OC값(API Key) 수령 (1~2 영업일)

### 2. 레포 클론
```bash
git clone https://github.com/{계정명}/law_collector.git
cd law_collector
```

### 3. API 키 설정
```bash
cp .env.example .env
# .env 파일 열어서 LAW_API_KEY=발급받은키 입력
```

### 4. Python 환경 (최초 1회)
```bash
pip install -r requirements.txt
```

---

## 반기 수집 실행 (매 1월·7월)

```bash
cd law_collector
bash scripts/run.sh
```

한 줄로 수집 → 변동 감지 → push까지 완료됩니다.

---

## 변동 감지 방식

`docs/{YYYYMMDD}/manifest.json`에 `{ "일련번호": "시행일자" }` 형태로 기록 보관.

- **날짜가 바뀌면** 새 날짜 폴더에 항상 전체 수집 (반기별 스냅샷)
- **같은 날 재실행 시**에만 manifest와 비교하여 미변경 건 스킵
- 변경 0건이면 자동으로 push 스킵
- 본문 수집에 실패한 항목은 manifest에 기록되지 않으므로, 같은 날 재실행하면 실패분만 재시도됨

---

## 참고

- 상세 사양, 발생 가능한 오류와 해결 방법, 수정 가이드: [PRD.md](./PRD.md)
- API 출처: [법제처 국가법령정보 공동활용](https://open.law.go.kr)
- API 문의: 02-2109-6446
