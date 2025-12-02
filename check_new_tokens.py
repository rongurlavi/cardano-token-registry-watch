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


def get_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return headers


def extract_subject_from_filename(filename: str) -> str:
    """
    Convert mappings/<subject>.json to <subject>
    """
    base = filename
    if "/" in base:
        base = base.split("/", 1)[1]
    if base.endswith(".json"):
        base = base[:-5]
    return base


def fetch_metadata_from_raw(raw_url: str) -> dict:
    """
    Fetch the JSON metadata for a single mapping file.
    Returns {} on error.
    """
    if not raw_url:
        return {}
    try:
        resp = requests.get(raw_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # CIP-26 entries usually have a "name", "ticker", "description", "url"
        # If nested, adapt here later
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def compute_night_score(text: str, is_new: bool) -> int:
    """
    Basic NIGHT resemblance scoring.
    Looks for 'night', 'knight', 'midnight', 'mnight', 'cnight'
    anywhere in the text (as substring, any case).
    Also bumps score for suspicious marketing terms.
    """
    if not text:
        text = ""
    t = text.lower()

    score = 0

    # Brand-related patterns
    brand_patterns = ["night", "knight", "midnight", "mnight", "cnight"]
    if any(p in t for p in brand_patterns):
        score += 40

    # Suspicious marketing / scammy language
    suspicious_keywords = [
        "airdrop",
        "airdrops",
        "reward",
        "rewards",
        "bonus",
        "double",
        "stake",
        "staking",
        "yield",
        "free",
    ]
    if any(k in t for k in suspicious_keywords):
        score += 20

    # Slight bump if the token is newly added
    if is_new:
        score += 10

    # Cap at 100
    return min(score, 100)


def classify_night_level(score: int) -> str:
    if score >= 50:
        return "high"
    elif score >= 20:
        return "medium"
    elif score > 0:
        return "low"
    else:
        return "none"


def main():
    # Use timezone aware UTC to avoid deprecation warnings
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    since_dt = now_utc - datetime.timedelta(hours=LOOKBACK_HOURS)
    since = since_dt.isoformat()

    url = f"https://api.github.com/repos/{REPO}/commits"
    params = {
        "path": PATH,
        "since": since,
        "per_page": 50,
    }
    headers = get_headers()

    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    commits = resp.json()

    # Use dicts keyed by filename to avoid duplicates across commits
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
            raw_url = f.get("raw_url")

            if not (
                filename.startswith(f"{PATH}/")
                and filename.endswith(".json")
            ):
                continue

            commit_sha = commit["sha"]
            commit_date = commit["commit"]["author"]["date"]

            # New token mappings (file added)
            if status == "added":
                if filename not in new_tokens:
                    new_tokens[filename] = {
                        "file": filename,
                        "commit": commit_sha,
                        "date": commit_date,
                        "raw_url": raw_url,
                    }
                # Ensure it is not treated as "updated" if we already consider it new
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
                        "raw_url": raw_url,
                    }

    # Enrich with subject, metadata and NIGHT scoring
    def enrich_token_info(token_dict: dict, is_new: bool):
        for info in token_dict.values():
            filename = info["file"]
            subject = extract_subject_from_filename(filename)
            metadata = fetch_metadata_from_raw(info.get("raw_url"))

            name = metadata.get("name", "")
            ticker = metadata.get("ticker", "")
            description = metadata.get("description", "")
            url_field = metadata.get("url", "")

            text_to_scan = " ".join(
                str(x)
                for x in [subject, name, ticker, description, url_field]
                if x
            )
            score = compute_night_score(text_to_scan, is_new=is_new)
            level = classify_night_level(score)

            info["subject"] = subject
            info["name"] = name
            info["ticker"] = ticker
            info["url"] = url_field
            info["night_score"] = score
            info["night_level"] = level

    if new_tokens:
        enrich_token_info(new_tokens, is_new=True)
    if updated_tokens:
        enrich_token_info(updated_tokens, is_new=False)

    if not new_tokens and not updated_tokens:
        print(
            "✅ No new or updated token registrations in the last",
            LOOKBACK_HOURS,
            "hours.",
        )
        return

    total_changes = len(new_tokens) + len(updated_tokens)

    # Header line with the 🚨 marker for the workflow
    print(
        f"🚨 New or updated Cardano token registrations detected in the last {LOOKBACK_HOURS} hours"
    )
    print(f"Total changed: {total_changes}")
    print(f"New tokens: {len(new_tokens)}")
    print(f"Updated tokens: {len(updated_tokens)}")
    print()

    # New token mappings section
    print("New token mappings:")
    if new_tokens:
        for t in new_tokens.values():
            subject = t.get("subject", "")
            name = t.get("name", "")
            ticker = t.get("ticker", "")
            score = t.get("night_score", 0)
            level = t.get("night_level", "none")

            # Single hyphen line per token so existing COUNT logic still works
            print(f"- {subject} ({t['file']})")
            print(f"  Commit: https://github.com/{REPO}/commit/{t['commit']}")
            print(f"  Mapping file: https://github.com/{REPO}/blob/master/{t['file']}")
            print(f"  Metadata: https://tokens.cardano.org/metadata/{subject}")
            if name or ticker:
                print(f"  Name/Ticker: {name} / {ticker}")
            if score > 0:
                print(f"  NIGHT resemblance: {score}/100 ({level})")
            print()
    else:
        print("  None in this window\n")

    # Updated token mappings section
    print("Updated token mappings:")
    if updated_tokens:
        for t in updated_tokens.values():
            subject = t.get("subject", "")
            name = t.get("name", "")
            ticker = t.get("ticker", "")
            score = t.get("night_score", 0)
            level = t.get("night_level", "none")

            print(f"- {subject} ({t['file']})")
            print(f"  Commit: https://github.com/{REPO}/commit/{t['commit']}")
            print(f"  Mapping file: https://github.com/{REPO}/blob/master/{t['file']}")
            print(f"  Metadata: https://tokens.cardano.org/metadata/{subject}")
            if name or ticker:
                print(f"  Name/Ticker: {name} / {ticker}")
            if score > 0:
                print(f"  NIGHT resemblance: {score}/100 ({level})")
            print()
    else:
        print("  None in this window\n")

    print("You can view all mappings here:")
    print(
        "https://github.com/cardano-foundation/cardano-token-registry/tree/master/mappings"
    )


if __name__ == "__main__":
    main()
