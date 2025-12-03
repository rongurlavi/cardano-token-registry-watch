# Cardano Token Registry Watch

This repository provides automated monitoring of the Cardano Token Registry. It detects new token registrations, updates to existing token metadata, and tokens resembling the Midnight ecosystem (including NIGHT, CNIGHT and similar variants). Alerts are delivered through GitHub Issues and Slack notifications.

## What It Does

1. Monitors the Cardano Foundation’s official token registry under `mappings/` in the repository
   [https://github.com/cardano-foundation/cardano-token-registry](https://github.com/cardano-foundation/cardano-token-registry)

2. Detects:

   * Newly added token mapping files
   * Updated token mapping files
   * Tokens with naming, metadata or branding similarities to NIGHT and Midnight

3. Generates structured alerts containing:

   * Token subject
   * Mapping file link
   * Commit link
   * Metadata lookup link
   * NIGHT resemblance score
   * Summary of new and updated tokens

4. Sends alerts via:

   * GitHub Issues (one issue per detected batch)
   * Slack notifications containing the full enriched output

5. Provides a daily “heartbeat” workflow that sends a Slack check-in message if the registry has no changes in the past 24 hours.

## How It Works

### Main Monitoring Workflow

Runs every hour and on manual trigger.
Uses a 2-hour lookback window to identify recent registry changes.
If new or updated tokens are found, it:

* Sets workflow outputs
* Creates a GitHub Issue with full details
* Sends a Slack notification with the complete detection output

### Heartbeat Workflow

Runs once per day.
Uses a 24-hour lookback window.
If no changes were detected in the last 24 hours, it sends a Slack “monitoring active” message.

### Detection Logic

The monitoring script:

* Queries recent commits under `mappings/` via GitHub’s API
* Classifies each changed file as added (new token) or modified (updated token)
* Avoids duplicates across commits
* Fetches metadata to extract name, ticker and descriptive fields
* Applies NIGHT resemblance scoring based on:

  * Name or ticker containing night, knight, midnight, cnight, mnight
  * Similar variants inside longer words
  * Suspicious keywords (airdrop, reward, staking)

All results are printed in a structured multi-section format.

## Configuration

The workflows expect the following secrets:

* `GITHUB_TOKEN` (provided automatically)
* `SLACK_WEBHOOK_URL` (incoming webhook for alerts)
* Optionally `SLACK_WEBHOOK_TEST` for testing

Lookback windows:

* Main workflow: `LOOKBACK_HOURS=2`
* Heartbeat workflow: `LOOKBACK_HOURS=24`

## Files

* `check_new_tokens.py`: Main detection script
* `.github/workflows/token-registry-watch.yml`: Hourly workflow
* `.github/workflows/token-registry-heartbeat.yml`: Daily heartbeat workflow

## Future Enhancements

Potential extensions include:

* Storing a baseline snapshot to detect field-level metadata changes
* Automatic labeling of high-risk NIGHT-like tokens
* Separate Slack routing for high-risk alerts
* One issue per token mode
* Weekly digest summaries
* Snapshot diffing for updated fields
* Watchlist for specific subjects
