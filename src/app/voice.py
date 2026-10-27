"""Voice input: file transcription + phrase-to-signal mapping.

transcribe_wav(audio_bytes, keywords, cache_dir=None, refresh=False)
posts one multipart call to POST /asr/transcribe (WAV only) with vocabulary
biasing. Results cache by audio hash: identical clips never re-spend.

phrase_to_signal(text) maps child speech to stuck/bored/explore (policy
signals) plus ready/back (deterministic lesson events, handled client-side
with no model call). Unmapped speech returns None and is graded as a say-it
answer; low-confidence input never triggers a transition by itself.
"""

import hashlib
import json
import os
import ssl
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
    (("show me", "show me more"), "explore"),
    (("got it", "i got it", "i'm ready", "im ready"), "ready"),
    (("back to the lesson", "go back", "back"), "back"),
]


def extract_text(result):
    """Transcript text from a transcribe response.

    The API returns the transcript top-level ("transcript"); per-turn
    transcripts are the fallback. Empty turns with a top-level transcript
    is the normal success shape, not a failure.
    """
    top = (result.get("transcript") or "").strip()
    if top:
        return top
    turns = result.get("turns", [])
    return " ".join(t.get("transcript", t.get("text", "")) for t in turns
                    ).strip()


def phrase_to_signal(text):
    lowered = text.lower()
    for phrases, signal in SIGNAL_PHRASES:
        if any(p in lowered for p in phrases):
            return signal
    return None


def _ssl_context():
    """Verified context backed by certifi when installed.

    python.org macOS builds ship no trust roots, so a bare urlopen fails
    with CERTIFICATE_VERIFY_FAILED; certifi (pip install certifi) fixes it
    with no env vars. Falls back to the platform default otherwise.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
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
    ctx = _ssl_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        result = json.load(resp)
    text = extract_text(result)
    turns = result.get("turns", [])
    out = {"text": text, "turns": turns, "keywords": keywords or KEYWORDS,
           "raw": result}
    if cache_path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    return out, False
