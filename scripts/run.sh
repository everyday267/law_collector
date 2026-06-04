#!/bin/bash
# =============================================
# 법령 수집 → GitHub push 원스텝 실행 스크립트
# 사용법: bash scripts/run.sh
# =============================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# ── 1. API 키 확인 ─────────────────────────
if [ -z "$LAW_API_KEY" ]; then
  if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
    echo "[INFO] .env 에서 API 키 로드"
  else
    echo "[ERROR] LAW_API_KEY 가 설정되지 않았습니다."
    echo "        .env 파일을 만들거나 export LAW_API_KEY=your_key 를 실행하세요."
    exit 1
  fi
fi

# ── 2. Python 의존성 확인 ───────────────────
echo "[INFO] 의존성 확인 중..."
pip install -q -r requirements.txt

# ── 3. 수집 실행 ────────────────────────────
echo "[INFO] 법령 수집 시작..."
python scripts/fetch_laws.py
RESULT=$?

if [ $RESULT -eq 0 ] && [ -z "$(git status --porcelain docs/)" ]; then
  echo "[INFO] 변동사항 없음 — push 스킵"
  exit 0
fi

# ── 4. Git push ─────────────────────────────
echo "[INFO] 변경사항 push 중..."
TIMESTAMP=$(date "+%Y-%m-%d %H:%M KST")
CHANGED=$(git diff --name-only docs/ | grep -c "\.md$" || true)
NEW=$(git ls-files --others --exclude-standard docs/ | grep -c "\.md$" || true)
TOTAL=$((CHANGED + NEW))

git add docs/ fetch_laws.log
git commit -m "chore: 법령 수집 ${TIMESTAMP} (변경 ${TOTAL}건)"
git push

echo ""
echo "✓ 완료: ${TOTAL}건 변경사항 push 완료"
