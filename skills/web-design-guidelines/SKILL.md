---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices", and before shipping frontend changes.
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

> 로컬 수정본: 원본은 실행할 때마다 원격 규칙을 받아오지만, 원격 내용이 바뀌어도 검토 없이 적용되지 않도록
> 2026-10-17에 검토한 규칙을 `guidelines.md`에 고정했다.
> 출처: vercel-labs/agent-skills (MIT), vercel-labs/web-interface-guidelines `command.md`.

## How It Works

1. Read `guidelines.md` in this skill's folder (do not fetch the rules from the network)
2. Read the specified files (or prompt user for files/pattern)
3. Check against all rules in the guidelines
4. Output findings in the terse `file:line` format

## Korean-language UIs

The "Content & Copy" and some "Typography" rules (Title Case, curly quotes) are for English copy.
For Korean UI text, skip them and review copy with the `design:ux-copy` skill instead.

## Usage

When a user provides a file or pattern argument:
1. Read `guidelines.md`
2. Read the specified files
3. Apply all rules from the guidelines
4. Output findings using the format specified in the guidelines

If no files specified, ask the user which files to review.
