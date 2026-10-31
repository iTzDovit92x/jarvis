"""
Jarvis - Phase 1: Talk to it.

Press Enter to talk, press Enter again to stop.
Your speech goes:  microphone -> Whisper (text) -> Claude Code (answer) -> Kokoro (voice)

You can also just type a message instead of talking.

Run it with:   python talk.py
"""

import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from kokoro_onnx import Kokoro

# ---------------------------------------------------------------------------
# Settings - change these to taste
# ---------------------------------------------------------------------------
VOICE = "bm_george"        # British male voices: bm_george, bm_lewis, bm_daniel, bm_fable
SPEED = 1.05               # 1.0 = normal speed
WHISPER_MODEL = "small.en" # "base.en" is faster, "small.en" copes better with accents
CLAUDE_MODEL = "haiku"     # Tier 2 = quick answers. Try "sonnet" for smarter, slower replies
SAMPLE_RATE = 16000        # Whisper expects 16 kHz audio

HERE = Path(__file__).parent

# Personal details live in about_me.txt, which is never uploaded to GitHub (see .gitignore).
ABOUT_ME_FILE = HERE / "about_me.txt"
ABOUT_ME = ABOUT_ME_FILE.read_text(encoding="utf-8").strip() if ABOUT_ME_FILE.exists() else ""

SYSTEM_PROMPT = (
    "You are Jarvis, a personal voice assistant. " + ABOUT_ME + " "
    "Your replies are spoken out loud, so: answer in one to three short sentences, "
    "plain words, no markdown, no bullet points, no code blocks, no emoji. "
    "Be dry and witty like the film Jarvis, but get to the point."
)
MODELS = HERE / "models"
SESSION_DIR = HERE / "session"   # Claude Code keeps this chat separate from your other projects
KOKORO_FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def download_voice_model():
    """Download Kokoro's model files the first time (about 350 MB)."""
    MODELS.mkdir(exist_ok=True)
    for name, url in KOKORO_FILES.items():
        path = MODELS / name
        if not path.exists():
            print(f"Downloading {name} (one-off)...")
            urllib.request.urlretrieve(url, path)


def find_claude():
    """Find the Claude Code command, wherever it was installed."""
    claude = shutil.which("claude")
    if claude is None:
        sys.exit("Can't find Claude Code. Open a new terminal and check that 'claude --version' works.")
    return claude


# ---------------------------------------------------------------------------
# Ears: record and transcribe
# ---------------------------------------------------------------------------
def record():
    """Record from the microphone until Enter is pressed. Returns the audio as numbers."""
    chunks = []

    def on_audio(indata, frames, time_info, status):
        chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=on_audio):
        input("  Listening... press Enter when you're done.")

    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)[:, 0]


def transcribe(whisper, audio):
    """Turn audio into text with Whisper."""
    if len(audio) < SAMPLE_RATE * 0.5:   # under half a second = nothing said
        return ""
    segments, _ = whisper.transcribe(audio, language="en", beam_size=1, vad_filter=True)
    return " ".join(segment.text for segment in segments).strip()


# ---------------------------------------------------------------------------
# Brain: ask Claude Code
# ---------------------------------------------------------------------------
def ask_claude(claude, message, first_turn):
    """Send a message to Claude Code in headless mode and return its answer."""
    command = [claude, "-p", message,
               "--model", CLAUDE_MODEL,
               "--append-system-prompt", SYSTEM_PROMPT]
    if not first_turn:
        command.append("--continue")   # carry on the same conversation

    result = subprocess.run(command, cwd=SESSION_DIR, capture_output=True,
                            text=True, encoding="utf-8", timeout=180)
    if result.returncode != 0:
        return "Sorry, Claude Code gave me an error. Check the terminal."
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Voice: speak the answer
# ---------------------------------------------------------------------------
def clean_for_speech(text):
    """Strip markdown symbols so Kokoro doesn't read them out."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)   # drop code blocks
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def speak(kokoro, text):
    """Say the text out loud, one sentence at a time so it starts talking sooner."""
    for sentence in re.split(r"(?<=[.!?])\s+", clean_for_speech(text)):
        if sentence:
            samples, rate = kokoro.create(sentence, voice=VOICE, speed=SPEED, lang="en-gb")
            sd.play(samples, rate)
            sd.wait()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    print("Starting Jarvis...")
    claude = find_claude()
    download_voice_model()
    SESSION_DIR.mkdir(exist_ok=True)

    print("Loading voice and ears (first run downloads Whisper, give it a minute)...")
    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    speak(kokoro, "Jarvis online.")
    first_turn = True

    while True:
        typed = input("\n[Enter] to talk, or type a message ('q' to quit): ").strip()
        if typed.lower() in ("q", "quit", "exit"):
            speak(kokoro, "Shutting down.")
            break

        if typed:
            message = typed
        else:
            message = transcribe(whisper, record())
            if not message:
                print("  Didn't catch that.")
                continue

        print(f"  You:    {message}")
        started = time.time()
        reply = ask_claude(claude, message, first_turn)
        first_turn = False
        print(f"  Jarvis: {reply}   ({time.time() - started:.1f}s)")
        speak(kokoro, reply)


if __name__ == "__main__":
    main()
