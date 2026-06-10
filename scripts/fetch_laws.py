"""
fetch_laws.py
-------------
법제처 국가법령정보 Open API를 이용하여 여객자동차 운수사업법 관련
법령·행정규칙·자치법규를 Markdown 파일로 수집·저장합니다.

저장 구조:
  docs/{YYYYMMDD}/{target}/{파일명}.md   ← 날짜별 폴더
  docs/{YYYYMMDD}/manifest.json          ← 날짜별 변동 감지
  docs/{YYYYMMDD}/README.md              ← 날짜별 인덱스

변동 감지 방식 (의도 C):
  날짜가 바뀌면 항상 새로 전체 수집 (새 날짜 폴더 생성)
  같은 날 재실행 시에만 manifest로 중복 스킵

API 문서: https://open.law.go.kr/LSO/openApi/guideList.do
실행 전 환경변수 LAW_API_KEY 설정 필요 (OC 값 = 등록 이메일의 앞부분)
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
DELAY_SEC = 0.5
RETRIES   = 3
LOG_LEVEL = logging.INFO

TODAY     = datetime.now().strftime("%Y%m%d")
TODAY_DIR = OUTPUT / TODAY
MANIFEST  = TODAY_DIR / "manifest.json"   # 날짜별 manifest

SEARCH_KEYWORDS = ["여객자동차", "노선버스", "준공영제"]

# target별 메타 (실측 확정)
TARGET_META = {
    "law":    {"item": "law",    "id_tag": "법령일련번호",     "body_key": "MST", "name": "법령명한글",  "region": None},
    "admrul": {"item": "admrul", "id_tag": "행정규칙일련번호", "body_key": "ID",  "name": "행정규칙명",  "region": None},
    "ordin":  {"item": "law",    "id_tag": "자치법규일련번호", "body_key": "MST", "name": "자치법규명",  "region": "지자체기관명"},
}

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
# 매니페스트 (변동 감지 - 날짜별)
# ─────────────────────────────────────────
def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict):
    TODAY_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def has_changed(mst: str, new_date: str, manifest: dict) -> bool:
    return manifest.get(mst) != new_date


# ─────────────────────────────────────────
# API 호출 공통
# ─────────────────────────────────────────
def api_get(endpoint: str, params: dict):
    params = {**params, "OC": API_KEY, "type": "XML"}
    url = f"{BASE_URL}/{endpoint}.do"
    for attempt in range(RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            time.sleep(DELAY_SEC)
            return ET.fromstring(resp.text)
        except requests.exceptions.ConnectionError:
            wait = 2 * (attempt + 1)
            log.warning(f"연결 끊김 [{endpoint}] {attempt+1}/{RETRIES} - {wait}s 후 재시도")
            time.sleep(wait)
        except Exception as e:
            log.warning(f"API 호출 실패 [{endpoint}] params={params}: {e}")
            return None
    log.warning(f"재시도 초과 [{endpoint}] params={params}")
    return None


# ─────────────────────────────────────────
# 목록 조회
# ─────────────────────────────────────────
def fetch_list(target: str, keyword: str) -> list:
    meta = TARGET_META[target]
    items, page = [], 1
    while True:
        root = api_get("lawSearch", {
            "target": target, "query": keyword,
            "display": 100, "page": page,
        })
        if root is None:
            break

        nodes = root.findall(f".//{meta['item']}")
        if not nodes:
            break

        for node in nodes:
            mst = _text(node, meta["id_tag"])
            if not mst:
                continue
            items.append({
                "type":   target,
                "mst":    mst,
                "name":   _text(node, meta["name"]),
                "date":   _text(node, "시행일자"),
                "region": _text(node, meta["region"]) if meta["region"] else "",
            })

        total = int(root.findtext("totalCnt") or 0)
        if page * 100 >= total or len(nodes) < 100:
            break
        page += 1
        time.sleep(DELAY_SEC)

    return items


def collect_all_lists() -> list:
    all_items = []
    for kw in SEARCH_KEYWORDS:
        log.info(f"  키워드 [{kw}] 목록 조회 중...")
        for target in TARGET_META:
            all_items += fetch_list(target, kw)
        time.sleep(DELAY_SEC)
    return deduplicate(all_items)


# ─────────────────────────────────────────
# 본문 조회 -> Markdown
# ─────────────────────────────────────────
def fetch_body(item: dict):
    meta = TARGET_META[item["type"]]
    root = api_get("lawService", {
        "target": item["type"],
        meta["body_key"]: item["mst"],
    })
    return xml_to_markdown(root) if root is not None else None


# ─────────────────────────────────────────
# XML -> Markdown
# ─────────────────────────────────────────
def xml_to_markdown(root: ET.Element) -> str:
    info = root.find("자치법규기본정보")
    name = ((info.findtext("자치법규명") if info is not None else None)
            or root.findtext(".//법령명한글")
            or root.findtext(".//행정규칙명")
            or "법령")
    promulgation = ((info.findtext("공포일자") if info is not None else None)
                    or root.findtext(".//공포일자")
                    or root.findtext(".//발령일자") or "")
    enforcement  = ((info.findtext("시행일자") if info is not None else None)
                    or root.findtext(".//시행일자") or "")
    law_no       = ((info.findtext("공포번호") if info is not None else None)
                    or root.findtext(".//법령번호")
                    or root.findtext(".//공포번호")
                    or root.findtext(".//발령번호") or "")
    region       = (info.findtext("지자체기관명") if info is not None else "") or ""

    lines = [f"# {name}\n"]
    if region:
        lines.append(f"> **지자체** {region}  ")
    lines.extend([
        f"> **법령번호** {law_no}  ",
        f"> **공포일자** {_fmt_date(promulgation)}  ",
        f"> **시행일자** {_fmt_date(enforcement)}\n",
        "---\n",
    ])

    body = []

    # (1) 자치법규 정형 구조: <조문> 컨테이너 안의 <조>
    jo_container = root.find("조문")
    if jo_container is not None:
        for jo in jo_container.findall("조"):
            jo_title   = jo.findtext("조제목") or ""
            jo_content = jo.findtext("조내용") or ""
            if not jo_content.strip():
                continue
            txt = _clean(jo_content)
            if not jo_title and re.match(r"^제\d+[장절]", txt):
                body.append(f"\n### {txt}\n")
                continue
            m = re.match(r"^(제\s*\d+조(?:의\d+)?)\s*(?:\(([^)]*)\))?\s*(.*)", txt, re.S)
            if m:
                jo_head, parsed_title, rest = m.group(1), m.group(2), m.group(3)
                title = parsed_title or jo_title
                body.append(f"## {jo_head}" + (f" ({title})" if title else ""))
                if rest.strip():
                    body.append(rest.strip() + "\n")
            else:
                body.append(txt + "\n")

    # (2) 법령식 정형 구조 (<조문>)
    if not body:
        for jo in root.iter("조문"):
            jo_no      = jo.findtext("조문번호") or ""
            jo_title   = jo.findtext("조문제목") or ""
            jo_content = jo.findtext("조문내용") or ""
            heading = f"## 제{jo_no}조" + (f" ({jo_title})" if jo_title else "")
            body.append(heading)
            if jo_content:
                body.append(_clean(jo_content) + "\n")
            for hang in jo.iter("항"):
                hang_no      = hang.findtext("항번호") or ""
                hang_content = hang.findtext("항내용") or ""
                if hang_content:
                    body.append(f"**{hang_no}항** {_clean(hang_content)}")
                for ho in hang.iter("호"):
                    ho_no      = ho.findtext("호번호") or ""
                    ho_content = ho.findtext("호내용") or ""
                    if ho_content:
                        body.append(f"  - {ho_no} {_clean(ho_content)}")
                    for mok in ho.iter("목"):
                        mok_no      = mok.findtext("목번호") or ""
                        mok_content = mok.findtext("목내용") or ""
                        if mok_content:
                            body.append(f"    - {mok_no}) {_clean(mok_content)}")
            body.append("")

    # (3) fallback: 행정규칙 — <조문내용> 통짜 텍스트
    if not body:
        for jo in root.iter("조문내용"):
            txt = (jo.text or "").strip()
            if not txt:
                continue
            m = re.match(r"^(제\s*\d+조(?:의\d+)?)\s*\(([^)]*)\)\s*(.*)", txt, re.S)
            if m:
                jo_head, jo_title, rest = m.group(1), m.group(2), m.group(3)
                body.append(f"## {jo_head} ({jo_title})")
                if rest.strip():
                    body.append(_clean(rest) + "\n")
            else:
                body.append(_clean(txt) + "\n")

    # (4) 그래도 비면 부칙 등 다른 텍스트라도 수집
    if not body:
        for el in root.iter():
            if el.tag.endswith("기본정보"):
                continue
            if el.text and el.text.strip() and el.tag not in (
                    "행정규칙명", "자치법규명", "법령명한글"):
                body.append(_clean(el.text))

    boochik = root.find("부칙")
    if boochik is not None:
        boochik_text = boochik.findtext("부칙내용") or ""
        if boochik_text.strip():
            body.append("\n---\n## 부칙\n")
            body.append(_clean(boochik_text) + "\n")

    lines += body
    return "\n".join(lines)


# ─────────────────────────────────────────
# 저장 / 인덱스
# ─────────────────────────────────────────
def save_markdown(subdir: str, filename: str, content: str):
    path = TODAY_DIR / subdir
    path.mkdir(parents=True, exist_ok=True)
    (path / filename).write_text(content, encoding="utf-8")
    log.info(f"    저장: {TODAY}/{subdir}/{filename}")


def build_index(all_items: list, generated_at: str,
                changed: int, skipped: int) -> str:
    lines = [
        "# 여객자동차 운수사업법 관련 법령 아카이브\n",
        f"> 수집일시: {generated_at}  ",
        f"> 총 {len(all_items)}건 (변경 {changed}건 / 미변경 스킵 {skipped}건)\n",
        "---\n",
    ]
    for cat, label in [("law", "법령"), ("admrul", "행정규칙"), ("ordin", "자치법규")]:
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
    if not tag:
        return ""
    node = el.find(tag)
    return node.text.strip() if node is not None and node.text else ""


def _clean(t: str) -> str:
    return re.sub(r"[ \t]+", " ", t).strip()


def _fmt_date(d: str) -> str:
    return f"{d[:4]}.{d[4:6]}.{d[6:]}" if len(d) == 8 else d


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)[:100]


def deduplicate(items: list) -> list:
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
    log.info(f"오늘 날짜 폴더: docs/{TODAY}/")
    OUTPUT.mkdir(exist_ok=True)
    TODAY_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    log.info(f"매니페스트 로드: {len(manifest)}건 이전 기록 (docs/{TODAY}/manifest.json)")

    log.info("목록 조회 중...")
    all_items = collect_all_lists()
    log.info(f"목록 조회 완료: {len(all_items)}건")

    changed_count = 0
    skipped_count = 0
    new_manifest  = {}

    for item in all_items:
        mst  = item["mst"]
        date = item["date"]
        new_manifest[mst] = date

        if not has_changed(mst, date, manifest):
            log.debug(f"  스킵(미변경): {item['name']} [{date}]")
            skipped_count += 1
            continue

        action = "신규" if mst not in manifest else f"변경({manifest[mst]}->{date})"
        log.info(f"  [{action}] {item['name']}")

        body = fetch_body(item)
        if body:
            save_markdown(item["type"], safe_filename(item["name"]) + ".md", body)
            changed_count += 1
        else:
            log.warning(f"    본문 수집 실패: {item['name']}")
        time.sleep(DELAY_SEC)

    log.info(f"변경 수집: {changed_count}건 / 미변경 스킵: {skipped_count}건")

    if changed_count == 0:
        log.info("변동사항 없음 - 파일 미수정, 커밋 발생하지 않습니다.")
        sys.exit(0)

    save_manifest(new_manifest)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    index_md = build_index(all_items, generated_at, changed_count, skipped_count)
    (TODAY_DIR / "README.md").write_text(index_md, encoding="utf-8")
    log.info(f"인덱스(docs/{TODAY}/README.md) 갱신 완료")

    log.info("=== 완료 ===")


if __name__ == "__main__":
    main()
