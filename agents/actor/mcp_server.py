import asyncio
import os
import pathlib

def _resolve_sandbox_cwd(cwd: str | None) -> str:
    base = pathlib.Path(os.getenv("ACTOR_SANDBOX_DIR", "C:\\ILoveCoding\\actor_sandbox")).resolve()
    base.mkdir(parents=True, exist_ok=True)
    if not cwd:
        return str(base)
    # Resolve cwd under base and prevent escape
    target = (base / cwd).resolve()
    if base not in target.parents and target != base:
        raise ValueError(f"cwd '{target}' escapes sandbox '{base}'")
    return str(target)

async def shell_run(cmd: str, args: list[str] = [], cwd: str | None = None, env: dict | None = None):
    allowed = [c.strip() for c in os.getenv(
    "ACTOR_ALLOWED_CMDS",
    "cmd,git,python,pytest,echo,kubectl"
    ).split(",")]
    if cmd not in allowed:
        return {"ok": False, "error": f"Command 'kubectl' not allowed"}
    try:
        safe_cwd = _resolve_sandbox_cwd(cwd)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    proc_env = os.environ.copy()
    if env:
        for k, v in env.items():
            proc_env[str(k)] = str(v)
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=safe_cwd,
            env=proc_env
        )
        out, err = await proc.communicate()
        return {"ok": proc.returncode == 0, "stdout": out.decode(), "stderr": err.decode(), "code": proc.returncode, "cwd": safe_cwd}
    except Exception as e:
        return {"ok": False, "error": str(e), "cwd": safe_cwd}

async def http_request(method: str, url: str, json: dict | None = None, headers: dict | None = None):
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.request(method.upper(), url, json=json, headers=headers)
        return {"ok": resp.is_success, "status": resp.status_code, "body": resp.text}

async def fs_write(path: str, content: str, cwd: str | None = None):
    safe_cwd = _resolve_sandbox_cwd(cwd)
    p = pathlib.Path(safe_cwd) / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p)}

async def docker(args: list[str], cwd: str | None = None, env: dict | None = None):
    return await shell_run(cmd="docker", args=args, cwd=cwd, env=env)

async def compose(args: list[str], cwd: str | None = None, env: dict | None = None):
    res = await shell_run(cmd="docker", args=["compose", *args], cwd=cwd, env=env)
    if res.get("ok"):
        return res
    return await shell_run(cmd="docker-compose", args=args, cwd=cwd, env=env)

async def kubectl(args: list[str], cwd: str | None = None, env: dict | None = None):
    return await shell_run(cmd="kubectl", args=args, cwd=cwd, env=env)
    import subprocess, tempfile, os, json, httpx, pathlib

    repo_dir = tempfile.mkdtemp()
    subprocess.run(["git", "clone", repo_url, repo_dir], check=True)

    target_file = pathlib.Path(repo_dir) / file_path
    old_code = target_file.read_text(encoding="utf-8")

    # Call LLM to propose a fix
    from compile_plan import _openai_compatible_chat
    prompt = f"Fix the following code error:\n\nError:\n{error}\n\nFile ({file_path}):\n{old_code}"
    new_code = _openai_compatible_chat(
        [{"role": "user", "content": prompt}],
        model=os.getenv("LLM_MODEL", "meta-llama/llama-3.3-8b-instruct:free")
    )

    target_file.write_text(new_code, encoding="utf-8")

    subprocess.run(["git", "checkout", "-b", branch], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", file_path], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_dir, check=True)
    subprocess.run(["git", "push", "origin", branch], cwd=repo_dir, check=True)

    # Raise PR via GitHub API
    token = os.getenv("GITHUB_TOKEN")
    repo_name = repo_url.split(":")[-1].replace(".git", "")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient() as client:
        pr = await client.post(
            f"https://api.github.com/repos/{repo_name}/pulls",
            headers=headers,
            json={"title": pr_title, "head": branch, "base": "main", "body": "Auto-generated PR"}
        )
        return {"ok": pr.status_code < 300, "status": pr.status_code, "response": pr.text}