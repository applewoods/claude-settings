# CHANGELOG

Upstream: https://github.com/Jakeschincariol/arena-skill (MIT, commit df07b8e, 2026-09-26)

- 2026-10-21: local fork made. Scope narrowed to planning only (main use is paper problem setting and research plans), because that is the only planned use.
- 2026-10-21: default agents changed from 100 to 16 (`DEFAULT_AGENTS` in bracket.py), because 100 means 595 calls.
- 2026-10-21: per-phase models: spawn, attack and defend use sonnet; judge and final use opus. Judging decides the result, and the rest is volume.
- 2026-10-21: banned invented references, using the `[확인 필요]`/`[근거 필요]`/`[가정]` markers, in the task file, the competitor/attacker/judge/final templates and the rubric, to keep CLAUDE.md's no-fabrication rule.
- 2026-10-21: attacker: "at most 7" changed to "only real flaws, 0 to 7, no quota", with NO REAL FLAWS FOUND allowed. In the first real run, all 14 attack files had exactly 7 attacks.
- 2026-10-21: defender: "conceding scores better" changed to "a correct rebuttal scores the same as a correct fix; conceding a wrong attack is penalised". In the first run, 97 of 98 attacks were conceded.
- 2026-10-21: judge and rubric: every attack ruled VALID or INVALID before scoring; only VALID attacks count; an accepted INVALID attack that made the solution worse is penalised. Verdict JSON gains an "invalid" field. Purpose: catch the case where every attack is accepted regardless of merit.
- 2026-10-21: control baseline: with no earlier answer, one opus single-pass answer is made before init (`--control-file`), hidden from competitors and compared blind in the final check. A finished run can get one with the new `control` command. The final template is now neutral (rejected answer or control). Without this, the first run could not show whether it beat a plain answer.
- 2026-10-21: load_state follows the folder it was loaded from (rewrites dir and solution paths). A copied run had been writing into the original run's folder.
- 2026-10-21: Step 2: an option wording the user picked is not a hard requirement unless confirmed ("1~2쪽" came from the orchestrator's option text). Step 5 gains a run-health report.
