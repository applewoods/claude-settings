#!/usr/bin/env bash
# 기존 파일 덮어쓰기 전에 묻기 (Claude Code PreToolUse hook, matcher: Write)
#   Write 도구가 이미 있는 파일을 통째로 바꾸려 하면 권한 확인 창을 띄운다.
#   새 파일 작성, Edit(부분 수정)은 그대로 진행한다.
#   설정 저장소 안의 파일과 Claude 작업용 임시 경로는 예외로 두지 않는다(전역 규칙: 덮어쓰기 전 묻기).
f="$(jq -r '.tool_input.file_path // empty' 2>/dev/null)"
[ -n "$f" ] && [ -e "$f" ] || exit 0
jq -n --arg f "$f" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask",
  permissionDecisionReason: ("기존 파일을 덮어씁니다: " + $f)}}'
