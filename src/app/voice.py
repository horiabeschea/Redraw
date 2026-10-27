"""Voice input: file transcription + phrase-to-signal mapping.

transcribe_wav(audio_bytes, keywords, cache_dir=None, refresh=False)
posts one multipart call to POST /asr/transcribe (WAV only) with vocabulary
biasing. Results cache by audio hash: identical clips never re-spend.

phrase_to_signal(text) maps child speech to stuck/bored/got_it (rules;
model fallback lives in the policy layer, not here).
"""

import hashlib
import json
import os
import urllib.request

TRANSCRIBE_URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL = "muse-voice-transcribe-1.0"

KEYWORDS = ["evaporation", "water vapor", "condensation", "precipitation",
            "collection", "lake", "cloud", "rain", "river",
            "Triceratops", "dinosaur"]

SIGNAL_PHRASES = [
    (("don't get it", "dont get it", "do not get it", "don't understand",
      "confusing", "too hard", "what does it mean"), "stuck"),
    (("boring", "bored", "too easy", "again"), "bored"),
    (("show me", "got it", "i know", "next", "i did it"), "got_it"),
]


def phrase_to_signal(text):
    lowered = text.lower()
    for phrases, signal in SIGNAL_PHRASES:
        if any(p in lowered for p in phrases):
            return signal
    return None


def _multipart(request_json, audio_bytes):
    boundary = "redraw-voice-boundary"
    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; '
                 f'name="request"\r\nContent-Type: application/json\r\n\r\n'
                 f'{request_json}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; '
                 f'name="audio"; filename="clip.wav"\r\n'
                 f'Content-Type: audio/wav\r\n\r\n'.encode() + audio_bytes
                 + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def transcribe_wav(audio_bytes, keywords=None, cache_dir=None, refresh=False):
    digest = hashlib.sha256(audio_bytes).hexdigest()[:16]
    cache_path = (os.path.join(cache_dir, f"voice_{digest}.json")
                  if cache_dir else None)
    if cache_path and os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f), True
    request_json = json.dumps({"model": MODEL, "audioEncoding": "WAV",
                               "mode": "PUSH_TO_TALK",
                               "keywords": keywords or KEYWORDS})
    body, boundary = _multipart(request_json, audio_bytes)
    req = urllib.request.Request(
        TRANSCRIBE_URL, data=body,
        headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}",
                 "Accept": "application/json",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)
    turns = result.get("turns", [])
    text = " ".join(t.get("transcript", t.get("text", "")) for t in turns)
    out = {"text": text, "turns": turns, "keywords": keywords or KEYWORDS}
    if cache_path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    return out, False
