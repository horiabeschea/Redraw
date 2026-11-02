# 26.10.2026 - Start of hackathon

- [x] Claim the $150 Meta credits, add a card, set a spend-limit alert
- [x] Create the public repo with a HACKATHON.md that logs what was built each day
- [x] Request Modal credits (first 1,000 participants) - Pending
- [x] Request Baseten credits - Received
- [x] Install Muse Code 
    ``` sh
    curl -fsSL https://dev.meta.ai/install.sh | sh
    ```
- [x] Make one real API call to muse-spark-1.3 from Romania
- [x] Post in #intros with the one-line pitch - Decided not to atm

# 27.10.2026 - MVP documentation phase 

- [x] Define architecture
- [] Understand what Meta model fits where - read documentation, need practice with the models
- [x] Write a lesson
- [x] Use **Meta wonder 1.0** to generate the first lesson outline and support media
- [x] Use **Muse image 1.0** to generate first lesson helper images
- [x] Use **Muse code** to generate scripts for producing, caching and loading of the first lesson
- [x] Create an implementation plan

# 27.10.2026 - MVP implementation phase

- [x] Restore pack cache; add `AdaptationDecision`/`LearnerState` contracts with checker
- [x] Verifier pass: fixed "invisible air" analogies (steps 1-3), hand-wrote say-it answer keys
- [x] Vendored official SAM mask decoder; segmented 10 scenes (10 SAM calls + 5 concept retries)
- [x] Hand boxes for 5 SAM-zero scenes (D9 fallback); all 20 hotspots done (10 normal + 10 simpler)
- [x] Generated 10 simpler scene variants; golden set complete (20 images, cached, replayable offline)
- [x] Lesson screen + tap grading (geometry, 20/20) + policy replay (20/20 live) + live wiring with latency log
- [x] Voice file endpoint + mapping tests (10/10); say-it grading wired with proof (47/50, never "wrong")
- [x] Verifier pass 2 + adjudication record; full suite re-verified offline with zero API calls
- [x] Baseten connector (private mode): same SDK, strict-first schemas, per-model caches, header toggle, `/api/backend` switch; probed live (policy + say-it ok)
- [x] Geyed-out future worlds, child-view default, single private control in setup
- [x] Layered captions: setup profile → one Spark rewrite → code checks (limits, glossary, key term, banned phrases) → version-keyed cache; screen overrides captions; all tiers cached and checked
- [x] Large-text + read-aloud toggles wired, sentence-by-sentence stuck mode, analogy line + tap explanations, child-collapsed timeline; fixed settings() crash that blanked the page
- [x] Correct-tap interaction: dilated masks (10, offline), teal glow, kind verdict + cached analogy, read-aloud/chime gating, say-it offer, prefetch, miss chain (pulse → reveal → advance), mastered tracking
- [x] State machine from the policy spreadsheet: 9 states, full transition table, Spark picks inside the allowed set, cache keyed by state; committed unit tests for every transition (144 assertions)
- [x] Got-it button opens the tap check; Back to the lesson exits the detour where it started; prompt pill shows only where an answer is requested
- [x] Correct taps and good answers advance under short praise with a filling progress bar; the child sees praise and hints only, grading reasons stay in the jury log
- [x] Waiting spinner on the pressed control; progress fill exempt from calm mode; transcription clears once the reply lands
- [x] Mic debugging: live level meter, clip length in messages, server errors surfaced; fixed missing TLS trust roots and top-level transcript parsing
- [x] World handling: primary world with session override, rotation on simplify/challenge entries, fallback chain with named jury entries, Back-button nudge after 6 explore taps
- [x] Failure diagnostics instead of silent dead taps: tap errors, policy HTTP status, and missing-asset names land in the jury timeline; missing masks fall back to hand boxes
- [x] Layout fixes: scene capped to the viewport, jury panel scrolls instead of stretching the page, bar buttons disable instead of vanishing, caption card holds its size
- [x] uv packaging (pyproject + lockfile, fresh-env verified) and README setup/run docs with keys table and test commands

# 29.10.2026 - Windows setup, parent report, lesson builder

- [x] Setup now works on Windows too, not just Mac and Linux. There is a keys template to copy from, and the instructions show both shells. Checked that the keys actually load and the secret file stays out of git.
- [x] Parents get a report: what the child mastered, where extra explanations helped, which worlds clicked, plus kind suggestions for home. It is built on demand behind the grown-ups gate, describes lesson moments rather than judging the kid, and falls back to a plain summary with no internet.
- [x] Parents can now build a lesson on any topic: type the topic and the facts, the app writes the five steps and checks the science, the parent reads and fixes the wording, saves a version, and builds the pictures for the chosen worlds. New lessons appear in a picker. Everything was tested without spending credits.
- [x] Two small fixes along the way: captions in Private mode now use the right model, and the picture-segmenting script loads without needing the network library.
- [ ] Still open: a real end-to-end run with live models for the video, which needs keys and a working Python environment.

# 02.11.2026 - Demo video takes

- [x] Rebuilt .venv on Python 3.13 (openai 3.39 + certifi per lockfile); full offline suite green
- [x] Fixed caption fallback-cache poisoning (offline/failed rewrites never cached) + regression test (builder: 66 assertions)
- [x] Proved every model path live: policy 3.3s, say-it ok/not_yet, report 3.7s, volcanoes Wonder build 107s, all verifier verdicts yes
- [x] Generated 3 Pixar-style key frames (muse-image-1.0) + 2 app screenshots into video_frames/
- [x] Saved src/record_takes.py: 9 scripted Playwright takes (all passing), run with the server up
- [ ] Still open: live-mic transcript take needs the deployed WS proxy; final 3:00 assembly

- [x] Takes v2: visible cursor + tap captions + glide motion (src/record_takes.py); 9/9 passing
- [x] Two 5s Pixar clips (page-push, cloud-tap): 3 Muse Image frames each, zoompan + xfade via ffmpeg
- [x] Sidecar .srt captions for all takes and clips (toggle at edit time)
- [x] Portable ffmpeg 9.0.2 installed user-level for assembly work
