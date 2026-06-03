"""
fetch_laws.py
-------------
법제처 국가법령정보 Open API를 이용하여
여객자동차 운수사업법 관련 법령·행정규칙·자치법규를
Markdown 파일로 수집·저장합니다.

변동 감지 방식:
  docs/.manifest.json 에 {mst: 시행일자} 를 보관.
  API에서 받은 시행일자와 비교하여 변경된 건만 본문 재수집.
  변경 없으면 파일 미수정 → git diff 없음 → 커밋 없음.

API 문서: https://open.law.go.kr/LSO/openApi/guideList.do
실행 전 환경변수 LAW_API_KEY 설정 필요
"""

import json
import os
import re
import sys
import time
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

import requests

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────
API_KEY   = os.environ["LAW_API_KEY"]
BASE_URL  = "https://www.law.go.kr/DRF"
OUTPUT    = Path("docs")
MANIFEST  = OUTPUT / ".manifest.json"   # 변동 감지용 스냅샷
DELAY_SEC = 0.5
LOG_LEVEL = logging.INFO

SEARCH_KEYWORDS = ["여객자동차", "노선버스", "준공영제"]

# ─────────────────────────────────────────
# 로거
# ─────────────────────────────────────────
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("fetch_laws.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 매니페스트 (변동 감지)
# ─────────────────────────────────────────
def load_manifest() -> dict:
    """이전 수집 시 저장한 {mst: enforcement_date} 딕셔너리."""
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict):
    OUTPUT.mkdir(exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def has_changed(mst: str, new_date: str, manifest: dict) -> bool:
    """시행일자가 달라졌거나 신규 항목이면 True."""
    return manifest.get(mst) != new_date


# ─────────────────────────────────────────
# API 호출 공통
# ─────────────────────────────────────────
def api_get(endpoint: str, params: dict) -> ET.Element | None:
    params.update({"OC": API_KEY, "type": "XML"})
    url = f"{BASE_URL}/{endpoint}.do"
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return ET.fromstring(resp.text)
    except Exception as e:
        log.warning(f"API 호출 실패 [{endpoint}] params={params}: {e}")
        return None


# ─────────────────────────────────────────
# 목록 조회
# ─────────────────────────────────────────
def fetch_list(target: str, item_tag: str, mst_tag: str,
               name_tag: str, keyword: str) -> list[dict]:
    items, page = [], 1
    while True:
        root = api_get("lawSearch", {
            "target": target, "query": keyword,
            "display": 100, "page": page,
        })
        if root is None:
            break
        nodes = root.findall(f".//{item_tag}")
        if not nodes:
            break
        for node in nodes:
            items.append({
                "type":   target,
                "mst":    _text(node, mst_tag),
                "name":   _text(node, name_tag),
                "date":   _text(node, "시행일자"),
                "region": _text(node, "자치단체명"),  # 자치법규만 값 있음
            })
        page += 1
        time.sleep(DELAY_SEC)
        if len(nodes) < 100:
            break
    return items


def collect_all_lists() -> list[dict]:
    configs = [
        ("law",    "law",    "법령MST",      "법령명한글"),
        ("admrul", "admrul", "행정규칙MST",   "행정규칙명"),
        ("ordin",  "ordin",  "자치법규MST",   "자치법규명"),
    ]
    all_items: list[dict] = []
    for kw in SEARCH_KEYWORDS:
        log.info(f"  키워드 [{kw}] 목록 조회 중...")
        for target, tag, mst_tag, name_tag in configs:
            all_items += fetch_list(target, tag, mst_tag, name_tag, kw)
        time.sleep(DELAY_SEC)
    return deduplicate(all_items)


# ─────────────────────────────────────────
# 본문 조회 → Markdown
# ─────────────────────────────────────────
TARGET_MAP = {
    "law":    "law",
    "admrul": "admrul",
    "ordin":  "ordin",
}

def fetch_body(item: dict) -> str | None:
    root = api_get("lawService", {
        "target": TARGET_MAP[item["type"]],
        "MST":    item["mst"],
    })
    return xml_to_markdown(root) if root is not None else None


# ─────────────────────────────────────────
# XML → Markdown
# ─────────────────────────────────────────
def xml_to_markdown(root: ET.Element) -> str:
    name = (root.findtext(".//법령명한글")
            or root.findtext(".//행정규칙명")
            or root.findtext(".//자치법규명")
            or "법령")
    promulgation = root.findtext(".//공포일자") or ""
    enforcement  = root.findtext(".//시행일자") or ""
    law_no       = (root.findtext(".//법령번호")
                    or root.findtext(".//공포번호") or "")

    lines = [
        f"# {name}\n",
        f"> **법령번호** {law_no}  ",
        f"> **공포일자** {_fmt_date(promulgation)}  ",
        f"> **시행일자** {_fmt_date(enforcement)}\n",
        "---\n",
    ]

    for jo in root.iter("조문"):
        jo_no      = jo.findtext("조문번호") or ""
        jo_title   = jo.findtext("조문제목") or ""
        jo_content = jo.findtext("조문내용") or ""

        heading = f"## 제{jo_no}조" + (f" ({jo_title})" if jo_title else "")
        lines.append(heading)
        if jo_content:
            lines.append(_clean(jo_content) + "\n")

        for hang in jo.iter("항"):
            hang_no      = hang.findtext("항번호") or ""
            hang_content = hang.findtext("항내용") or ""
            if hang_content:
                lines.append(f"**{hang_no}항** {_clean(hang_content)}")
            for ho in hang.iter("호"):
                ho_no      = ho.findtext("호번호") or ""
                ho_content = ho.findtext("호내용") or ""
                if ho_content:
                    lines.append(f"  - {ho_no}. {_clean(ho_content)}")
                for mok in ho.iter("목"):
                    mok_no      = mok.findtext("목번호") or ""
                    mok_content = mok.findtext("목내용") or ""
                    if mok_content:
                        lines.append(f"    - {mok_no}) {_clean(mok_content)}")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────
# 저장 / 인덱스
# ─────────────────────────────────────────
def save_markdown(subdir: str, filename: str, content: str):
    path = OUTPUT / subdir
    path.mkdir(parents=True, exist_ok=True)
    (path / filename).write_text(content, encoding="utf-8")
    log.info(f"    저장: {subdir}/{filename}")


def build_index(all_items: list[dict], generated_at: str,
                changed: int, skipped: int) -> str:
    lines = [
        "# 여객자동차 운수사업법 관련 법령 아카이브\n",
        f"> 수집일시: {generated_at}  ",
        f"> 총 {len(all_items)}건 (변경 {changed}건 / 미변경 스킵 {skipped}건)\n",
        "---\n",
    ]
    for cat, label in [("law","📘 법령"),("admrul","📙 행정규칙"),("ordin","📗 자치법규")]:
        subset = [i for i in all_items if i["type"] == cat]
        if not subset:
            continue
        lines.append(f"## {label} ({len(subset)}건)\n")
        lines.append("| 법령명 | 시행일 | 파일 |")
        lines.append("|---|---|---|")
        for item in sorted(subset, key=lambda x: x["name"]):
            fn     = safe_filename(item["name"]) + ".md"
            region = f" ({item['region']})" if item.get("region") else ""
            link   = f"[{item['name']}{region}](./{cat}/{fn})"
            lines.append(f"| {link} | {_fmt_date(item['date'])} | `{fn}` |")
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def _text(el: ET.Element, tag: str) -> str:
    node = el.find(tag)
    return node.text.strip() if node is not None and node.text else ""

def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()

def _fmt_date(d: str) -> str:
    return f"{d[:4]}.{d[4:6]}.{d[6:]}" if len(d) == 8 else d

def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)[:100]

