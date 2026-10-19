#!/usr/bin/env bash
# PDF에서 페이지별 텍스트를 뽑거나, 한 쪽을 PNG로 렌더링한다.
# poppler(pdftotext·pdftoppm)가 있으면 그것을, 없으면 macOS 기본 PDFKit(swift)을 쓴다.
#   텍스트: pdf2txt.sh <입력.pdf> [출력.txt]        (출력 생략 시 표준 출력)
#           페이지마다 "=== p.N ===" 머리줄을 붙인다. N은 PDF 쪽 번호(1부터)다.
#   이미지: pdf2txt.sh --png <입력.pdf> <쪽> <출력.png>   (표가 텍스트로 뒤섞일 때 눈으로 확인용)
set -euo pipefail

if [ "${1:-}" = "--png" ]; then
  in="$2"; page="$3"; out="$4"
  [ -f "$in" ] || { echo "파일 없음: $in" >&2; exit 1; }
  if command -v pdftoppm >/dev/null; then
    pdftoppm -png -r 150 -f "$page" -l "$page" -singlefile "$in" "${out%.png}"
    exit 0
  fi
  command -v swift >/dev/null || { echo "pdftoppm도 swift도 없음: brew install poppler 필요" >&2; exit 1; }
  swift - "$in" "$page" "$out" <<'SWIFT'
import Foundation
import PDFKit
import AppKit
let a = CommandLine.arguments
guard let doc = PDFDocument(url: URL(fileURLWithPath: a[1])), let n = Int(a[2]),
      let page = doc.page(at: n - 1) else { FileHandle.standardError.write("쪽을 열 수 없음\n".data(using: .utf8)!); exit(1) }
let box = page.bounds(for: .mediaBox)
let scale: CGFloat = 2.0
let size = NSSize(width: box.width * scale, height: box.height * scale)
let img = page.thumbnail(of: size, for: .mediaBox)
guard let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
try png.write(to: URL(fileURLWithPath: a[3]))
SWIFT
  exit 0
fi

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
