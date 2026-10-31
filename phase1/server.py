"""
Jarvis HUD server.

Serves the HUD in your browser and connects it to the voice loop from talk.py:
    browser button -> microphone -> Whisper -> Claude Code -> Kokoro -> speakers
and streams Jarvis's state (idle / listening / working / speaking) back to the orb.

Start it with run_hud.bat. It opens http://localhost:8765 for you.
"""

import asyncio
import json
import re
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

import memory   # Phase 2: your vault of markdown files
import router   # Phase 2: instant answers without AI
import talk     # the ears, brain and voice from Phase 1

HERE = Path(__file__).parent
HUD_PAGE = HERE / "hud" / "index.html"
DATA = HERE / "data"
LOG_FILE = DATA / "log.jsonl"      # one line per request: the HUD's vitals come from here
OLD_PANELS = DATA / "hud.json"     # Phase 1's panel file; its to-do list moves into the vault once
PORT = 8765


# ---------------------------------------------------------------------------
# Jarvis: holds the models and the current state
# ---------------------------------------------------------------------------
class Jarvis:
    def __init__(self):
        self.clients = set()
        self.loop = None
        self.state = "idle"
        self.model = talk.CLAUDE_MODEL
        self.first_turn = True
        self.busy = False
        self.stream = None
        self.chunks = []
        self.mic_level = 0.0
        self.stop_speaking = False
        self.history = []          # transcript lines for browsers that connect later

        self.claude = talk.find_claude()
        talk.download_voice_model()
        talk.SESSION_DIR.mkdir(exist_ok=True)
        DATA.mkdir(exist_ok=True)
        old = json.loads(OLD_PANELS.read_text(encoding="utf-8")).get("directives") if OLD_PANELS.exists() else None
        memory.setup(old)
        print("Loading voice and ears...")
        self.kokoro = talk.Kokoro(str(talk.MODELS / "kokoro-v1.0.onnx"), str(talk.MODELS / "voices-v1.0.bin"))
        self.whisper = talk.WhisperModel(talk.WHISPER_MODEL, device="cpu", compute_type="int8")

    # ----- talking to the browser -------------------------------------------
    async def send(self, message):
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)

    def send_from_thread(self, message):
        """Worker threads (speech) use this to reach the browser."""
        asyncio.run_coroutine_threadsafe(self.send(message), self.loop)

    async def set_state(self, state):
        self.state = state
        await self.send({"type": "state", "state": state})

    async def say_line(self, who, text, secs=None, tier=None):
        line = {"type": "transcript", "who": who, "text": text}
        if secs is not None:
            line["secs"] = secs
        if tier is not None:
            line["tier"] = tier
        self.history = (self.history + [line])[-30:]
        await self.send(line)

    # ----- ears ---------------------------------------------------------------
    def _on_audio(self, indata, frames, time_info, status):
        self.chunks.append(indata.copy())
        self.mic_level = float(np.sqrt(np.mean(indata ** 2)))

    async def start_listening(self):
        if self.busy or self.stream:
            return
        self.chunks = []
        self.stream = sd.InputStream(samplerate=talk.SAMPLE_RATE, channels=1,
                                     dtype="float32", callback=self._on_audio)
        self.stream.start()
        await self.set_state("listening")
        while self.stream:                        # feed the orb your voice level
            await self.send({"type": "level", "value": min(1.0, self.mic_level * 14)})
            await asyncio.sleep(0.06)

    async def stop_listening(self, cancel=False):
        if not self.stream:
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None
        if cancel:
            await self.set_state("idle")
            return
        audio = np.concatenate(self.chunks)[:, 0] if self.chunks else np.zeros(0, np.float32)
        self.busy = True
        await self.set_state("working")
        text = await asyncio.to_thread(talk.transcribe, self.whisper, audio)
        self.busy = False
        if not text:
            await self.send({"type": "toast", "text": "Didn't catch that"})
            await self.set_state("idle")
            return
        await self.handle(text, source="voice")

    # ----- brain + voice -------------------------------------------------------
    async def handle(self, text, source="typed", label=None):
        if self.busy:
            return
        self.busy = True
        try:
            await self.say_line("you", label or text)
            started = time.time()
            reply, tier = router.route(text), 1          # Tier 1: answer from the vault, instantly
            if reply is None:                              # Tier 2: ask Claude, with your context
                await self.set_state("working")
                talk.CLAUDE_MODEL = self.model
                reply = await asyncio.to_thread(talk.ask_claude, self.claude, text,
                                                self.first_turn, memory.context())
                self.first_turn, tier = False, 2
            secs = round(time.time() - started, 1)
            await self.say_line("jarvis", talk.clean_for_speech(reply), secs, tier)
            self.log(label or text, reply, secs, source, tier)
            await self.send({"type": "stats", "data": stats()})
            await self.send({"type": "panels", "data": memory.panels()})
            await self.set_state("speaking")
            await asyncio.to_thread(self.speak, reply)
            await self.set_state("idle")
        except Exception as error:
            print("Error:", error)
            await self.send({"type": "toast", "text": f"Error: {error}"})
            await self.set_state("error")
            await asyncio.sleep(2)
            await self.set_state("idle")
        finally:
            self.busy = False

    def speak(self, text):
        """Speak sentence by sentence, sending the voice level to the orb as it goes."""
        self.stop_speaking = False
        for sentence in re.split(r"(?<=[.!?])\s+", talk.clean_for_speech(text)):
            if self.stop_speaking or not sentence:
                break
            samples, rate = self.kokoro.create(sentence, voice=talk.VOICE, speed=talk.SPEED, lang="en-gb")
            if self.stop_speaking:
                break
            sd.play(samples, rate)
            started, length = time.time(), len(samples) / rate
            while not self.stop_speaking and (elapsed := time.time() - started) < length:
                i = int(elapsed * rate)
                window = samples[i:i + 1024]
                level = float(np.sqrt(np.mean(window ** 2))) if len(window) else 0.0
                self.send_from_thread({"type": "level", "value": min(1.0, level * 6)})
                time.sleep(0.05)
            sd.stop()
        self.send_from_thread({"type": "level", "value": 0})

    async def cancel(self):
        if self.stream:
            await self.stop_listening(cancel=True)
        elif self.state == "speaking":
            self.stop_speaking = True
            sd.stop()

    # ----- memory --------------------------------------------------------------
    def log(self, text, reply, secs, source, tier):
        row = {"ts": datetime.now().isoformat(timespec="seconds"), "tier": tier,
               "model": self.model if tier == 2 else None,
               "source": source, "secs": secs, "you": text, "jarvis": reply}
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        memory.log_request(text, reply, tier, secs)        # and a readable copy in today's daily note


