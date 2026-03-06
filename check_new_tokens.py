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
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def extract_value(field):
    """
    Extract the CIP-26 field value.
    Example:
    {"sequenceNumber": 0, "value": "NIGHT", "signatures": [...]} -> "NIGHT"
    """
    if isinstance(field, dict):
        return field.get("value", "")
    return field if isinstance(field, str) else ""


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

    brand_patterns = ["night", "knight", "midnight", "mnight", "cnight"]
    if any(p in t for p in brand_patterns):
        score += 40

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

    if is_new:
        score += 10

    return min(score, 100)


def classify_night_level(score: int) -> str:
    if score >= 80:
        return "high"
    elif score >= 40:
        return "med"
    else:
        return "low"


def short_subject(subject: str, head: int = 6, tail: int = 6) -> str:
    if not subject or len(subject) <= head + tail + 1:
        return subject
    return f"{subject[:head]}…{subject[-tail:]}"


def slack_link(url: str, text: str) -> str:
    return f"<{url}|{text}>"


def main():
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

    new_tokens = {}
    updated_tokens = {}

    for commit in commits:
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

            if status == "added":
                if filename not in new_tokens:
                    new_tokens[filename] = {
                        "file": filename,
                        "commit": commit_sha,
                        "date": commit_date,
                        "raw_url": raw_url,
                    }
                if filename in updated_tokens:
                    updated_tokens.pop(filename, None)

            elif status == "modified":
                if filename not in new_tokens and filename not in updated_tokens:
                    updated_tokens[filename] = {
                        "file": filename,
                        "commit": commit_sha,
                        "date": commit_date,
                        "raw_url": raw_url,
                    }

    def enrich_token_info(token_dict: dict, is_new: bool):
        for info in token_dict.values():
            filename = info["file"]
            subject = extract_subject_from_filename(filename)
            metadata = fetch_metadata_from_raw(info.get("raw_url"))

            name = extract_value(metadata.get("name"))
            ticker = extract_value(metadata.get("ticker"))
            description = extract_value(metadata.get("description"))
            url_field = extract_value(metadata.get("url"))

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
            info["description"] = description
            info["url"] = url_field
            info["night_score"] = score
            info["night_level"] = level
            info["commit_url"] = f"https://github.com/{REPO}/commit/{info['commit']}"
            info["metadata_url"] = f"https://tokens.cardano.org/metadata/{subject}"

    if new_tokens:
        enrich_token_info(new_tokens, is_new=True)
    if updated_tokens:
        enrich_token_info(updated_tokens, is_new=False)

    if not new_tokens and not updated_tokens:
        print(f"✅ No new or updated token registrations in the last {LOOKBACK_HOURS} hours.")
        return

    total_changes = len(new_tokens) + len(updated_tokens)

    print(f"🚨 Cardano Token Registry Update")
    print()
    print(f"Total changed: {total_changes}")
    print(f"New tokens: {len(new_tokens)}")
    print(f"Updated tokens: {len(updated_tokens)}")
    print()

    if new_tokens:
        print("NEW")
        for t in new_tokens.values():
            subject = t.get("subject", "")
            name = t.get("name", "(missing)") or "(missing)"
            ticker = t.get("ticker", "(missing)") or "(missing)"
            score = t.get("night_score", 0)
            level = t.get("night_level", "low")
            commit_short = t["commit"][:7]

            # Keep one hyphen line per token so existing COUNT logic still works
            print(f"- {name} ({ticker})")
            print(f"  Subject: {short_subject(subject)}")
            print(f"  Score: {score}/100 ({level})")
            print(f"  Commit: {slack_link(t['commit_url'], commit_short)}")
            print(f"  Metadata: {slack_link(t['metadata_url'], 'View')}")
            print()

    if updated_tokens:
        print("UPDATED")
        for t in updated_tokens.values():
            subject = t.get("subject", "")
            name = t.get("name", "(missing)") or "(missing)"
            ticker = t.get("ticker", "(missing)") or "(missing)"
            score = t.get("night_score", 0)
            level = t.get("night_level", "low")
            commit_short = t["commit"][:7]

            print(f"- {name} ({ticker})")
            print(f"  Subject: {short_subject(subject)}")
            print(f"  Score: {score}/100 ({level})")
            print(f"  Commit: {slack_link(t['commit_url'], commit_short)}")
            print(f"  Metadata: {slack_link(t['metadata_url'], 'View')}")
            print()
    else:
        print("UPDATED")
        print("  None")
