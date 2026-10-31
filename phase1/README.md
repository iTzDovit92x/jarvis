# Jarvis - Phase 1: Talk to it

Push-to-talk voice chat: microphone -> Whisper -> Claude Code (Haiku) -> Kokoro voice.

## Quick way

1. Double-click **setup.bat** (once).
2. Double-click **run_jarvis.bat** whenever you want to talk to Jarvis.

## Setup by hand (same thing, if you'd rather type it)

Open PowerShell in this folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run this once first:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Run

```powershell
.venv\Scripts\Activate.ps1
python talk.py
```

The first run downloads the voice model (about 350 MB) and Whisper (about 500 MB), so it takes a few minutes.

- Press **Enter** to talk, then **Enter** again when you're done.
- Or type a message and press Enter.
- Type **q** to quit.

## Things to tweak (top of talk.py)

| Setting | What it does |
| --- | --- |
| `VOICE` | `bm_george`, `bm_lewis`, `bm_daniel` or `bm_fable` |
| `WHISPER_MODEL` | `base.en` is faster; `small.en` copes better with a Scottish accent |
| `CLAUDE_MODEL` | `haiku` for quick answers, `sonnet` for smarter but slower ones |

## Python you'll learn reading this file

- `subprocess.run` - calling another program (Claude Code) from Python
- `sounddevice.InputStream` with a callback - recording audio in the background
- `numpy` arrays - audio is just a long list of numbers
- `re` (regular expressions) - cleaning text and splitting sentences
- `pathlib.Path` - working with files and folders

## The HUD (interface)

Double-click **run_hud.bat**. It installs the extra packages the first time, starts the server and opens
http://localhost:8765 in your browser.

- Tap the **Tap to talk** button (or press **Space**), speak, tap again to send. **Esc** cancels or stops speech.
- **Quick actions** send ready-made prompts to Claude.
- **Haiku / Sonnet** at the top switches the model.
- Click a directive to tick it off.

Where the panels get their numbers:

| Panel | Source |
| --- | --- |
| Requests today, Avg reply | `data/log.jsonl`, written automatically after every request |
| Study streak, study hours, applications, roadmap, directives, AI wire | `data/hud.json`, which you edit by hand for now (skills will fill it later) |

Open `hud/index.html?demo` straight in a browser to see it with sample data, no server needed.
