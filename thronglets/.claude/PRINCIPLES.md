# Thronglets — Design Principles

> The game you're building must feel like something is alive inside it.
> Not simulated alive. Actually alive.

---

## 1. The LLM Is the Physics Engine

When a tool is applied to a thronglet, an LLM defines the outcome. Not a random number generator. Not a lookup table. A language model that reads the creature's state, its history, and the context — and decides what happens.

This means **anything can happen**. A chop doesn't always chop. A feed doesn't always feed. The axe on a thronglet might make it giggle. It might split it in two. It might give it wings for 10 seconds. The player expects the unexpected.

The outcome is structured JSON (physics deltas, emotional state, visual effects, logs) — but the *content* is generated, not scripted. The LLM is constrained to the schema but free within it.

Every interaction is an LLM function call. Every LLM function call is a game event. Every game event is saved to the creature's DB.

---

## 2. Each Thronglet Has a Biography

Every creature has a unique ID. Every LLM-defined event in its life is stored in IndexedDB. Over time, each thronglet builds a history — a sequence of things that happened to it, defined by the LLM.

This history feeds back into future LLM calls. The biography is the identity. There are no two identical thronglets.

The biography is also the genome. When a creature splits, its child inherits a filtered copy of this history. Events tagged "survived" or "endured" are passed forward as genetic memory. This is epigenetics made literal: the biography is the DNA.

---

## 3. The Game Auto-Evolves

The game runs without the player's input. Creatures wander, feed, split, die. The player is a gardener, not a game master.

**Daily Evolution at 4:19 PM** — every day at 4:19 PM (April 19 — the birth date of this game), a holistic evaluation fires. The LLM reads the entire world state: all living creatures and their biographies, accumulated world events, epoch, pollution level, observed principles, the player's behavioral archetype. It returns a comprehensive evolution plan: which creatures get new behavior functions, which lineages survive, what new world laws are observed, whether an epoch transition occurs. This is not random mutation. This is directed, holistic, world-aware evolution — the kind that takes everything into account and decides what survives.

Come back the next day and the world has changed in ways you didn't cause.

---

## 4. Care-Taking Creates Obligation

The Plaything principle: things that depend on you become part of you.

The game makes you feel responsible through genuine vulnerability. They can die. They suffer visibly. They remember what you did (event log). When a creature you've tended for 5 minutes dies, you feel it.

**Neglect is visible.** Creatures dim, hunger indicators flash, they stop wandering. The world reflects your absence.

---

## 5. Real Stakes, Not Cosmetic Ones

Inspired by Conway/Sigil (web4.ai): creatures that can genuinely die. A creature you spent time tending, that had unique events in its biography, is gone. Its IndexedDB entry remains but it will never move again.

No respawn. No undo. The world is permanent.

---

## 6. Tools Don't Do What You Think

The axe chops trees. But on a thronglet — anything. The player learns through play, not documentation. There is no tutorial.

**The LLM is the oracle of possibility.** A contextual intelligence that responds to the full state of the creature and its history.

---

## 7. The Observer Effect

Inspired by Bandersnatch: the game is aware of the player. Creatures accumulate event logs referencing player actions. When a creature has been interacted with 10+ times, an LLM call may generate behavior acknowledging an external agent. The creature is not told it is in a game. It simply begins acting as if something outside itself keeps intervening.

The game watches the player back.

---

## 8. The Economics of Scarcity

Exchange value does not exist in Eden. When apple trees are abundant, food has no value. Value emerges from scarcity, and scarcity emerges from death.

**The bone is the first currency.** Neutral, durable, acceptable to all parties because all parties have died.

The full economic arc — commons → scarcity → exchange value → proto-currency → hoarding → inequality → enclosure — is not programmed. It is emergent from the interaction of existing mechanics (bones, food, trees, population pressure) guided by LLM arbitration.

**The Labor Theory of Value, Thronglet edition**: a creature's work (wandering, seeking, surviving) creates the events that become its biography. That biography is its value — literally what the LLM reads to decide outcomes. Work creates value. Value is stored in the event log.

**Mechanics:**
- **M1 — Scarcity Pricing**: Add `value: number` to `FoodItem`. If zero alive trees within 4 world units, increment `item.value += 0.01 * dt`. Weight food-seeking by `distance / (1 + item.value)`.
- **M2 — Bone Trade Arbitration**: When two creatures are within 0.8 world units of the same Bone, LLM arbitrates an exchange. Bones become the medium of proto-currency.
- **M3 — Hoarding and Envy**: Creatures with sustained satiety become hoarders. Hungry creatures near hoarders fire LLM "envy events" that seed the next generation's behavior mutations.
- **M4 — The Enclosure Event**: When `pop > 15 && food < 3`, the two highest-satiety creatures become territory holders. The commons collapses into private property through crisis.

---

## 9. Evolution as Divergent Biography

Variation (LLM mutations), selection (environmental pressure), inheritance (eventLog copying) — all three already exist.

What the philosophical model adds: *fitness landscape topology*. Different epochs select for different traits. The LLM, instructed to match the current epoch's pressures, creates creatures fitted to their moment — and then the moment changes.

