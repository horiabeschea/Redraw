# 26.10.2026 - Start of hackathon

- [x] Claim the $150 Meta credits, add a card, set a spend-limit alert
- [x] Create the public repo with a HACKATHON.md that logs what was built each day
- [x] Request Modal credits (first 1,000 participants) - Pending
- [x] Request Baseten credits - Pending
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