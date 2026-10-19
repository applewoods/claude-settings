#!/usr/bin/env python3
"""지식 위키 기계 점검: 깨진 링크, index 누락, 고립 페이지, frontmatter·출처 누락.

사용법: python3 lint.py ~/wiki
문제가 있으면 목록을 출력하고 종료 코드 1, 없으면 0. 아직 없는 페이지로의 링크는 경고만 한다.
"""
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
REQUIRED = ("type", "sources", "updated")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def links(text):
    # 코드 블록·인라인 코드 안의 [[...]]는 예시이므로 링크로 세지 않는다
    return [t.strip() for t in LINK.findall(CODE.sub("", text))]


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
    files = sorted((root / "wiki").rglob("*.md"))
    # 링크는 파일명([[stem]])으로 걸리므로 폴더가 달라도 같은 파일명이면 하나가 가려진다
    seen, dup_names = {}, []
    for p in files:
        if p.stem in seen:
            dup_names.append(f"{p.stem}: {seen[p.stem].relative_to(root)} / {p.relative_to(root)}")
        seen.setdefault(p.stem, p)
    pages = {p.stem: p for p in files}
    index_text = (root / "index.md").read_text(encoding="utf-8")
    index_links = set(links(index_text))

    broken, missing_fm, no_sources, bad_sources = [], [], [], []
    inbound = {name: 0 for name in pages}
    for name, path in pages.items():
        text = path.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if fm is None or any(k not in fm for k in REQUIRED):
            missing_fm.append(name)
        elif fm["sources"] in ("", "[]"):
            no_sources.append(name)
        else:
            # raw/ 로 시작하는 출처는 실제 파일이 있어야 한다
            for src in re.findall(r"raw/[^,\]\s]+", fm["sources"]):
                if not (root / src).exists():
                    bad_sources.append(f"{name} → {src}")
        for target in links(text):
            if target in pages:
                if target != name:
                    inbound[target] += 1
            else:
                broken.append(f"{name} → [[{target}]]")

    # 아직 없는 페이지로의 링크는 위키 규칙상 허용(만들 페이지 후보)이라 경고로만 보여 준다
    warnings = {"아직 없는 페이지로의 링크 (만들 페이지 후보)": broken}
    report = {
        "index.md에 없는 페이지": sorted(set(pages) - index_links),
        "index.md에만 있고 파일이 없는 항목": sorted(index_links - set(pages)),
        "다른 페이지에서 링크하지 않는 페이지": sorted(n for n, c in inbound.items() if c == 0),
        "frontmatter 누락(type·sources·updated)": sorted(missing_fm),
        "sources가 비어 있음": sorted(no_sources),
        "sources의 raw/ 파일이 없음": sorted(bad_sources),
        "폴더가 달라도 파일명이 겹침 (링크가 한쪽만 가리킴)": dup_names,
    }
    print(f"페이지 {len(pages)}개 점검")
    found = False
    for title, items in report.items():
        if items:
            found = True
            print(f"\n## {title} ({len(items)})")
            for item in items:
                print(f"- {item}")
    for title, items in warnings.items():
        if items:
            print(f"\n## [경고, 실패 아님] {title} ({len(items)})")
            for item in items:
                print(f"- {item}")
    if not found:
        print("문제 없음")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "~/wiki"))
