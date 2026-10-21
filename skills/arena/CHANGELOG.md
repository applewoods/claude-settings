# CHANGELOG

Upstream: https://github.com/Jakeschincariol/arena-skill (MIT, commit df07b8e, 2026-09-26)

- 2026-10-21: local fork made. Scope narrowed to planning only (main use is paper problem setting and research plans), because that is the only planned use.
- 2026-10-21: default agents changed from 100 to 16 (`DEFAULT_AGENTS` in bracket.py), because 100 means 595 calls.
- 2026-10-21: per-phase models: spawn, attack and defend use sonnet; judge and final use opus. Judging decides the result, and the rest is volume.
- 2026-10-21: banned invented references, using the `[확인 필요]`/`[근거 필요]`/`[가정]` markers, in the task file, the competitor/attacker/judge/final templates and the rubric, to keep CLAUDE.md's no-fabrication rule.