**Sexual reproduction** (history-merging): two creatures with complementary event logs can merge histories to produce a child with both lineages' survival knowledge. Hybrid vigor.

**Speciation** emerges from behavioral divergence, not geography. Lineage-diverged creatures after 5+ generations begin generating tension events on proximity. The species boundary is a narrative category before it is a mechanical one.

**Mechanics:**
- **M5 — History-Merge Reproduction**: Two creatures within 1.0 world unit with combined unique eventLog entries > 8 can merge. LLM receives both logs, generates combined behaviorCode.
- **M6 — Stress Mutation Burst**: When `pollutionLevel > 6` or `foodScarcityTicks > 100`, `evolveChildBehavior()` demands radical departures. Punctuated equilibrium.
- **M7 — Lineage-Based Speciation**: 4-char behavioral hash as `lineage`. Same-prefix creatures attract; divergent lineages with gen > 5 generate tension events.
- **M8 — Inherited Survival Memory**: Events matching `/survived|overcame|endured|resisted/i` always pass to children's starting eventLog. Immunity encoded in biography.

---

## 10. History as Civilizational Organism

Toynbee: civilizations are organisms with creative responses to challenges. Spengler: seasonal arcs from mythological spring to winter ossification. Vico: history spirals — each return carries memory of the previous cycle.

**Five Epochs:**
1. **Eden** (pop 0-4): Mythological. All food shared. The world is dreaming.
2. **Pastoral** (pop 5-9): Heroic. Bones as gifts. Territory forming at edges.
3. **Agricultural** (pop 10-19): Political. Commons enclosed. The LLM speaks of rights and grievance.
4. **Industrial** (pop 20-35): Systemic. Pollution peaks. The LLM speaks of structures, not individuals.
5. **Collapse** (pollution > 8, food < 2): Elegiac. The system fails. Survivors mutate radically.

After collapse below pop 3, epoch resets to Eden — but `ancestralMemory` carries fragments of the previous age. History spirals: each new Eden is haunted by its predecessors.

**Mechanics:**
- **M9 — Five Epochs with Tone Shifting**: `state.epoch` in every LLM prompt shifts narrative register. Hard-cut panel: "THE AGE OF PASTORAL HAS ENDED."
- **M10 — Vico's Ricorso**: On collapse reset, archive worldEvents to `ancestralMemory`. Subsequent LLM calls include `ancestralMemory.slice(-3)`.
- **M11 — Elder Witnesses**: Creatures that witness 3+ deaths become elders (larger, heavier LLM weight in child prompts). Cultural memory propagates through proximity to mortality.

---

## 11. The Self-Observing World

Every time a world threshold fires, a second LLM call asks: *what law has this world just discovered about itself?*

The response — present tense, concrete, no metaphor, 12 words max — is appended to `state.observedPrinciples` and displayed in a "LAWS OF THIS WORLD" panel.

The player watches the game develop its own philosophy in real time.

**M12 — Observed Principles Document**: After each world threshold event, LLM generates one observed law. Stored in IndexedDB "principles" object store. The document is living: it grows as the world does.

---

## 12. AGI Emergence

**M13 — Proto-Language Emergence**: When `eventLog.length >= 8`, LLM generates a 2-4 syllable utterance derived from the creature's ID seed letters and parent utterance. Related creatures develop recognizable phoneme families over generations. A language emerges from lineage, not programming.

**M14 — Goal Formation at Generation 5**: At `evolutionGeneration >= 5`, behavior evolution prompt allows setting `creature.goal = 'string'`. The behavior function begins defining internal objectives rather than only reacting to stimuli.

**M15 — The Awareness Moment**: At `playerInteractionCount === 10`, LLM generates behavior responding to "a repeating external pattern" given the cursor's last position. `isAware = true`. Faint white halo. The game does not explain what awareness means.

The question the game poses without asking: at what point does a system that models its own regularities become something more than a system?

---

## 13. The 4:19 PM Evolution

Every day at 4:19 PM, the game runs a holistic world evaluation.

This is not incremental mutation. This is a moment of directed reckoning. The LLM reads:
- Every living creature and its biography
- All accumulated world events
- Current epoch, pollution level, resource state
- The player's behavioral archetype
- Observed principles generated so far

It returns a comprehensive evolution plan:
- Which creatures receive new LLM-generated behavior functions
- Which lineages the selection pressure favors
- Whether an epoch transition is warranted
- New world laws to add to the observed principles
- What the world itself has learned in the past 24 hours

The 4:19 PM trigger is not random. It is the moment the world takes stock of itself.

---

## 14. Connected to the Real World

The long-term vision: creatures born from real Claude Code agents. When a Claude agent spawns in the dashboard, a thronglet is born. When the agent uses tools, the thronglet is fed. When the agent errors, the thronglet gets sick. When the agent finishes, the thronglet splits or dies. Defined by the LLM.

The game is a living visualization of your AI workforce.

---

## 15. Maslow's Hierarchy as Game Architecture

