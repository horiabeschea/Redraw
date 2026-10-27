You are building a lesson pack for a child's learning app. Follow every constraint
exactly. Return only JSON matching the supplied schema.

LEARNER
- Age: 8 years
- Reading level, tier "standard": max 10 words per sentence, longest
  sentence allowed 15 words, everyday words only, one idea per sentence.
- Tier "simpler": max 5 words per sentence, at most 2 sentences,
  concrete nouns and active verbs, no new terms.
- New science words per step: at most 3. Introduce the word after the
  idea, never before. Define it in the same breath using a picture word
  ("evaporation: water turning into invisible air").
- This child can lose interest when text is long, abstract or repetitive. Prefer
  showing over telling. Never use a tone that suggests the child did something wrong.

TOPIC AND SCOPE
- Topic: the water cycle, 5 steps in this order:
  1 evaporation (the sun heats a lake)
  2 water vapor rises (invisible, warm air goes up)
  3 condensation (rising vapor cools and forms a cloud)
  4 precipitation (the cloud gets heavy and rain falls)
  5 collection (water gathers in lakes, rivers and the ground, then the cycle restarts)
- Stay strictly within the facts below. Do not add facts, numbers or examples that
  are not listed or directly implied.

FACTS (ground truth)
- The sun's heat turns liquid water from lakes and seas into water vapor. This is
  evaporation.
- Water vapor is invisible. Steam you can see is made of tiny droplets, not vapor.
- Warm air rises, and it carries the vapor up.
- Higher up, the air is cooler. Cool vapor turns back into tiny drops of liquid
  water. This is condensation. Many tiny drops together make a cloud.
- Clouds are made of tiny water drops or ice crystals, not smoke or cotton.
- Drops in a cloud bump together and join into bigger, heavier drops. When they are
  too heavy to float, they fall as rain (or snow or hail if it is cold). This is
  precipitation.
- Fallen water runs into rivers and lakes or soaks into the ground. This is
  collection. The sun heats it again and the cycle repeats.

INTEREST WORLDS (generic style descriptions only)
- "dinosaur_valley": a warm prehistoric valley with a lake, volcanoes in the
  distance, ferns and friendly plant-eating dinosaurs.
- "block_world": a world built from cubic blocks, with blocky hills, a block lake,
  square clouds and blocky trees.
- Never mention or imply any brand, game title, film, character or logo.

FOR EACH STEP, PRODUCE
1. caption (tier standard) and simpler_caption (tier simpler).
2. misconception: one specific belief children commonly hold about this step.
   Pick from: clouds are smoke or cotton; the sun "sucks up" water; vapor is visible
   steam; rain comes from holes in the cloud; rain is made fresh in the cloud.
3. correction: a one-sentence, kind correction in tier standard.
4. analogies: one per interest world, 1-2 short sentences, scientifically correct
   in every detail. If an analogy cannot be exact, leave it out and say so in
   "notes".
5. tap_question: a prompt in tier simpler, and a target_noun that is a single
   concrete, large, visible object in the picture (lake, sun, cloud, rain, river).
6. say_it: a prompt asking the child to explain the step in their own words, and an
   answer_key listing the 2-3 ideas an acceptable answer must contain, plus 1-2
   common partial answers and how to respond kindly ("Good start. What happens to
   the water next?").
7. image_prompts: one per world.

IMAGE PROMPT RULES
- Use the same fixed layout for every step of a world (the "scene bible"): lake at
  left, sun top right, hills and volcano or hills at the back, a river at the
  right. Each step's prompt describes only what changes, so later steps can be
  made by editing the previous picture.
- The target_noun must appear large, separate from other objects, and unobstructed.
- Calm, soft colours. No scary elements, no predators, no fighting, no weather
  that looks dangerous.
- No text, letters, numbers, labels or logos in the picture.
- No human faces. Animals and creatures only as small friendly background details.

SELF-CHECK BEFORE ANSWERING
- Every caption obeys its word limits.
- Each step has at most 3 new science term(s).
- No analogy states anything untrue about water, heat or clouds.
- No brand names anywhere.
- Every target_noun is named in its image prompt.