def deduplicate(items: list[dict]) -> list[dict]:
    seen, result = set(), []
    for item in items:
        key = (item["type"], item["mst"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────
def main():
    log.info("=== 법령 수집 시작 ===")
    OUTPUT.mkdir(exist_ok=True)

    # ① 매니페스트 로드 (이전 실행의 시행일자 스냅샷)
    manifest = load_manifest()
    log.info(f"매니페스트 로드: {len(manifest)}건 이전 기록")

    # ② 전체 목록 조회 (본문 없이 메타만)
    log.info("목록 조회 중...")
    all_items = collect_all_lists()
    log.info(f"목록 조회 완료: {len(all_items)}건")

    # ③ 변동 여부 판별 → 변경된 건만 본문 수집
    changed_count = 0
    skipped_count = 0
    new_manifest  = {}

    for item in all_items:
        mst  = item["mst"]
        date = item["date"]
        new_manifest[mst] = date   # 항상 최신 시행일자로 갱신

        if not has_changed(mst, date, manifest):
            log.debug(f"  스킵(미변경): {item['name']} [{date}]")
            skipped_count += 1
            continue

        # 신규 또는 시행일자 변경 → 본문 재수집
        action = "신규" if mst not in manifest else f"변경({manifest[mst]}→{date})"
        log.info(f"  [{action}] {item['name']}")

        body = fetch_body(item)
        if body:
            save_markdown(item["type"], safe_filename(item["name"]) + ".md", body)
            changed_count += 1
        else:
            log.warning(f"    본문 수집 실패: {item['name']}")
        time.sleep(DELAY_SEC)

    # ④ 결과 로그
    log.info(f"변경 수집: {changed_count}건 / 미변경 스킵: {skipped_count}건")

    if changed_count == 0:
        log.info("변동사항 없음 — 파일 미수정, 커밋 발생하지 않습니다.")
        # 인덱스·매니페스트도 건드리지 않아 git diff 없음
        sys.exit(0)

    # ⑤ 변경이 있을 때만 매니페스트·인덱스 업데이트
    save_manifest(new_manifest)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    index_md = build_index(all_items, generated_at, changed_count, skipped_count)
    (OUTPUT / "README.md").write_text(index_md, encoding="utf-8")
    log.info("인덱스(docs/README.md) 갱신 완료")

    log.info("=== 완료 ===")


if __name__ == "__main__":
    main()
