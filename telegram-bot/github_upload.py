"""
GitHub upload module — pushes a generated project to a GitHub repository.

Uses the GitHub Git Data API (Tree + Commit + Ref) to create a single
atomic commit containing all project files in a `<project_name>/` subfolder.

No extra dependencies required — uses httpx (already in requirements.txt).

Configuration (from config.py):
  GITHUB_TOKEN   — Personal Access Token with 'repo' scope
  GITHUB_REPO    — Target repository, e.g. "username/my-ai-projects"

The target repo must already exist. If it is empty (no commits), this module
will initialise it with a first commit automatically.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from config import config

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _github_headers() -> dict[str, str]:
    return {
        "Authorization": f"token {config.github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "TelegramAgentBot/1.0",
    }


async def upload_project_to_github(
    project_name: str,
    files: list[dict],  # [{"path": str, "content": str}, ...]
    description: str = "",
) -> dict[str, Any]:
    """
    Upload all project files to GitHub under `<project_name>/` folder.

    Uses the Git Data Tree API for an atomic single-commit upload:
      1. Resolve the default branch and its latest commit SHA
      2. Create a blob for each file
      3. Create a new tree containing all blobs under project_name/
      4. Create a commit pointing at the new tree
      5. Fast-forward the branch ref to the new commit

    Returns {"github_url": ..., "project_name": ..., "files_count": ..., "commit_sha": ...}
    or {"error": "..."}
    """
    if not config.github_token:
        return {"error": "GITHUB_TOKEN is not set. Configure it to enable GitHub uploads."}
    if not config.github_repo:
        return {"error": "GITHUB_REPO is not set. Configure it to enable GitHub uploads."}

    try:
        owner, repo = config.github_repo.split("/", 1)
    except ValueError:
        return {"error": f"GITHUB_REPO must be 'owner/repo', got: {config.github_repo!r}"}

    base_url = f"{GITHUB_API}/repos/{owner}/{repo}"
    headers = _github_headers()

    async with httpx.AsyncClient(timeout=60) as client:
        # ------------------------------------------------------------------
        # 1. Resolve default branch and latest commit SHA
        # ------------------------------------------------------------------
        repo_resp = await client.get(base_url, headers=headers)
        if repo_resp.status_code == 404:
            return {"error": f"Repository '{config.github_repo}' not found or token has no access."}
        if repo_resp.status_code != 200:
            return {"error": f"Cannot access repository (HTTP {repo_resp.status_code})"}

        repo_info = repo_resp.json()
        default_branch = repo_info.get("default_branch", "main")

        ref_resp = await client.get(
            f"{base_url}/git/ref/heads/{default_branch}", headers=headers
        )

        # Empty repo has no refs yet — initialise with a root commit
        if ref_resp.status_code == 404:
            init_result = await _initialise_empty_repo(
                client, base_url, headers, default_branch, owner, repo,
                project_name, files, description,
            )
            return init_result

        if ref_resp.status_code != 200:
            return {"error": f"Cannot get branch ref (HTTP {ref_resp.status_code})"}

        latest_commit_sha: str = ref_resp.json()["object"]["sha"]

        # ------------------------------------------------------------------
        # 2. Get the base tree SHA from the latest commit
        # ------------------------------------------------------------------
        commit_resp = await client.get(
            f"{base_url}/git/commits/{latest_commit_sha}", headers=headers
        )
        if commit_resp.status_code != 200:
            return {"error": f"Cannot get commit (HTTP {commit_resp.status_code})"}
        base_tree_sha: str = commit_resp.json()["tree"]["sha"]

        # ------------------------------------------------------------------
        # 3. Create blobs for each file
        # ------------------------------------------------------------------
        tree_items: list[dict] = []
        for file_info in files:
            file_path = f"{project_name}/{file_info['path']}"
            content = file_info["content"]

            blob_resp = await client.post(
                f"{base_url}/git/blobs",
                json={"content": content, "encoding": "utf-8"},
                headers=headers,
            )
            if blob_resp.status_code not in (200, 201):
                return {
                    "error": (
                        f"Cannot create blob for '{file_info['path']}' "
                        f"(HTTP {blob_resp.status_code}): {blob_resp.text[:200]}"
                    )
                }
            tree_items.append({
                "path": file_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_resp.json()["sha"],
            })

        # ------------------------------------------------------------------
        # 4. Create a new tree
        # ------------------------------------------------------------------
        tree_resp = await client.post(
            f"{base_url}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree_items},
            headers=headers,
        )
        if tree_resp.status_code not in (200, 201):
            return {"error": f"Cannot create tree (HTTP {tree_resp.status_code})"}
        new_tree_sha: str = tree_resp.json()["sha"]

        # ------------------------------------------------------------------
        # 5. Create the commit
        # ------------------------------------------------------------------
        commit_message = f"Add project: {project_name}"
        if description:
            commit_message += f"\n\n{description}"

        new_commit_resp = await client.post(
            f"{base_url}/git/commits",
            json={
                "message": commit_message,
                "tree": new_tree_sha,
                "parents": [latest_commit_sha],
            },
            headers=headers,
        )
        if new_commit_resp.status_code not in (200, 201):
            return {"error": f"Cannot create commit (HTTP {new_commit_resp.status_code})"}
        new_commit_sha: str = new_commit_resp.json()["sha"]

        # ------------------------------------------------------------------
        # 6. Update the branch ref
        # ------------------------------------------------------------------
        update_resp = await client.patch(
            f"{base_url}/git/refs/heads/{default_branch}",
            json={"sha": new_commit_sha, "force": False},
            headers=headers,
        )
        if update_resp.status_code not in (200, 201):
            return {"error": f"Cannot update branch ref (HTTP {update_resp.status_code})"}

    github_url = (
        f"https://github.com/{owner}/{repo}/tree/{default_branch}/{project_name}"
    )
    return {
        "github_url": github_url,
        "project_name": project_name,
        "files_count": len(files),
        "commit_sha": new_commit_sha[:7],
        "branch": default_branch,
    }


async def _initialise_empty_repo(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    branch: str,
    owner: str,
    repo: str,
    project_name: str,
    files: list[dict],
    description: str,
) -> dict[str, Any]:
    """
    Bootstrap an empty repository with an initial commit containing the project.
    Uses the Contents API (simpler for the first file) then Tree API for the rest.
    """
    # Create blobs
    tree_items: list[dict] = []
    for file_info in files:
        file_path = f"{project_name}/{file_info['path']}"
        content = file_info["content"]
        blob_resp = await client.post(
            f"{base_url}/git/blobs",
            json={"content": content, "encoding": "utf-8"},
            headers=headers,
        )
        if blob_resp.status_code not in (200, 201):
            return {"error": f"Cannot create blob (HTTP {blob_resp.status_code})"}
        tree_items.append({
            "path": file_path,
            "mode": "100644",
            "type": "blob",
            "sha": blob_resp.json()["sha"],
        })

    # Create root tree (no base_tree for first commit)
    tree_resp = await client.post(
        f"{base_url}/git/trees",
        json={"tree": tree_items},
        headers=headers,
    )
    if tree_resp.status_code not in (200, 201):
        return {"error": f"Cannot create initial tree (HTTP {tree_resp.status_code})"}
    tree_sha = tree_resp.json()["sha"]

    # Create initial commit
    commit_message = f"Initial commit: {project_name}"
    if description:
        commit_message += f"\n\n{description}"

    commit_resp = await client.post(
        f"{base_url}/git/commits",
        json={"message": commit_message, "tree": tree_sha, "parents": []},
        headers=headers,
    )
    if commit_resp.status_code not in (200, 201):
        return {"error": f"Cannot create initial commit (HTTP {commit_resp.status_code})"}
    commit_sha = commit_resp.json()["sha"]

    # Create the branch ref
    ref_resp = await client.post(
        f"{base_url}/git/refs",
        json={"ref": f"refs/heads/{branch}", "sha": commit_sha},
        headers=headers,
    )
    if ref_resp.status_code not in (200, 201):
        return {"error": f"Cannot create branch ref (HTTP {ref_resp.status_code})"}

    github_url = f"https://github.com/{owner}/{repo}/tree/{branch}/{project_name}"
    return {
        "github_url": github_url,
        "project_name": project_name,
        "files_count": len(files),
        "commit_sha": commit_sha[:7],
        "branch": branch,
    }
