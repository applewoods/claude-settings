#!/usr/bin/env python3
"""지식 위키 기계 점검: 깨진 링크, index 누락, 고립 페이지, frontmatter·출처 누락.

사용법: python3 lint.py ~/wiki
문제가 있으면 목록을 출력하고 종료 코드 1, 없으면 0.
"""
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
REQUIRED = ("type", "sources", "updated")


def frontmatter(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    fields = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fields[key.strip()] = val.strip()
    return fields


def main(root):
    root = Path(root).expanduser()
    pages = {p.stem: p for p in (root / "wiki").rglob("*.md")}
    index_text = (root / "index.md").read_text(encoding="utf-8")
    index_links = set(LINK.findall(index_text))

    broken, missing_fm, no_sources = [], [], []
    inbound = {name: 0 for name in pages}
    for name, path in pages.items():
        text = path.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if fm is None or any(k not in fm for k in REQUIRED):
            missing_fm.append(name)
        elif fm["sources"] in ("", "[]"):
            no_sources.append(name)
        for target in LINK.findall(text):
            target = target.strip()
            if target in pages:
                if target != name:
                    inbound[target] += 1
            else:
                broken.append(f"{name} → [[{target}]]")

    report = {
        "깨진 링크 (만들 페이지 후보일 수 있음)": broken,
        "index.md에 없는 페이지": sorted(set(pages) - index_links),
        "index.md에만 있고 파일이 없는 항목": sorted(index_links - set(pages)),
        "다른 페이지에서 링크하지 않는 페이지": sorted(n for n, c in inbound.items() if c == 0),
        "frontmatter 누락(type·sources·updated)": sorted(missing_fm),
        "sources가 비어 있음": sorted(no_sources),
    }
    print(f"페이지 {len(pages)}개 점검")
    found = False
    for title, items in report.items():
        if items:
            found = True
            print(f"\n## {title} ({len(items)})")
            for item in items:
                print(f"- {item}")
    if not found:
        print("문제 없음")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "~/wiki"))
