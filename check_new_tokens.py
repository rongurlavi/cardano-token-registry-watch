import requests
import datetime
import os

# Repo and path we’re watching
REPO = "cardano-foundation/cardano-token-registry"
PATH = "mappings"

# How far back to look each run (in hours)
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "2"))

# GitHub token for higher rate limits (provided automatically in Actions)
TOKEN = os.getenv("GITHUB_TOKEN")

def main():
    since = (datetime.datetime.utcnow() - datetime.timedelta(hours=LOOKBACK_HOURS)).isoformat() + "Z"

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

    new_tokens = []

    for commit in commits:
        # Get details of each commit
        commit_detail = requests.get(commit["url"], headers=headers)
        commit_detail.raise_for_status()
        detail = commit_detail.json()

        for f in detail.get("files", []):
            # We're only interested in *new* JSON files under mappings/
            if (
                f.get("status") == "added"
                and f.get("filename", "").startswith("mappings/")
                and f.get("filename", "").endswith(".json")
            ):
                new_tokens.append(
                    {
                        "file": f["filename"],
                        "commit": commit["sha"],
                        "date": commit["commit"]["author"]["date"],
                    }
                )

    if not new_tokens:
        print("✅ No new token registrations in the last", LOOKBACK_HOURS, "hours.")
        return

    print("🚨 New token registrations detected in the last", LOOKBACK_HOURS, "hours:")
    for t in new_tokens:
        print(f"- {t['file']} (commit {t['commit']} at {t['date']})")
    print("\nYou can view them here:")
    print("https://github.com/cardano-foundation/cardano-token-registry/tree/master/mappings")


if __name__ == "__main__":
    main()
