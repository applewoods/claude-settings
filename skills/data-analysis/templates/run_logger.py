"""실험 기록 폴더 만들기: results/<YYYYMMDD-HHMMSS>_<name>/ 에 config·meta·환경 저장.

사용:
    run_dir = make_run_dir("baseline_lr", cfg)       # 실행 시작 시
    ... 학습/평가, 시드·fold별 원 점수를 run_dir / "metrics.csv" 에 저장 ...
    finish_run(run_dir, status="ok")                 # 끝날 때(실패면 status="failed: 이유")
"""
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml


def _run(cmd):
    """명령 출력. 실패(git 저장소 아님, 커밋 없음 등)하면 빈 문자열."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def make_run_dir(name: str, cfg: dict, root: str = "results") -> Path:
    # git 상태는 결과 폴더를 만들기 전에 읽는다(새 폴더가 dirty로 잡히지 않게)
    git_commit = _run(["git", "rev-parse", "HEAD"]) or None
    git_dirty = bool(_run(["git", "status", "--porcelain", "--untracked-files=no"]))
    base = Path(root) / f"{datetime.now():%Y%m%d-%H%M%S}_{name}"
    run_dir, i = base, 1
    while run_dir.exists():  # 같은 초에 여러 실행(시드 루프)이면 _2, _3 … 붙임. 기존 폴더는 덮어쓰지 않는다
        i += 1
        run_dir = base.with_name(f"{base.name}_{i}")
    (run_dir / "figures").mkdir(parents=True)
    with open(run_dir / "config.yaml", "w") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    meta = {
        "command": " ".join(sys.argv),
        "started": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit,
        "git_dirty": git_dirty,  # 추적 중인 파일에 커밋 안 된 변경이 있으면 True
        "python": sys.version.split()[0],
        "host": platform.node(),
        "seed": cfg.get("seed"),
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    if shutil.which("conda"):
        (run_dir / "environment.yml").write_text(_run(["conda", "env", "export", "--no-builds"]))
    else:
        (run_dir / "requirements.txt").write_text(_run([sys.executable, "-m", "pip", "freeze"]))
    return run_dir


def finish_run(run_dir: Path, status: str = "ok") -> None:
    meta_path = Path(run_dir) / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta.update(finished=datetime.now().isoformat(timespec="seconds"), status=status)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    d = make_run_dir("demo", {"seed": 0, "lr": 0.01})
    finish_run(d)
    print(sorted(p.name for p in d.iterdir()))