# ---------------------------------------------------------------------------
# Live vitals from the request log
# ---------------------------------------------------------------------------
def stats():
    """Work out the live vitals from the request log."""
    rows = []
    if LOG_FILE.exists():
        for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    today = datetime.now().date().isoformat()
    todays = [r for r in rows if r["ts"].startswith(today)]
    hourly = [0] * 24
    for r in todays:
        hourly[int(r["ts"][11:13])] += 1
    claude_rows = [r for r in todays if r.get("tier", 2) == 2]
    avg = round(sum(r["secs"] for r in claude_rows) / len(claude_rows), 1) if claude_rows else None
    return {"today": len(todays), "instant": len(todays) - len(claude_rows), "avg": avg, "hourly": hourly,
            "recent": [r["secs"] for r in rows[-20:] if r.get("tier", 2) == 2], "total": len(rows)}


# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------
jarvis: Jarvis = None


@asynccontextmanager
async def lifespan(app):
    jarvis.loop = asyncio.get_running_loop()
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    print(f"\nJarvis HUD running at http://localhost:{PORT}  (close this window to stop)\n")
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def page():
    return FileResponse(HUD_PAGE)


@app.websocket("/ws")
async def socket(ws: WebSocket):
    await ws.accept()
    jarvis.clients.add(ws)
    await ws.send_json({"type": "hello", "state": jarvis.state, "model": jarvis.model,
                        "panels": memory.panels(), "stats": stats(), "transcript": jarvis.history})
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "talk_start":
                asyncio.create_task(jarvis.start_listening())
            elif kind == "talk_stop":
                asyncio.create_task(jarvis.stop_listening())
            elif kind == "cancel":
                await jarvis.cancel()
            elif kind == "text" and msg.get("text"):
                asyncio.create_task(jarvis.handle(msg["text"], label=msg.get("label")))
            elif kind == "model" and msg.get("model") in ("haiku", "sonnet"):
                jarvis.model = msg["model"]
                await jarvis.send({"type": "model", "model": jarvis.model})
            elif kind == "directive":
                memory.toggle_directive(int(msg["index"]))
                await jarvis.send({"type": "panels", "data": memory.panels()})
    except WebSocketDisconnect:
        jarvis.clients.discard(ws)


if __name__ == "__main__":
    print("Starting Jarvis...")
    jarvis = Jarvis()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
