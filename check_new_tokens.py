import requests
import datetime
import os

# Repo and path we are watching
REPO = "cardano-foundation/cardano-token-registry"
PATH = "mappings"

# How far back to look each run (in hours)
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "24"))

# GitHub token for higher rate limits (provided automatically in Actions)
TOKEN = os.getenv("GITHUB_TOKEN")


def main():
    # Use timezone aware UTC time to avoid deprecation warnings
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    since = (now_utc - datetime.timedelta(hours=LOOKBACK_HOURS)).isoformat()

    url = f"https://api.github.com/repos/{REPO}/commits"
    params = {
        "path": PATH,
        "since": since,
        "per_page": 50,
    }
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    commits = resp.json()

    # Use dicts keyed by filename to avoid duplicates
    new_tokens = {}
    updated_tokens = {}

    for commit in commits:
        # Get details of each commit
        commit_detail = requests.get(commit["url"], headers=headers)
        commit_detail.raise_for_status()
        detail = commit_detail.json()

        for f in detail.get("files", []):
            filename = f.get("filename", "")
            status = f.get("status")

            if not (
                filename.startswith(f"{PATH}/")
                and filename.endswith(".json")
            ):
                continue

            commit_sha = commit["sha"]
            commit_date = commit["commit"]["author"]["date"]

            # New token mappings (file added)
            if status == "added":
                # If a file is newly added, treat it as new even if it was also modified later
                if filename not in new_tokens:
                    new_tokens[filename] = {
                        "file": filename,
                        "commit": commit_sha,
                        "date": commit_date,
                    }
                # Ensure it is not considered "updated" if we have seen it as new
                if filename in updated_tokens:
                    updated_tokens.pop(filename, None)

            # Updated token mappings (file modified)
            elif status == "modified":
                # Only treat as updated if we have not already classified it as new
                if filename not in new_tokens and filename not in updated_tokens:
                    updated_tokens[filename] = {
                        "file": filename,
                        "commit": commit_sha,
                        "date": commit_date,
                    }

    if not new_tokens and not updated_tokens:
        print(
            "✅ No new or updated token registrations in the last",
            LOOKBACK_HOURS,
            "hours.",
        )
        return

    print(
        "🚨 New or updated token registrations detected in the last",
        LOOKBACK_HOURS,
        "hours:",
    )

    if new_tokens:
        print("\nNew token mappings:")
        for t in new_tokens.values():
            print(f"- {t['file']} (commit {t['commit']} at {t['date']})")

    if updated_tokens:
        print("\nUpdated token mappings:")
        for t in updated_tokens.values():
            print(f"- {t['file']} (commit {t['commit']} at {t['date']})")

    print("\nYou can view them here:")
    print(
        "https://github.com/cardano-foundation/cardano-token-registry/tree/master/mappings"
    )


if __name__ == "__main__":
    main()
