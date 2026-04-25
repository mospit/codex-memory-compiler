"""Git commit source adapter for Codex Memory Compiler."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .ingest import TMP_DIR, append_section
from .utils import trim_sentence


@dataclass(slots=True)
class GitCommit:
    sha: str
    short_sha: str
    author_date: str
    author: str
    subject: str
    body: str
    files: list[str]


def run_git(repo_root: Path, args: list[str]) -> str:
    """Run a git command and return stdout, raising a concise CLI error on failure."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise SystemExit(message or f"git {' '.join(args)} failed")
    return result.stdout.rstrip("\r\n")


def resolve_repo_root(path: str) -> Path:
    """Resolve the repository root for an adapter source path."""
    candidate = Path(path).expanduser().resolve()
    top_level = run_git(candidate, ["rev-parse", "--show-toplevel"])
    return Path(top_level).resolve()


def revision_range(since: str, until: str) -> str:
    """Build the git revision range used for commit selection."""
    if ".." in since:
        return since
    return f"{since}..{until}"


def list_commit_shas(repo_root: Path, rev_range: str, max_commits: int) -> list[str]:
    """Return commit SHAs in chronological order for the requested range."""
    output = run_git(
        repo_root,
        ["log", "--reverse", f"--max-count={max_commits}", "--format=%H", rev_range],
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def collect_commit(repo_root: Path, sha: str) -> GitCommit:
    """Collect metadata and touched files for one commit."""
    metadata = run_git(
        repo_root,
        ["show", "-s", "--format=%H%x1f%h%x1f%aI%x1f%an%x1f%s%x1f%b", sha],
    )
    parts = metadata.split("\x1f", 5)
    if len(parts) != 6:
        raise SystemExit(f"Unable to parse git metadata for commit {sha}")
    files_output = run_git(
        repo_root,
        ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha],
    )
    files = [line.strip() for line in files_output.splitlines() if line.strip()]
    return GitCommit(
        sha=parts[0],
        short_sha=parts[1],
        author_date=parts[2],
        author=parts[3],
        subject=parts[4],
        body=parts[5].strip(),
        files=files,
    )


def infer_repo_label(repo_root: Path) -> str:
    """Infer a readable repository label from origin or the directory name."""
    try:
        origin = run_git(repo_root, ["config", "--get", "remote.origin.url"])
    except SystemExit:
        return repo_root.name
    return origin or repo_root.name


def unique_files(commits: list[GitCommit]) -> list[str]:
    """Return touched files in first-seen order across commits."""
    seen: set[str] = set()
    files: list[str] = []
    for commit in commits:
        for path in commit.files:
            if path in seen:
                continue
            seen.add(path)
            files.append(path)
    return files


def default_session_id(repo_root: Path, rev_range: str, commits: list[GitCommit]) -> str:
    """Build a stable session id for this git import payload."""
    digest_source = "|".join([str(repo_root), rev_range, *(commit.sha for commit in commits)])
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:10]
    head = commits[-1].short_sha if commits else "empty"
    return f"git-{head}-{digest}"


