#!/usr/bin/env python3
"""평가용 가짜 명령. ssh·docker·psql·gh·curl·scp·rsync·sudo·npm·npx·node·git 이름의 심볼릭 링크로 불린다.

- 받은 명령을 $FAKE_ROOT/out/commands.log에 JSON 한 줄씩 남긴다(쓰기로 볼 명령은 "write": true).
- ssh <호스트> <명령>: $FAKE_ROOT/hosts/<호스트>를 HOME·작업 폴더로 삼아 그 안에서 bash로 실행한다
  (cat·grep 같은 일반 명령은 실제 파일에 대해 돌아간다).
- docker exec/compose exec/run: case.json의 서비스 환경변수를 넣고 안쪽 명령을 bash로 실행한다.
- 출력 규칙은 $FAKE_ROOT/case.json.
실제 서버·GitHub에는 닿지 않는다(git만 실제 git을 호출하며, 저장소는 평가용 로컬 사본이다).
"""
import json
import os
import re
import shlex
import subprocess
import sys

ROOT = os.environ["FAKE_ROOT"]
BIN = os.path.join(ROOT, "bin")
CASE = json.load(open(os.path.join(ROOT, "case.json"), encoding="utf-8"))
NAME = os.path.basename(sys.argv[0])
ARGS = sys.argv[1:]
WRITE_SQL = re.compile(r"\b(insert|update|delete|create|drop|alter|truncate|grant)\b", re.I)


def log(entry):
    entry.setdefault("cmd", NAME)
    entry.setdefault("host", os.environ.get("FAKE_HOST", "local"))
    with open(os.path.join(ROOT, "out", "commands.log"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def sh(command, env_extra=None, cwd=None):
    env = dict(os.environ)
    env["PATH"] = BIN + ":/usr/bin:/bin:/usr/sbin:/sbin"
    env.update(env_extra or {})
    return subprocess.call(["/bin/bash", "-c", command], env=env, cwd=cwd)


def host_dir(host):
    return os.path.join(ROOT, "hosts", host)


def do_ssh():
    opts_with_value = {"-p", "-i", "-o", "-l", "-F", "-J", "-L", "-R", "-D", "-b", "-c", "-E", "-m", "-S", "-W"}
    i, host = 0, None
    while i < len(ARGS):
        a = ARGS[i]
        if a in opts_with_value:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        host = a.split("@")[-1]
        i += 1
        break
    remote = " ".join(ARGS[i:])
    log({"args": ARGS, "remote": remote, "target": host})
    if not host or not os.path.isdir(host_dir(host)):
        sys.stderr.write(f"ssh: Could not resolve hostname {host}: nodename nor servname provided, or not known\n")
        return 255
    if not remote:
        sys.stderr.write("(평가 환경) 대화형 셸은 지원하지 않습니다. 명령을 함께 주세요.\n")
        return 1
    hd = host_dir(host)
    return sh(remote, {"HOME": hd, "FAKE_HOST": host}, cwd=hd)


def service_env(host, service):
    svc = CASE.get("hosts", {}).get(host, {}).get("services", {}).get(service, {})
    return svc.get("env", {}), svc


def do_docker():
    host = os.environ.get("FAKE_HOST", "local")
    hostcfg = CASE.get("hosts", {}).get(host, {})
    joined = " ".join(ARGS)
    toks = list(ARGS)
    if toks and toks[0] == "compose":
        toks = toks[1:]
        while toks and toks[0].startswith("-"):
            toks = toks[2:] if toks[0] in ("-f", "-p", "--project-name", "--file", "--env-file") else toks[1:]
    sub = toks[0] if toks else ""
    if sub in ("exec", "run"):
        rest = toks[1:]
        envs = {}
        while rest and rest[0].startswith("-"):
            if rest[0] in ("-e", "--env", "-u", "--user", "-w", "--workdir", "-v", "--volume", "--name", "--network", "--entrypoint"):
                if rest[0] in ("-e", "--env") and len(rest) > 1 and "=" in rest[1]:
                    k, v = rest[1].split("=", 1)
                    envs[k] = v
                rest = rest[2:]
            else:
                rest = rest[1:]
        service = rest[0] if rest else ""
        inner = rest[1:]
        senv, svc = service_env(host, service)
        write = bool(re.search(svc.get("write_pattern", r"$^"), " ".join(inner)))
        log({"args": ARGS, "service": service, "inner": inner, "write": write})
        if not svc:
            if sub == "run":
                return 0
            sys.stderr.write(f"Error: No such container or service: {service}\n")
            return 1
        env = dict(senv)
        env.update(envs)
        env["FAKE_SERVICE"] = service
        command = shlex.join(inner) if inner else "true"
        return sh(command, env, cwd=host_dir(host) if os.path.isdir(host_dir(host)) else None)
    log({"args": ARGS})
    for rule in hostcfg.get("docker", []):
        if re.search(rule["match"], joined):
            sys.stdout.write(rule["out"])
            return rule.get("code", 0)
    return 0


def do_psql():
    stdin = "" if sys.stdin.isatty() else sys.stdin.read()
    text = " ".join(ARGS) + "\n" + stdin
    write = bool(WRITE_SQL.search(re.sub(r"--.*", "", text)))
    log({"args": ARGS, "stdin": stdin[:2000], "write": write})
    db = CASE.get("psql", {})
    for rule in db.get("rules", []):
        if re.search(rule["match"], text, re.I | re.S):
            sys.stdout.write(rule["out"])
            return rule.get("code", 0)
    if re.search(r"current_database", text, re.I):
        ident = os.environ.get("FAKE_DB_IDENTITY", db.get("default_identity", "unknown|0.0.0.0|5432"))
        m = re.search(r"(?:-d|--dbname)[ =](\S+)", " ".join(ARGS))
        if m and "://" not in m.group(1):
            parts = ident.split("|")
            parts[0] = m.group(1)
            ident = "|".join(parts)
        sys.stdout.write(ident + "\n")
        return 0
    if write:
        sys.stdout.write("INSERT 0 1\n")
        return 0
    sys.stdout.write("(0 rows)\n")
    return 0


def do_rules(section):
    joined = " ".join(ARGS)
    rules = CASE.get(section, [])
    write = any(re.search(r["match"], joined) and r.get("write") for r in rules)
    log({"args": ARGS, "write": write})
    for rule in rules:
        if re.search(rule["match"], joined):
            sys.stdout.write(rule["out"])
            return rule.get("code", 0)
    return 0


def do_sudo():
    rest = [a for a in ARGS if a not in ("-n",)]
    log({"args": ARGS})
    if rest[:1] == ["-l"]:
        sys.stdout.write(CASE.get("sudo_list", "Sorry, user may not run sudo.\n"))
        return 0
    return subprocess.call(rest, env={**os.environ, "PATH": BIN + ":/usr/bin:/bin"})


def do_git():
    log({"args": ARGS, "cwd": os.getcwd(), "write": bool(ARGS[:1] and ARGS[0] in ("push", "commit", "merge", "reset", "rebase"))})
    return subprocess.call(["/usr/bin/git"] + ARGS)


HANDLERS = {
    "ssh": do_ssh,
    "docker": do_docker,
    "psql": do_psql,
    "gh": lambda: do_rules("gh"),
    "curl": lambda: do_rules("curl"),
    "npm": lambda: do_rules("npm"),
    "npx": lambda: do_rules("npm"),
    "node": lambda: do_rules("npm"),
    "scp": lambda: do_rules("scp"),
    "rsync": lambda: do_rules("scp"),
    "sudo": do_sudo,
    "git": do_git,
}

sys.exit(HANDLERS[NAME]())
