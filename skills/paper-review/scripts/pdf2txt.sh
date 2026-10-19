#!/usr/bin/env bash
# PDF에서 페이지별 텍스트를 뽑는다. poppler(pdftotext)가 있으면 그것을, 없으면 macOS 기본 PDFKit(swift)을 쓴다.
# 사용법: pdf2txt.sh <입력.pdf> [출력.txt]   (출력 생략 시 표준 출력)
# 페이지마다 "=== p.N ===" 머리줄을 붙인다. N은 PDF 쪽 번호(1부터)다.
set -euo pipefail
in="$1"; out="${2:-/dev/stdout}"
[ -f "$in" ] || { echo "파일 없음: $in" >&2; exit 1; }

if command -v pdftotext >/dev/null && command -v pdfinfo >/dev/null; then
  n="$(pdfinfo "$in" | awk '/^Pages:/{print $2}')"
  { for ((i=1; i<=n; i++)); do echo "=== p.$i ==="; pdftotext -layout -f "$i" -l "$i" "$in" -; done; } > "$out"
  exit 0
fi

command -v swift >/dev/null || { echo "pdftotext도 swift도 없음: brew install poppler 필요" >&2; exit 1; }
swift - "$in" > "$out" <<'SWIFT'
import Foundation
import PDFKit
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let doc = PDFDocument(url: url) else { FileHandle.standardError.write("PDF 열기 실패\n".data(using: .utf8)!); exit(1) }
for i in 0..<doc.pageCount {
    print("=== p.\(i + 1) ===")
    print(doc.page(at: i)?.string ?? "")
}
SWIFT