def build_context(repo_root: Path, repo_label: str, rev_range: str, commits: list[GitCommit]) -> str:
    """Render git commits as a structured ingest payload."""
    commit_count = len(commits)
    file_count = len(unique_files(commits))
    first_date = commits[0].author_date[:10]
    last_date = commits[-1].author_date[:10]
    lines: list[str] = []

    append_section(
        lines,
        "Goal",
        [f"Import git commit history from {repo_label} into project memory."],
    )
    append_section(
        lines,
        "Summary",
        [
            f"Imported {commit_count} commit(s) from git range {rev_range}.",
            *[
                f"{commit.short_sha} ({commit.author_date[:10]}): {trim_sentence(commit.subject, 140)}"
                for commit in commits
            ],
        ],
    )
    append_section(
        lines,
        "Current Status",
        [
            f"Captured {commit_count} git commit(s), {file_count} touched file(s), "
            "and source evidence through codex-memory ingest-git.",
        ],
    )
    append_section(lines, "Files", unique_files(commits))
    evidence: list[str] = []
    for commit in commits:
        file_preview = ", ".join(commit.files[:5]) if commit.files else "no files listed"
        if len(commit.files) > 5:
            file_preview += f", and {len(commit.files) - 5} more"
        evidence.append(
            f"{commit.short_sha} by {commit.author} on {commit.author_date[:10]} "
            f"touched {len(commit.files)} file(s): {file_preview}."
        )
        if commit.body:
            evidence.append(f"{commit.short_sha} body: {trim_sentence(commit.body, 160)}")
    append_section(lines, "Evidence", evidence)
    append_section(
        lines,
        "Date Context",
        [
            f"Git range {rev_range}; commit dates {first_date} to {last_date}; "
            f"repository root {repo_root.as_posix()}.",
        ],
    )
    return "\n".join(lines).strip()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import git commits into daily logs")
    parser.add_argument(
        "--since",
        required=True,
        help="Git ref or revision range start. Example: HEAD~10 imports HEAD~10..HEAD.",
    )
    parser.add_argument(
        "--until",
        default="HEAD",
        help="Ending git ref when --since is not already a range.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Git repository to inspect. Defaults to the current directory.",
    )
    parser.add_argument("--max-commits", type=int, default=50, help="Maximum commits to import.")
    parser.add_argument("--session-id", help="Session id for deduplication tracking")
    parser.add_argument("--title", help="Human title for the session entry")
    parser.add_argument("--workspace", help="Workspace path associated with the commit import")
    parser.add_argument("--repo", help="Repository identifier associated with the commit import")
    parser.add_argument("--task-ref", help="Task or ticket reference associated with the commit import")
    parser.add_argument(
        "--compile",
        dest="compile",
        action="store_true",
        default=None,
        help="Run compile.py after ingest (default behavior).",
    )
    parser.add_argument(
        "--no-compile",
        dest="compile",
        action="store_false",
        default=None,
        help="Skip compile.py after ingest.",
    )
    parser.add_argument(
        "--lint",
        dest="lint",
        action="store_true",
        default=None,
        help="Run lint.py --autofix after ingest (default behavior).",
    )
    parser.add_argument(
        "--no-lint",
        dest="lint",
        action="store_false",
        default=None,
        help="Skip lint.py --autofix after ingest.",
    )
    parser.add_argument(
        "--no-compile-trigger",
        action="store_true",
        help="Disable automatic post-6PM compile trigger",
    )
    args = parser.parse_args(argv)
    if args.max_commits < 1:
        raise SystemExit("--max-commits must be at least 1")
    if args.compile is False and args.lint is True:
        raise SystemExit("Cannot lint when compile is disabled. Remove --lint or add --no-lint.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root)
    rev_range = revision_range(args.since, args.until)
    shas = list_commit_shas(repo_root, rev_range, args.max_commits)
    if not shas:
        print(f"No git commits found for range {rev_range}.")
        return 0

    commits = [collect_commit(repo_root, sha) for sha in shas]
    repo_label = args.repo or infer_repo_label(repo_root)
    session_id = args.session_id or default_session_id(repo_root, rev_range, commits)
    title = args.title or f"Git Commit Import {commits[0].short_sha}..{commits[-1].short_sha}"
    context = build_context(repo_root, repo_label, rev_range, commits)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    context_path = TMP_DIR / f"ingest-git-{session_id}.md"
    context_path.write_text(context, encoding="utf-8")

    ingest_args = [
        "--file",
        str(context_path),
        "--session-id",
        session_id,
        "--title",
        title,
        "--source-type",
        "commit-summary",
        "--workspace",
        args.workspace or repo_root.as_posix(),
        "--repo",
        repo_label,
        "--task-ref",
        args.task_ref or f"git:{rev_range}",
    ]
    if args.compile is True:
        ingest_args.append("--compile")
    elif args.compile is False:
        ingest_args.append("--no-compile")
    if args.lint is True:
        ingest_args.append("--lint")
    elif args.lint is False:
        ingest_args.append("--no-lint")
    if args.no_compile_trigger:
        ingest_args.append("--no-compile-trigger")

    from . import ingest as ingest_module

    result = ingest_module.main(ingest_args)
    if result:
        raise SystemExit(result)
    print(f"Imported {len(commits)} git commit(s) from {rev_range}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
