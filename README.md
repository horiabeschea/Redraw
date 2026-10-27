**Redraw**

# Architecture

**Redraw** is a visual learning sandbox for kids who learn differently. When a child says "I don't get it" or "this is boring", the lesson changes: the picture is redrawn in a world the child loves, the wording gets simpler or harder, and the child can tap parts of the picture to explore and be checked. Every change is logged with a reason.

Built for the Meta Global AI Developer Hackathon (Oct 27 – Nov 4, 2026). Everything in this repository was written during the hackathon; see `HACKATHON.md` for the daily build log.

## Design principles

- **The child steers.** The only inputs are what the child says, which button they press, and where they tap. There is no camera or voice-tone emotion detection. This complies with EU AI Act - running from Romania
- **Scene first, not chat.** The screen is a picture with a short caption. Text is secondary.
- **Deterministic where possible.** Tap answers are graded by geometry (point-in-mask), not by an LLM.
- **Auditable.** Every adaptation is a typed decision with a visible reason.
- **Private by default.** No child account, local storage only, Standard-mode (no-training) model IDs, and an optional mode running on open weights.

## System overview

```mermaid
flowchart LR
    Child([Child: voice, buttons, taps]) --> UI[Lesson screen]
    UI -->|audio| Proxy[Server: API proxy]
    Proxy -->|WebSocket| VT[Muse Voice Transcribe]
    VT --> Proxy --> Interp[Signal interpreter]
    UI -->|button / tap| Interp
    Interp --> Policy[Adaptation policy<br/>Muse Spark 1.3]
    Pack[(Lesson pack<br/>built by Muse Wonder)] --> Policy
    Learner[(Learner model<br/>+ why-it-changed log)] <--> Policy
    Policy --> Caption[Rewrite caption<br/>Muse Spark 1.3]
    Policy --> Image[Redraw scene<br/>Muse Image]
    Image --> SAM[Segment parts<br/>SAM 3.1]
    SAM --> Hot[Tappable hotspots]
    Caption --> UI
    Hot --> UI
    UI --> Check{Check understanding}
    Check -->|tap: point-in-mask| Learner
    Check -->|spoken answer vs answer key| Learner
```

## Components

| Component | Responsibility | Model / tech |
| --- | --- | --- |
| **Lesson screen** | Shows the scene, caption, progress, three signal buttons ("I don't get it", "Boring!", "Show me"), hotspot overlay, and read-aloud (browser speech synthesis). | Web front end |
| **API proxy** | Holds the API key, relays requests, proxies the transcription WebSocket. The key is never sent to the browser. | Small server (Python or Node), OpenAI SDK pointed at `https://api.meta.ai/v1` |
| **Speech input** | Turns the child's speech into text with keyword biasing (lesson and interest words), endpointing, and speaker labels so a parent's hint is not scored as the child's answer. | Muse Voice Transcribe (`muse-voice-transcribe-1.0`) |
| **Signal interpreter** | Maps a button press or spoken phrase to one of: `stuck`, `bored`, `got_it`. | Rules first, model fallback (Muse Spark; open-weight in private mode) |
| **Adaptation policy** | Chooses the next teaching strategy. Returns a typed `AdaptationDecision`: `{signal, strategy, target_concept, reason}`. | Muse Spark 1.3 (`muse-spark-1.3`)

## Data contracts

**Lesson pack** (`lessons/<topic>.json`), one object per step:
`caption`, `simpler_caption`, `misconception`, `correction`, `analogies` (per interest world), `image_prompts` (per world), `tap_question {prompt, target_noun}`, `say_it {prompt, answer_key}`.

**AdaptationDecision** (returned by the policy and rendered in the UI):
`signal` (`stuck | bored | got_it`), `strategy` (for example `simplify_language`, `redraw_simpler`, `raise_challenge`, `advance`), `target_concept`, `reason` (one plain sentence).

**Scene asset** (`scenes/<step>/<world>/`): the image, one mask per target noun, and the prompt that produced them.

## Meta models we plan to use

1. Lesson pack, plus the accuracy check on it **muse-wonder-1.0** reasoning: {effort: "medium"}, structured output. Run once, cache the result. Use it for the verifier pass too.
2. Opening scene and step-by-step edits **muse-image-1.0** Responses API for multi-turn edits, chaining with previous_response_id. reasoning_strength: "high" for the opening scene, "low" for redraws. Turn off enable_image_search so it can’t pull brand references.
3. Tappable parts **sam-3.1* One request per noun (“lake”, “cloud”), over the Responses API.
4. Tap grading **none** Plain geometry (point-in-mask), no model.
5. Adaptation policy **muse-spark-1.3** Structured output, reasoning: {effort: "low"} on live turns. Add a rule-based fallback.
6. Caption rewrite **muse-spark-1.3** Same model, "minimal" or "low" effort for speed.
7. Voice **muse-voice-transcribe-1.0** Realtime WebSocket wss://api.meta.ai/v1/asr/realtime for live speech, with keyword biasing. File endpoint for your test recordings.
8. Say-it grading **muse-spark-1.3** Structured output with a verdict, hint and short kind explanation.
9. Private mode (stretch) **meta-models/muse-spark-open-1026** on Baseten if we get the credits. Run the signal interpreter and say-it grading here. For Modal or local, serve **Muse-Spark-Open-816B-A42B** (NVFP4 weights) or **Muse Glimmer**. Not sure if the GPU fits

## Runtime flow

1. The child says or presses "I don't get it".
2. Speech is transcribed (if spoken) and mapped to the signal `stuck`.
3. The policy reads the signal, the current step and the learner model, and returns a decision, for example *simplify the caption and redraw a simpler scene*.
4. The caption is rewritten at a lower reading level; the scene is edited from the current picture (or a pre-made simpler variant is shown while the live one renders).
5. SAM segments the redrawn scene so parts are tappable.
6. The decision and its reason are added to the "why it changed" timeline.
7. The child answers a check (a tap or a spoken answer); the result updates the learner model and the next decision.

## Reliability and latency

- **Pre-generation:** while the child reads step *n*, the scene and masks for step *n+1* are generated and cached.
- **Golden set:** a committed set of pre-generated scenes lets the whole lesson run with no live API calls.
- **Fallbacks:** if a model call fails, the policy falls back to rules and the scene falls back to the cached variant.
- **Speed settings:** `reasoning_strength: low` for redraws, low reasoning effort on live text turns.

## Testing and verification

- **Replay file:** 20 scripted child turns with expected strategies; run after every policy or prompt change.
- **Schema validation:** every model output is validated against its JSON schema before use.
- **Geometry tests:** fixed points inside and outside each mask give the expected verdict.
- **Lesson verification:** a separate Muse Wonder pass flags scientifically misleading analogies.
- **Safety checks:** no brand names in prompts, no raw child data in logs, API key only on the server.

## Privacy and safety

No accounts and no child profile on a server; settings and progress are stored locally. Only Standard-mode model IDs are used, so content is not used to train Meta models. The product makes no medical or diagnostic claims and infers no emotions from biometric data.

# Project

Planned to use **Muse Code** for development, have to check usage conditions and if credits work with it.

## Status

| Piece | Status |
| --- | --- |
| Lesson pack (water cycle) | |
| Scene pipeline + golden set | |
| Lesson screen | |
| Tap grading | |
| Adaptation policy + replay tests | |
| Live adaptation | |
| Voice input | |
| "Why it changed" panel | |
| Say-it check | |
| Private mode (open weights) | |