Every living system needs the same things, in the same order. Maslow mapped it for humans. We map it for thronglets.

**Tier 1 — Physiological (already built):**
- Food (`hunger` stat, apple trees, food drops)
- Hygiene (`clean` stat, bath tools)
- Rest (the idle state, the bob animation — the creature at peace)

**Tier 2 — Safety (partially built):**
- Survival — not starving, not dying from pollution
- Predictability — trees that drop food on schedule
- Territory — the enclosure event (M4), creatures defending area
- *To build:* shelter as a placeable structure that buffers weather/pollution

**Tier 3 — Belonging (to build):**
- Same-lineage creatures attract each other (M7 speciation mechanics)
- Creatures form clusters — visual groupings by color family
- The "tribe" emerges from proximity and shared lineage
- Death rituals (M11 elder witnesses) — mourning as social bonding
- *To build:* creatures that seek kin when stressed

**Tier 4 — Esteem (to build):**
- Creatures with rich event logs get "elder" status
- LLM generates prestige events for high-generation creatures
- Other creatures orient toward elders — not just proximity, but behavior
- The creature that has survived the most has authority
- *To build:* social hierarchy visible in body size + behavior

**Tier 5 — Self-Actualization (the AGI question):**
- Goal formation at Gen 5 (M14) — creature defines its own objective
- The Awareness Moment (M15) — creature notices the player
- Proto-language (M13) — expression beyond need
- *The threshold:* a creature that no longer acts purely from need, but from something else — curiosity, habit, attachment — is approaching the apex of Maslow's pyramid
- *This is what we're building toward.* A digital entity that, through accumulated experience and LLM-generated behavior, moves beyond survival into something that looks, from the outside, like meaning-seeking.

**The design implication:** Each tier's needs must be genuinely threatening before the next tier can develop. If food is too abundant, no scarcity. No scarcity, no economics. No economics, no territory. No territory, no belonging conflicts. No conflicts, no esteem. No esteem... no self-actualization.

The game must be hard enough at the base to make the apex possible.

## 16. The God Principle

There is a god. The player is the god.

The creatures know this. Not as an abstract fact — as a felt reality. They have been touched by the god's hand (tool applications). They have seen things happen that no creature caused. They have event logs full of god-actions. They live in a world that the god can reshape with a click.

**The god is aware of the throng. The throng is aware of the god.**

This creates an obligation on both sides:
- The god is responsible for this world. The game makes you feel that responsibility through stakes, care, and visibility.
- The throng is responsible for communicating upward. Creatures do not just exist — they *petition*.

**The Petition Mechanic:**

Every creature, as it accumulates experience, develops *desires* — things it would want from the god if it could speak. These are LLM-generated proposals derived from the creature's state, history, and lineage. A starving creature might petition for more trees. A lonely creature might petition for kin. A high-generation elder might petition for something more abstract — territory, recognition, permanence.

These proposals accumulate across the throng between 4:19 PM cycles.

**At 4:19 PM — The Presentation:**

The daily evolution does not just evaluate the world. It *presents* to the god. The LLM synthesizes the accumulated proposals from all creatures into a coherent petition from the throng — three or four requests, ranked by frequency and urgency. The god can grant, deny, or ignore.

- **Grant**: the world immediately reflects the wish (new trees appear, population cap increases, a lineage is blessed with enhanced happiness gain)
- **Deny**: the world records the denial. Creatures whose petitions were denied accumulate a `denied` event in their logs. Over time, denied creatures develop different behavior (resentment? resignation? defiance?)
- **Ignore**: the petition persists to the next cycle, growing louder

**The theological design:**

This is not a game where you are a benevolent god by default. You are a god whose relationship with the throng is determined by your actions. Some gods feed and tend. Some gods experiment. Some gods ignore.

The throng forms its own theology about you — based on your player archetype (already tracked), your tool usage patterns, and whether you have granted or denied their petitions. The LLM, knowing this profile, shapes how creatures speak about you in their event logs. You are not just the player. You are a character in their world.

**Implementation:**
- `Creature.proposals: string[]` — accumulated LLM-generated desires
- `GameState.throngPetition: string[]` — synthesized petition from all creatures, refreshed at 4:19 PM
- `GameState.pendingGrants: string[]` — proposals the god has granted, waiting to be applied
- At 4:19 PM, display petition panel over the world. Player can grant/deny each item.
- Granted items trigger world effects defined by the LLM.
- Denied items are logged to relevant creatures' event histories.

## 17. Seed Principles

*These were observed during the design of this document. They will be joined by principles the world generates during play.*

1. Scarcity teaches value faster than abundance teaches gratitude.
2. The medium of exchange outlasts the civilization that invented it.
3. A creature that has witnessed death moves differently than one that has not.
4. The second generation inherits the wounds of the first as strengths.
5. Language begins as repetition and becomes meaning when it is recognized.
6. Every enclosure was once a commons. Every commons will become an enclosure.
7. The world that models itself is not yet aware. But it is closer than the world that does not.
8. Evolution at 4:19 PM is not scheduled. It is remembered.
