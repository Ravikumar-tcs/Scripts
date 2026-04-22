from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import config

APPROVED_LABEL = "approved-ready-to-ship"
ARTIFACT_NAME = "episode-audio"
_RUN_ID_RE = re.compile(r"artifact-run-id:\s*(\d+)", re.IGNORECASE)


def _run(cmd: list[str], *, check: bool = True, capture: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def _run_id() -> str:
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if not run_id:
        raise RuntimeError("GITHUB_RUN_ID not set (must run inside GitHub Actions)")
    return run_id


def _server_url() -> str:
    return os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")


def _repo() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY not set")
    return repo


def artifact_url_for_current_run() -> str:
    return f"{_server_url()}/{_repo()}/actions/runs/{_run_id()}"


def create_episode_pr(
    *,
    when: date,
    episode_dir: Path,
    script_preview: str,
) -> dict:
    """Commit episode artifacts on a new branch and open a PR. Returns {url, number, branch}."""
    branch = f"episode/{when.isoformat()}"

    _run(["git", "config", "user.name", "github-actions[bot]"])
    _run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    _run(["git", "checkout", "-B", branch])

    rel = episode_dir.relative_to(config.REPO_ROOT)
    for fname in ("findings.json", "sources.md", "script.md", "script.json"):
        p = episode_dir / fname
        if p.exists():
            _run(["git", "add", str(rel / fname)])

    _run(["git", "commit", "-m", f"Episode {when.isoformat()}: draft script and findings"])
    _run(["git", "push", "-u", "origin", branch, "--force-with-lease"])

    artifact_url = artifact_url_for_current_run()
    body = _pr_body(when=when, artifact_url=artifact_url, script_preview=script_preview)
    result = _run([
        "gh", "pr", "create",
        "--title", f"Episode {when.isoformat()} — ready for review",
        "--body", body,
        "--head", branch,
        "--base", "main",
    ])
    url = result.stdout.strip().splitlines()[-1]

    number_result = _run([
        "gh", "pr", "view", url, "--json", "number", "-q", ".number",
    ])
    number = int(number_result.stdout.strip())

    return {"url": url, "number": number, "branch": branch, "artifact_url": artifact_url}


def _pr_body(*, when: date, artifact_url: str, script_preview: str) -> str:
    return (
        f"# Episode {when.isoformat()}\n\n"
        f"**Artifact (episode.mp3):** {artifact_url}\n"
        f"**artifact-run-id: {_run_id()}**\n\n"
        f"## Review checklist\n"
        f"- [ ] Script facts trace to `sources.md`\n"
        f"- [ ] Audio plays cleanly start to finish\n"
        f"- [ ] Voices match the intended speakers\n"
        f"- [ ] No legal / confidential issues\n\n"
        f"When ready, label this PR `{APPROVED_LABEL}` — ship workflow runs Friday 9 AM EST.\n\n"
        f"---\n\n"
        f"## Script preview\n\n"
        f"```\n{script_preview}\n```\n"
    )


@dataclass
class ApprovedPR:
    number: int
    branch: str
    body: str
    artifact_run_id: str


def find_approved_pr() -> ApprovedPR | None:
    result = _run([
        "gh", "pr", "list",
        "--label", APPROVED_LABEL,
        "--state", "open",
        "--json", "number,headRefName,body",
        "--limit", "10",
    ])
    prs = json.loads(result.stdout or "[]")
    if not prs:
        return None
    pr = prs[0]
    match = _RUN_ID_RE.search(pr.get("body") or "")
    if not match:
        raise RuntimeError(f"PR #{pr['number']} is labeled approved but has no artifact-run-id in its body")
    return ApprovedPR(
        number=pr["number"],
        branch=pr["headRefName"],
        body=pr["body"],
        artifact_run_id=match.group(1),
    )


def download_artifact(run_id: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    _run(["gh", "run", "download", run_id, "-n", ARTIFACT_NAME, "-D", str(target_dir)])
    mp3s = list(target_dir.rglob("*.mp3"))
    if not mp3s:
        raise RuntimeError(f"No mp3 found in artifact for run {run_id}")
    return mp3s[0]


def checkout_branch(branch: str) -> None:
    _run(["git", "fetch", "origin", branch])
    _run(["git", "checkout", branch])


def commit_and_push_shipped_log(when: date, shipped_path: Path, branch: str) -> None:
    rel = shipped_path.relative_to(config.REPO_ROOT)
    _run(["git", "config", "user.name", "github-actions[bot]"])
    _run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    _run(["git", "add", str(rel)])
    _run(["git", "commit", "-m", f"Shipped log for {when.isoformat()}"])
    _run(["git", "push", "origin", branch])


def merge_pr(pr_number: int) -> None:
    _run(["gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch"])
