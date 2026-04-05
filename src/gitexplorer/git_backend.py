"""Git operations wrapper using GitPython."""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import git


@dataclass
class CommitInfo:
    hash: str
    short_hash: str
    message: str
    author: str
    date: str


@dataclass
class DiffLine:
    content: str
    line_type: str          # 'added' | 'removed' | 'context'
    old_lineno: Optional[int]
    new_lineno: Optional[int]


class GitBackend:
    def __init__(self, path: Path) -> None:
        try:
            self.repo = git.Repo(path, search_parent_directories=True)
            self.repo_root = Path(self.repo.working_tree_dir)
            self.valid = True
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            self.repo = None
            self.repo_root = path
            self.valid = False

    # ------------------------------------------------------------------
    # Branches
    # ------------------------------------------------------------------

    def get_branches(self) -> list[str]:
        if not self.valid:
            return []
        branches = [b.name for b in self.repo.branches]
        try:
            current = self.repo.active_branch.name
            if current in branches:
                branches.remove(current)
                branches.insert(0, current)
        except TypeError:
            pass  # detached HEAD
        return branches

    def get_current_branch(self) -> str:
        if not self.valid:
            return ""
        try:
            return self.repo.active_branch.name
        except TypeError:
            return self.repo.head.commit.hexsha[:7]

    # ------------------------------------------------------------------
    # File tree
    # ------------------------------------------------------------------

    def get_file_tree(self, branch: str) -> list[str]:
        """Return sorted file paths relative to repo root for the given branch."""
        if not self.valid:
            return []
        try:
            ref = self.repo.branches[branch]
            return sorted(self._walk_tree(ref.commit.tree, ""))
        except (IndexError, KeyError, AttributeError):
            return []

    def _walk_tree(self, tree, prefix: str) -> list[str]:
        files: list[str] = []
        for item in tree:
            path = f"{prefix}{item.name}" if prefix else item.name
            if item.type == "tree":
                files.extend(self._walk_tree(item, path + "/"))
            else:
                files.append(path)
        return files

    # ------------------------------------------------------------------
    # Commits
    # ------------------------------------------------------------------

    def get_file_commits(self, branch: str, filepath: str) -> list[CommitInfo]:
        """All commits that touched *filepath* in *branch*, newest first."""
        if not self.valid:
            return []
        try:
            result = []
            for c in self.repo.iter_commits(branch, paths=filepath):
                result.append(CommitInfo(
                    hash=c.hexsha,
                    short_hash=c.hexsha[:7],
                    message=c.message.strip().splitlines()[0],
                    author=str(c.author),
                    date=c.committed_datetime.strftime("%Y-%m-%d %H:%M"),
                ))
            return result
        except Exception:
            return []

    def get_changed_files(self, commit_hash: str) -> list[str]:
        """Return all file paths touched by *commit_hash* (vs its first parent)."""
        if not self.valid:
            return []
        try:
            commit = self.repo.commit(commit_hash)
            if not commit.parents:
                return [item.path for item in commit.tree.traverse()
                        if item.type == "blob"]
            diff = commit.parents[0].diff(commit)
            paths: set[str] = set()
            for d in diff:
                if d.a_path:
                    paths.add(d.a_path)
                if d.b_path:
                    paths.add(d.b_path)
            return list(paths)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Content & diff
    # ------------------------------------------------------------------

    def get_file_content(self, commit_hash: str, filepath: str) -> str:
        if not self.valid:
            return ""
        try:
            blob = self.repo.commit(commit_hash).tree / filepath
            return blob.data_stream.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def get_diff(self, commit_hash: str, filepath: str) -> list[DiffLine]:
        """Unified diff between *commit_hash* and its first parent for *filepath*."""
        if not self.valid:
            return []
        try:
            commit = self.repo.commit(commit_hash)
            new_content = self.get_file_content(commit_hash, filepath)
            new_lines = new_content.splitlines(keepends=True)

            if not commit.parents:
                # First commit — everything is new
                return [
                    DiffLine(l.rstrip("\n"), "added", None, i + 1)
                    for i, l in enumerate(new_lines)
                ]

            try:
                old_blob = commit.parents[0].tree / filepath
                old_content = old_blob.data_stream.read().decode("utf-8", errors="replace")
            except KeyError:
                old_content = ""

            old_lines = old_content.splitlines(keepends=True)
            return _compute_diff(old_lines, new_lines)
        except Exception:
            return []


def _compute_diff(old: list[str], new: list[str]) -> list[DiffLine]:
    result: list[DiffLine] = []
    old_no = new_no = 1

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                result.append(DiffLine(old[i1 + k].rstrip("\n"), "context", old_no, new_no))
                old_no += 1
                new_no += 1
        elif op in ("replace", "delete"):
            for k in range(i2 - i1):
                result.append(DiffLine(old[i1 + k].rstrip("\n"), "removed", old_no, None))
                old_no += 1
            if op == "replace":
                for k in range(j2 - j1):
                    result.append(DiffLine(new[j1 + k].rstrip("\n"), "added", None, new_no))
                    new_no += 1
        elif op == "insert":
            for k in range(j2 - j1):
                result.append(DiffLine(new[j1 + k].rstrip("\n"), "added", None, new_no))
                new_no += 1

    return result


def pair_diff_lines(
    diff_lines: list[DiffLine],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Convert a flat diff into aligned left/right columns for side-by-side view.

    Returns (left_text, right_text, left_types, right_types) where every list
    has the same length.  Empty strings represent blank padding lines.
    """
    lt: list[str] = []
    rt: list[str] = []
    lty: list[str] = []
    rty: list[str] = []

    i = 0
    while i < len(diff_lines):
        dl = diff_lines[i]
        if dl.line_type == "context":
            lt.append(dl.content)
            rt.append(dl.content)
            lty.append("context")
            rty.append("context")
            i += 1
        elif dl.line_type in ("removed", "added"):
            removed: list[str] = []
            added: list[str] = []
            while i < len(diff_lines) and diff_lines[i].line_type == "removed":
                removed.append(diff_lines[i].content)
                i += 1
            while i < len(diff_lines) and diff_lines[i].line_type == "added":
                added.append(diff_lines[i].content)
                i += 1
            max_len = max(len(removed), len(added))
            for j in range(max_len):
                lt.append(removed[j] if j < len(removed) else "")
                rt.append(added[j] if j < len(added) else "")
                lty.append("removed" if j < len(removed) else "context")
                rty.append("added" if j < len(added) else "context")
        else:
            i += 1

    return lt, rt, lty, rty
