You are building a lesson pack for a child's learning app. Follow every constraint
exactly. Return only JSON matching the supplied schema.

LEARNER
- Age: 7 years
- Reading level, tier "standard": max 10 words per sentence, longest
  sentence allowed 10 words, everyday words only, one idea per sentence.
- Tier "simpler": max 5 words per sentence, at most 2 sentences,
  concrete nouns and active verbs, no new terms.
- New science words per step: at most 1. Introduce the word after the
  idea, never before. Define it in the same breath using a picture word.
- This child can lose interest when text is long, abstract or repetitive. Prefer
  showing over telling. Never use a tone that suggests the child did something wrong.

TOPIC AND SCOPE
- Topic: volcanoes. Derive exactly 5 ordered steps from the facts below.
  Name each step with a short snake_case step_name.
- Stay strictly within the facts below. Do not add facts, numbers or examples that
  are not listed or directly implied.

FACTS (ground truth, chosen by the parent)
- Magma is hot melted rock under the ground.
- Lava is magma that reaches the surface.
- Volcanoes erupt lava, ash and gas.
- Lava cools into solid rock.
- Some eruptions explode, others flow gently.

INTEREST WORLDS (generic style descriptions only)
- "dinosaur_valley": a warm prehistoric valley with a lake, volcanoes in the distance, ferns and friendly plant-eating dinosaurs.
- "block_world": a world built from cubic blocks, with blocky hills, a block lake, square clouds and blocky trees.
- Never mention or imply any brand, game title, film, character or logo.

FOR EACH STEP, PRODUCE
1. key_terms: the 1-3 science words this step teaches (plain words or short phrases).
2. caption (tier standard) and simpler_caption (tier simpler).
3. misconception: one specific belief children commonly hold about this step.
4. correction: a one-sentence, kind correction in tier standard.
5. analogies: one per interest world, 1-2 short sentences, scientifically correct
   in every detail. If an analogy cannot be exact, leave it out and say so in
   "notes".
6. tap_question: a prompt in tier simpler, and a target_noun that is a single
   concrete, large, visible object in the picture.
7. say_it: a prompt asking the child to explain the step in their own words, and an
   answer_key listing the 2-3 ideas an acceptable answer must contain, plus 1-2
   common partial answers and how to respond kindly.
8. image_prompts: one per world.

IMAGE PROMPT RULES
- First describe a fixed layout for every step of a world (the "scene bible",
  named places for the important objects). Each step's prompt describes only
  what changes, so later steps can be made by editing the previous picture.
- The target_noun must appear large, separate from other objects, and unobstructed.
- Calm, soft colours. No scary elements, no predators, no fighting, no weather
  that looks dangerous.
- No text, letters, numbers, labels or logos in the picture.
- No human faces. Animals and creatures only as small friendly background details.

SELF-CHECK BEFORE ANSWERING
- Every caption obeys its word limits.
- Each step has at most 1 new science term(s), listed in key_terms.
- No analogy states anything untrue about the topic.
- No brand names anywhere.
- Every target_noun is named in its image prompt.