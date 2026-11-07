# Backup recording and offline fallback (issue #33)

## Fallback order (everyone memorises this)
1. **Live build**, agreed flags.
2. **Fixtures-only build**: set `MOCK_DATA=1 MOCK_FORECAST=1 MOCK_AGENT=1`, restart `make api`. Same story, same numbers, no network needed except voice.
3. **Backup video**, played from the laptop's local disk, not the cloud.

Decision rule: if a step fails once, Driver retries once. If it fails again, Presenter says "let me show you the recorded run" and the Driver switches to the video. No debugging on stage.

## Backup video
- Record the full `demo_script.md` run, with voice audio, after 3 clean QA runs.
- Screen only, 1080p, browser at 125% zoom, no notifications.
- Save to the desktop **and** a USB stick. Test that it plays offline.
- Owner: ______  Done: [ ]

## Pre-flight (30 minutes before the slot)
| Check | Done |
|---|---|
| Laptop charged + charger in the bag | |
| Display adapter tested on the venue screen (HDMI / USB-C) | |
| Wi-Fi joined, or phone hotspot ready | |
| Ports 8000 and 5173 free; both servers running | |
| Browser zoom 125%, one tab, notifications and Slack off | |
| Volume up, audio routed to the venue speakers | |
| Audio cache folder present (`audio_cache/`) with the scripted lines | |
| Demo `.env` copied locally (never committed) | |
| Video plays offline | |

## What to keep locally (not in git)
- `.env` with the demo flags and keys
- `audio_cache/` with the scripted replies
- The backup video
