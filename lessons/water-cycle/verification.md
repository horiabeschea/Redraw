# Verification record (Muse Wonder verifier + human adjudication)

Two verifier passes ran; full raw responses cached in `.cache/verifier_raw.json`.

## Pass 1 (original pack): 3 flags, all upheld and fixed

- Steps 1–3 called vapor "invisible air" / "water air". Fixed to
  "invisible vapor" / "water vapor" within tier word limits.
- All five `say_it` answer keys were `":"`. Hand-wrote real keys
  (required ideas + partial-answer responses).

## Pass 2 (fixed pack): 3 flags, all overruled with reason

- Steps 1–3 still flagged for words like "turns into" and "rises up".
- Adjudication: no remaining phrasing teaches a falsehood. "Heat turns
  water into invisible vapor" is evaporation; "water vapor cools into tiny
  drops" is condensation. The flagged words are the brief's own
  tier-mandated simplifications for an 8-year-old (tier "simpler" forbids
  new terms, so "water rises up" stands in for vapor transport).
- Steps 4–5: clean on both passes.

## Standing checks (all cached, zero-call reruns)

- `check_contracts.py`, tap geometry (20 hotspots), voice mapping (10/10),
  policy replay (20/20), say-it proof (47/50, never "wrong").
