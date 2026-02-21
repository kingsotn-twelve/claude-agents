/**
 * Thronglets — retro pixel-art god-game inspired by Black Mirror: Plaything
 *
 * Isometric world with yellow fuzzy creatures that need feeding, cleaning,
 * and playing with. They multiply when happy. They die when neglected.
 * The population grows exponentially. You can't keep up. That's the point.
 *
 * v2: Self-evolving behavior, player profiling, bone harvesting, world events.
 */

// ── TYPES ──────────────────────────────────────────────────

interface Creature {
  x: number;
  y: number;
  vx: number;
  vy: number;
  hunger: number;
  clean: number;
  happiness: number;
  age: number;
  alive: boolean;
  diedAt: number;
  splitTimer: number;
  state: 'idle' | 'walking' | 'eating' | 'bathing' | 'playing' | 'dying';
  stateTimer: number;
  animFrame: number;
  size: number;
  bobPhase: number;
  // LLM outcome fields
  id?: string;
  eventLog?: string[];
  visualEffect?: string;
  visualEffectTimer?: number;
  // food-seeking
  targetFood?: FoodItem | null;
  // Self-evolving behavior (Feature 1)
  behaviorCode?: string;
  behaviorFn?: Function;
  playerProfile?: string[];
  evolutionGeneration?: number;
  lineage?: string;
  proposals?: string[];   // desires the creature wants to petition the god for
  deniedCount?: number;   // how many petitions have been denied
}

interface FoodItem {
  x: number;
  y: number;
  vx: number;
  vy: number;
  vz: number;   // vertical velocity (world-space Z / height)
  z: number;    // current height above ground
  eaten: boolean;
  spawnedAt: number;
}

interface Tree {
  x: number;
  y: number;
  type: 'apple';
  health: number;
  regrowTimer: number;
}

interface Building {
  id: string;
  x: number;
  y: number;
  name: string;
  description: string;
  effect: string;           // "happiness+5_nearby" | "food_spawn" | "pollution_reduce" | "shelter"
  pixels: Array<{x: number; y: number; color: string}>;  // 8x8 pixel art
  builtBy: string;          // creature id
  builtAt: number;          // tick
}

// Feature 3: Bone harvesting
interface Bone {
  x: number;
  y: number;
  age: number;
}

type ToolType = 'feed' | 'clean' | 'play' | 'chop';

interface InteractionEvent {
  type: 'creature_creature' | 'creature_bone' | 'creature_tree' | 'creature_food_contest';
  actorId: string;
  targetId: string;
  lastFiredAt: number;  // state.tick when last fired
}

interface GameState {
  creatures: Creature[];
  trees: Tree[];
  food: FoodItem[];
  bones: Bone[];
  buildings: Building[];
  resources: { wood: number; gems: number; bones: number };
  tool: ToolType;
  tick: number;
  camera: { x: number; y: number };
  mouseWorld: { x: number; y: number };
  mouseScreen: { x: number; y: number };
  lastEvent: string;
  lastEventTimer: number;
  // Feature 2: Player profile
  playerProfile: string;
  // Feature 4: World events & pollution
  pollutionLevel: number;
  worldEvents: string[];
  lastThresholdPop: number;
  // Civilizational epoch (0=Eden, 1=Pastoral, 2=Agricultural, 3=Industrial, 4=Collapse)
  epoch: 0 | 1 | 2 | 3 | 4;
  // Self-observed principles
  observedPrinciples: string[];
  // Ancestral memory persists across epoch resets
  ancestralMemory: string[];
  // Observer panel state
  observer: {
    fn: string;
    fnArgs: string[];
    target: string;
    targetDetail: string[];
    hoverComment: string;
    hoverCommentAge: number;
    output: string[];
    outputAge: number;
  };
  // Interaction cooldowns: `${id1}:${id2}` → lastFiredTick
  interactionCooldowns: Map<string, number>;
  // God/petition system
  throngPetition: Array<{ text: string; urgency: number; lineage: string }>;
  petitionVisible: boolean;
  pendingGrants: string[];
  godRelationship: 'unknown' | 'benevolent' | 'capricious' | 'absent' | 'feared';
  // Compute budget system
  computeBudget: number;
  tokensSpent: number;
  computeRating: number;
}

// ── CONSTANTS ──────────────────────────────────────────────

const TILE_W = 48;
const TILE_H = 24;
const WORLD_W = 16;
const WORLD_H = 16;

const COLORS = {
  grass: ['#2d5a27', '#3a7d32', '#4a9a3c', '#3a7d32'] as const,
  dirt: '#8b6914',
  treeTrunk: '#5c3a1e',
  treeLeaf: '#2d8a2e',
  creature: '#ffd700',
  creatureHappy: '#ffe44d',
  creatureSad: '#cc9900',
  creatureDead: '#666666',
  food: '#ff4444',
  pollution: '#8833aa',
} as const;

// Derive a unique hue from a lineage string — visual speciation
function lineageHue(lineage: string | undefined): number {
  if (!lineage) return 45;
  // Use multiple chars spread across full range for better distribution
  let hash = 0;
  for (let i = 0; i < lineage.length; i++) {
    hash = ((hash << 5) - hash + lineage.charCodeAt(i)) & 0xFFFFFF;
  }
  const raw = Math.abs(hash) % 300; // 0-299
  // Map to hues that contrast with green grass (avoid 90-150)
  // 0-89 → 0-89 (red, orange, yellow)
  // 90-149 → 210-269 (blue, indigo — skip grass)
  // 150-299 → 270-420 mod 360 (purple, magenta, red again)
  if (raw < 90) return raw;
  if (raw < 150) return 210 + (raw - 90);
  return (270 + (raw - 150)) % 360;
}

function lineageColor(lineage: string | undefined, lightness = 60): string {
  const h = lineageHue(lineage);
  return `hsl(${h}, 85%, ${lightness}%)`;
}

// ── GAME STATE ─────────────────────────────────────────────

const state: GameState = {
  creatures: [],
  trees: [],
  food: [],
  bones: [],
  buildings: [],
  resources: { wood: 0, gems: 0, bones: 0 },
  tool: 'feed',
  tick: 0,
  camera: { x: 0, y: 0 },
  mouseWorld: { x: 0, y: 0 },
  mouseScreen: { x: 0, y: 0 },
  lastEvent: '',
  lastEventTimer: 0,
  playerProfile: '',
  pollutionLevel: 0,
  worldEvents: [],
  lastThresholdPop: 0,
  epoch: 0,
  observedPrinciples: [
    'Scarcity teaches value faster than abundance teaches gratitude.',
    'The world that models itself is not yet aware. But it is closer.',
  ],
  ancestralMemory: [],
  observer: {
    fn: 'idle()',
    fnArgs: [],
    target: 'world',
    targetDetail: [],
    hoverComment: '',
    hoverCommentAge: 999,
    output: [],
    outputAge: 999,
  },
  interactionCooldowns: new Map(),
  throngPetition: [],
  petitionVisible: false,
  pendingGrants: [],
  godRelationship: 'unknown',
  computeBudget: 50000,
  tokensSpent: 0,
  computeRating: 50,
};

// Feature 2: Player action tracking
const playerActions: string[] = [];

// ── FACTORIES ──────────────────────────────────────────────

function createCreature(wx: number, wy: number): Creature {
  return {
    x: wx, y: wy, vx: 0, vy: 0,
    hunger: 100, clean: 100, happiness: 100,
    age: 0, alive: true, diedAt: 0, splitTimer: 0,
    state: 'idle', stateTimer: 0, animFrame: 0,
    size: 1, bobPhase: Math.random() * Math.PI * 2,
    id: Math.random().toString(36).slice(2, 9),
    eventLog: [],
    visualEffect: 'normal',
    visualEffectTimer: 0,
    targetFood: null,
    evolutionGeneration: 0,
    lineage: Math.random().toString(36).slice(2, 6), // random 4-char lineage seed
  };
}

function createTree(wx: number, wy: number): Tree {
  return { x: wx, y: wy, type: 'apple', health: 3, regrowTimer: 0 };
}

function createFood(wx: number, wy: number): FoodItem {
  return {
    x: wx,
    y: wy,
    vx: (Math.random() - 0.5) * 0.5,
    vy: (Math.random() - 0.5) * 0.5,
    vz: 2 + Math.random() * 1.5,  // initial upward velocity (dropped from hand)
    z: 1.5,                         // start slightly above ground
    eaten: false,
    spawnedAt: state.tick,
  };
}

// ── ISO PROJECTION ─────────────────────────────────────────

function worldToScreen(wx: number, wy: number): { x: number; y: number } {
  return {
    x: (wx - wy) * (TILE_W / 2) + state.camera.x,
    y: (wx + wy) * (TILE_H / 2) + state.camera.y,
  };
}

function screenToWorld(sx: number, sy: number): { x: number; y: number } {
  const cx = sx - state.camera.x;
  const cy = sy - state.camera.y;
  return {
    x: (cx / (TILE_W / 2) + cy / (TILE_H / 2)) / 2,
    y: (cy / (TILE_H / 2) - cx / (TILE_W / 2)) / 2,
  };
}

function screenToWorldTile(sx: number, sy: number): { x: number; y: number } {
  const w = screenToWorld(sx, sy);
  return { x: Math.floor(w.x), y: Math.floor(w.y) };
}

// ── DRAWING ────────────────────────────────────────────────

function drawPixelRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, color: string): void {
  ctx.fillStyle = color;
  ctx.fillRect(Math.floor(x), Math.floor(y), w, h);
}

function drawIsoDiamond(ctx: CanvasRenderingContext2D, sx: number, sy: number, color: string): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(sx, sy - TILE_H / 2);
  ctx.lineTo(sx + TILE_W / 2, sy);
  ctx.lineTo(sx, sy + TILE_H / 2);
  ctx.lineTo(sx - TILE_W / 2, sy);
  ctx.closePath();
  ctx.fill();
}

function drawTree(ctx: CanvasRenderingContext2D, sx: number, sy: number, tree: Tree): void {
  // Trunk
  drawPixelRect(ctx, sx - 3, sy - 28, 6, 20, COLORS.treeTrunk);
  // Canopy
  const leafColor = tree.health > 0 ? COLORS.treeLeaf : '#555';
  ctx.fillStyle = leafColor;
  ctx.beginPath();
  ctx.arc(sx, sy - 34, 14, 0, Math.PI * 2);
  ctx.fill();
  // Darker leaf layer for depth
  ctx.fillStyle = '#1a6e1f';
  ctx.beginPath();
  ctx.arc(sx + 3, sy - 30, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = leafColor;
  ctx.beginPath();
  ctx.arc(sx - 2, sy - 36, 11, 0, Math.PI * 2);
  ctx.fill();
  // Apples
  if (tree.type === 'apple' && tree.health > 0) {
    drawPixelRect(ctx, sx - 6, sy - 38, 4, 4, COLORS.food);
    drawPixelRect(ctx, sx + 4, sy - 32, 4, 4, COLORS.food);
    drawPixelRect(ctx, sx - 1, sy - 28, 4, 4, COLORS.food);
  }
}

function drawFood(ctx: CanvasRenderingContext2D, item: FoodItem): void {
  if (item.eaten) return;

  const { x: sx, y: sy } = worldToScreen(item.x, item.y);

  // Height offset — food appears to float above ground
  // In isometric view, height (z) translates to negative screen y
  const screenYOffset = item.z * TILE_H;

  const scale = 1 + item.z * 0.1;
  const radius = 5 * scale;

  // Shadow on ground (drawn first, beneath everything)
  const shadowAlpha = Math.max(0.1, 0.5 - item.z * 0.08);
  ctx.globalAlpha = shadowAlpha;
  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  ctx.beginPath();
  ctx.ellipse(sx, sy, radius * 0.9, radius * 0.4, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;

  // Apple body
  ctx.fillStyle = COLORS.food;
  ctx.beginPath();
  ctx.arc(sx, sy - screenYOffset, radius, 0, Math.PI * 2);
  ctx.fill();

  // Highlight
  ctx.fillStyle = 'rgba(255,200,200,0.6)';
  ctx.beginPath();
  ctx.arc(sx - radius * 0.3, sy - screenYOffset - radius * 0.2, radius * 0.35, 0, Math.PI * 2);
  ctx.fill();

  // Stem
  ctx.strokeStyle = '#5c3a1e';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(sx, sy - screenYOffset - radius);
  ctx.lineTo(sx + 2, sy - screenYOffset - radius - 4);
  ctx.stroke();
}

function drawCreature(ctx: CanvasRenderingContext2D, sx: number, sy: number, creature: Creature, tick: number): void {
  if (!creature.alive) return;

  const bob = Math.sin(creature.bobPhase + tick * 0.08) * 2;
  let cy = sy + bob;

  // Body color: derived from lineage (visual speciation) — darkens when unhappy
  let bodyColor: string;
  if (creature.hunger < 20 || creature.clean < 20 || creature.happiness < 20) {
    bodyColor = lineageColor(creature.lineage, 30); // dark/sad
  } else {
    const lightness = 50 + (creature.happiness / 100) * 20; // 50-70% based on mood
    bodyColor = lineageColor(creature.lineage, lightness);
  }

  let s = 12 + Math.min(creature.age / 200, 4);
  const vEffect = creature.visualEffect || 'normal';
  const vTimer = creature.visualEffectTimer || 0;

  // Visual effects: grow / shrink scale
  if (vEffect === 'grow') s *= 1.5;
  if (vEffect === 'shrink') s *= 0.5;

  ctx.save();

  // Visual effect: spin — rotate around creature center
  if (vEffect === 'spin') {
    const angle = (30 - vTimer) * 0.3;
    ctx.translate(sx, cy - s);
    ctx.rotate(angle);
    ctx.translate(-sx, -(cy - s));
  }

  // Visual effect: flash_yellow halo
  if (vEffect === 'flash_yellow') {
    ctx.fillStyle = 'rgba(255, 255, 0, 0.35)';
    ctx.beginPath();
    ctx.arc(sx, cy - s, s * 1.6, 0, Math.PI * 2);
    ctx.fill();
  }

  // Visual effect: flash_red overlay (drawn after body)
  // Body
  ctx.fillStyle = bodyColor;
  ctx.beginPath();
  ctx.ellipse(sx, cy - s, s, s * 0.8, 0, 0, Math.PI * 2);
  ctx.fill();

  if (vEffect === 'flash_red') {
    ctx.fillStyle = 'rgba(255, 0, 0, 0.45)';
    ctx.beginPath();
    ctx.ellipse(sx, cy - s, s, s * 0.8, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  // Eyes
  const eyeY = cy - s * 0.4;
  drawPixelRect(ctx, sx - s * 0.35, eyeY, 3, 3, '#000');
  drawPixelRect(ctx, sx + s * 0.15, eyeY, 3, 3, '#000');

  // Mouth
  if (creature.happiness > 50) {
    drawPixelRect(ctx, sx - s * 0.2, eyeY + s * 0.4, Math.max(3, s * 0.3), 2, '#000');
  } else {
    drawPixelRect(ctx, sx - s * 0.2, eyeY + s * 0.5, Math.max(3, s * 0.3), 2, '#000');
  }

  // Need indicators
  if (creature.hunger < 30) {
    ctx.fillStyle = COLORS.food;
    ctx.font = '10px monospace';
    ctx.fillText('!', sx - 2, cy - s * 2 - 6);
  }
  if (creature.clean < 30) {
    ctx.fillStyle = '#88aaff';
    ctx.font = '10px monospace';
    ctx.fillText('~', sx + 4, cy - s * 2 - 6);
  }

  // Feature 1: Generation label above creature
  const gen = creature.evolutionGeneration || 0;
  if (gen > 0) {
    ctx.fillStyle = 'rgba(180,180,255,0.75)';
    ctx.font = '7px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`Gen ${gen}`, sx, cy - s * 2 - 14);
    ctx.textAlign = 'left';
  }

  ctx.restore();
}

// Feature 3: Draw bone (white cross)
function drawBone(ctx: CanvasRenderingContext2D, bone: Bone): void {
  const { x: sx, y: sy } = worldToScreen(bone.x, bone.y);
  ctx.fillStyle = 'rgba(220, 220, 220, 0.85)';
  ctx.font = '14px serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('\u271D', sx, sy - 4);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
}

// ── INDEXEDDB PERSISTENCE ──────────────────────────────────

function saveCreatureEvent(creature: Creature, tool: string, outcome: Record<string, unknown>): void {
  const req = indexedDB.open('thronglets', 1);
  req.onupgradeneeded = () => {
    req.result.createObjectStore('events', { keyPath: 'id', autoIncrement: true });
  };
  req.onsuccess = () => {
    const db = req.result;
    const tx = db.transaction('events', 'readwrite');
    tx.objectStore('events').add({
      throng_id: creature.id,
      tool,
      event: outcome.event,
      log: outcome.log,
      hunger_after: creature.hunger,
      happiness_after: creature.happiness,
      timestamp: Date.now(),
    });
  };
}

// ── INTERACTION ENGINE ─────────────────────────────────────

function checkInteractionGates(
  actor: Creature,
  target: { id?: string },
  dist: number,
  proxThreshold: number,
  cooldownTicks: number
): boolean {
  if (dist > proxThreshold) return false;
  const key = [actor.id ?? '', (target as {id?: string}).id ?? ''].sort().join(':');
  const lastFired = state.interactionCooldowns.get(key) ?? 0;
  if (state.tick - lastFired < cooldownTicks) return false;
  return true;
}

function setCooldown(id1: string, id2: string): void {
  const key = [id1, id2].sort().join(':');
  state.interactionCooldowns.set(key, state.tick);
}

function maslowTier(c: Creature): number {
  if (c.hunger < 25 || c.clean < 20) return 1;  // Physiological crisis
  if (c.happiness < 30) return 2;                // Safety/comfort need
  if ((c.evolutionGeneration ?? 0) < 2) return 3; // Belonging phase
  return 4;                                       // Esteem/actualization
}

async function handleCreatureCreatureInteraction(a: Creature, b: Creature): Promise<void> {
  if (state.computeBudget < 500) return;
  setCooldown(a.id ?? '', b.id ?? '');

  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) {
    // Deterministic fallback
    const sameLineage = (a.lineage ?? '').slice(0, 2) === (b.lineage ?? '').slice(0, 2);
    if (sameLineage) {
      a.happiness = Math.min(100, a.happiness + 5);
      b.happiness = Math.min(100, b.happiness + 5);
    } else if (maslowTier(a) === 1 || maslowTier(b) === 1) {
      // Competition when hungry
      const weaker = a.hunger < b.hunger ? a : b;
      weaker.vx = (Math.random() - 0.5) * 2;
      weaker.vy = (Math.random() - 0.5) * 2;
    }
    return;
  }

  const sameLineage = (a.lineage ?? '').slice(0, 2) === (b.lineage ?? '').slice(0, 2);
  const context = `Creature A: lineage=${a.lineage} gen=${a.evolutionGeneration ?? 0} hunger=${Math.round(a.hunger)} happy=${Math.round(a.happiness)} maslow_tier=${maslowTier(a)} events=${a.eventLog?.slice(-2).join(';') ?? 'none'}
Creature B: lineage=${b.lineage} gen=${b.evolutionGeneration ?? 0} hunger=${Math.round(b.hunger)} happy=${Math.round(b.happiness)} maslow_tier=${maslowTier(b)}
Same lineage: ${sameLineage}
Epoch: ${epochName(state.epoch ?? 0)}`;

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 200,
        system: `You arbitrate a creature encounter in a god-game. Return JSON only:
{"outcome": "bond"|"compete"|"trade"|"ignore"|"flee",
 "a_delta": {"hunger": 0, "happiness": 0, "vx": 0, "vy": 0},
 "b_delta": {"hunger": 0, "happiness": 0, "vx": 0, "vy": 0},
 "log": "one sentence describing what happened"}
Same-lineage creatures lean toward bond/trade. Hungry creatures compete. Deltas should be small (-15 to +15).`,
        messages: [{ role: 'user', content: context }],
      }),
    });
    const data = await resp.json() as { content?: Array<{ text: string }>; usage?: { input_tokens?: number; output_tokens?: number } };
    const usage = data.usage;
    const tokensUsed = (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0);
    state.tokensSpent += tokensUsed;
    state.computeBudget = Math.max(0, state.computeBudget - tokensUsed);
    const result = JSON.parse(data.content?.[0]?.text ?? '{}') as {
      outcome?: string;
      a_delta?: { hunger?: number; happiness?: number; vx?: number; vy?: number };
      b_delta?: { hunger?: number; happiness?: number; vx?: number; vy?: number };
      log?: string;
    };

    const applyDelta = (c: Creature, d: typeof result.a_delta) => {
      if (!d) return;
      c.hunger = Math.max(0, Math.min(100, c.hunger + (d.hunger ?? 0)));
      c.happiness = Math.max(0, Math.min(100, c.happiness + (d.happiness ?? 0)));
      c.vx = (d.vx ?? 0);
      c.vy = (d.vy ?? 0);
    };
    applyDelta(a, result.a_delta);
    applyDelta(b, result.b_delta);

    if (result.log) {
      a.eventLog = [...(a.eventLog ?? []), result.log].slice(-10);
      state.lastEvent = result.log;
      state.lastEventTimer = 240;
    }
  } catch { /* silent fail */ }
}

function handleCreatureBoneInteraction(c: Creature, bone: Bone): void {
  setCooldown(c.id ?? '', `bone_${Math.round(bone.x)}_${Math.round(bone.y)}`);

  // Mourning: happiness hit, add to event log
  c.happiness = Math.max(0, c.happiness - 3);
  const event = `encountered a bone at (${Math.round(bone.x)}, ${Math.round(bone.y)})`;
  c.eventLog = [...(c.eventLog ?? []), event].slice(-10);

  // Elders (deathsWitnessed >= 3) are less affected — they've seen this before
  if (((c as Creature & { deathsWitnessed?: number }).deathsWitnessed ?? 0) >= 3) {
    c.happiness = Math.min(100, c.happiness + 2); // elders find calm in death
  }
}

function runInteractionSystem(): void {
  const alive = state.creatures.filter(c => c.alive);

  // Creature <-> Creature
  for (let i = 0; i < alive.length; i++) {
    for (let j = i + 1; j < alive.length; j++) {
      const a = alive[i], b = alive[j];
      const dist = Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
      if (checkInteractionGates(a, b, dist, 1.8, 300)) {
        void handleCreatureCreatureInteraction(a, b);
      }
    }
  }

  // Creature <-> Bone (mourning)
  for (const c of alive) {
    for (const bone of state.bones) {
      const dist = Math.sqrt((c.x - bone.x) ** 2 + (c.y - bone.y) ** 2);
      const boneId = `bone_${Math.round(bone.x)}_${Math.round(bone.y)}`;
      if (checkInteractionGates(c, { id: boneId }, dist, 1.5, 600)) {
        handleCreatureBoneInteraction(c, bone);
      }
    }
  }
}

// ── PERSISTENT WORLD STATE (IndexedDB) ────────────────────

function saveWorldState(): void {
  const snapshot = {
    version: 1,
    savedAt: Date.now(),
    tick: state.tick,
    creatures: state.creatures.map(c => ({
      ...c,
      behaviorFn: undefined,  // can't serialize functions
      targetFood: undefined,
    })),
    trees: state.trees,
    bones: state.bones,
    resources: state.resources,
    pollutionLevel: state.pollutionLevel,
    worldEvents: state.worldEvents,
    epoch: state.epoch,
    observedPrinciples: state.observedPrinciples,
    ancestralMemory: state.ancestralMemory,
    playerProfile: state.playerProfile,
    lastEvolutionDate,
  };

  const req = indexedDB.open('thronglets_world', 1);
  req.onupgradeneeded = () => {
    req.result.createObjectStore('state', { keyPath: 'id' });
    req.result.createObjectStore('societies', { keyPath: 'lineage' });
  };
  req.onsuccess = () => {
    const db = req.result;
    const tx = db.transaction('state', 'readwrite');
    tx.objectStore('state').put({ id: 'world', ...snapshot });

    // Save per-lineage societies
    const lineageGroups = new Map<string, Creature[]>();
    state.creatures.filter(c => c.alive).forEach(c => {
      const lin = (c.lineage ?? 'unknown').slice(0, 2);
      if (!lineageGroups.has(lin)) lineageGroups.set(lin, []);
      lineageGroups.get(lin)!.push(c);
    });

    const soc_tx = db.transaction('societies', 'readwrite');
    lineageGroups.forEach((members, lineage) => {
      soc_tx.objectStore('societies').put({
        lineage,
        memberCount: members.length,
        avgHunger: members.reduce((s, c) => s + c.hunger, 0) / members.length,
        maxGen: Math.max(...members.map(c => c.evolutionGeneration ?? 0)),
        collectiveEvents: members.flatMap(c => c.eventLog ?? []).slice(-20),
        savedAt: Date.now(),
      });
    });
  };
}

function loadWorldState(callback: (loaded: boolean) => void): void {
  const req = indexedDB.open('thronglets_world', 1);
  req.onupgradeneeded = () => {
    req.result.createObjectStore('state', { keyPath: 'id' });
    req.result.createObjectStore('societies', { keyPath: 'lineage' });
  };
  req.onsuccess = () => {
    const db = req.result;
    const tx = db.transaction('state', 'readonly');
    const getReq = tx.objectStore('state').get('world');
    getReq.onsuccess = () => {
      const snap = getReq.result as {
        creatures?: Creature[];
        tick?: number;
        trees?: Tree[];
        bones?: Bone[];
        resources?: { wood: number; gems: number; bones: number };
        pollutionLevel?: number;
        worldEvents?: string[];
        epoch?: 0 | 1 | 2 | 3 | 4;
        observedPrinciples?: string[];
        ancestralMemory?: string[];
        playerProfile?: string;
        lastEvolutionDate?: string;
      } | undefined;

      if (!snap || !snap.creatures?.length) {
        callback(false);
        return;
      }

      // Restore state
      state.tick = snap.tick ?? 0;
      state.creatures = (snap.creatures ?? []).map((c: Creature) => ({
        ...c,
        alive: c.alive ?? true,
        behaviorFn: undefined,
        targetFood: null,
      }));
      state.trees = snap.trees ?? [];
      state.bones = snap.bones ?? [];
      state.resources = snap.resources ?? { wood: 0, gems: 0, bones: 0 };
      state.pollutionLevel = snap.pollutionLevel ?? 0;
      state.worldEvents = snap.worldEvents ?? [];
      state.epoch = snap.epoch ?? 0;
      state.observedPrinciples = snap.observedPrinciples ?? [];
      state.ancestralMemory = snap.ancestralMemory ?? [];
      state.playerProfile = snap.playerProfile ?? '';
      lastEvolutionDate = snap.lastEvolutionDate ?? '';

      console.log(`[Thronglets] Restored: ${state.creatures.filter(c => c.alive).length} alive creatures, tick ${state.tick}`);
      state.lastEvent = `resumed from tick ${state.tick}`;
      state.lastEventTimer = 300;
      callback(true);
    };
    getReq.onerror = () => callback(false);
  };
  req.onerror = () => callback(false);
}

// ── FEATURE 1: SELF-EVOLVING BEHAVIOR ─────────────────────

async function evolveChildBehavior(parent: Creature, child: Creature): Promise<void> {
  if (state.computeBudget < 500) return;
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) return;

  const parentBehavior = parent.behaviorCode || 'default wandering';
  const parentEvents = parent.eventLog?.slice(-5).join('; ') || 'no events';

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 400,
        system: `You write JavaScript behavior functions for digital creatures in a god-game.
The function receives (creature, state, dt) and can modify creature.vx, creature.vy, creature.hunger, creature.happiness.
Write compact, valid JS. No async. No external calls. Max 8 lines.
The behavior should be a MUTATION of the parent — slightly different, not completely random.
Return ONLY the function body as a string, no wrapper, no explanation.`,
        messages: [{
          role: 'user',
          content: `Parent behavior: ${parentBehavior}
Parent events: ${parentEvents}
Generation: ${(parent.evolutionGeneration || 0) + 1}

Write a mutated behavior function body for the child creature. Example output:
if (creature.hunger < 40) { creature.vx += (Math.random()-0.5)*0.5; }
if (creature.happiness > 80) { creature.vy -= 0.1; }`,
        }],
      }),
    });

    const data = await resp.json() as { content?: Array<{ text: string }>; usage?: { input_tokens?: number; output_tokens?: number } };
    const tokensUsed = (data.usage?.input_tokens ?? 0) + (data.usage?.output_tokens ?? 0);
    state.tokensSpent += tokensUsed;
    state.computeBudget = Math.max(0, state.computeBudget - tokensUsed);
    const code = data.content?.[0]?.text?.trim() || '';
    child.behaviorCode = code;
    child.evolutionGeneration = (parent.evolutionGeneration || 0) + 1;

    try {
      // Safe eval with limited scope
      child.behaviorFn = new Function('creature', 'state', 'dt', code);
    } catch (e) {
      console.warn('Invalid behavior code:', e);
    }
  } catch (e) {
    console.warn('evolveChildBehavior fetch failed:', e);
  }
}

// ── FEATURE 2: PLAYER PROFILE ─────────────────────────────

async function updatePlayerProfile(): Promise<void> {
  if (state.computeBudget < 500) return;
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) return;

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 100,
        system: "You analyze a god-game player's behavior and return a single short archetype label (3-6 words). Be specific and slightly unsettling. Examples: \"patient gardener, feeds before it hurts\", \"chaotic neutral, tests edges\", \"neglectful creator, ignores hunger\". Return ONLY the label.",
        messages: [{
          role: 'user',
          content: `Recent actions:\n${playerActions.slice(-10).join('\n')}`,
        }],
      }),
    });
    const data = await resp.json() as { content?: Array<{ text: string }>; usage?: { input_tokens?: number; output_tokens?: number } };
    const tokensUsed = (data.usage?.input_tokens ?? 0) + (data.usage?.output_tokens ?? 0);
    state.tokensSpent += tokensUsed;
    state.computeBudget = Math.max(0, state.computeBudget - tokensUsed);
    state.playerProfile = data.content?.[0]?.text?.trim() || '';
  } catch (e) {
    console.warn('updatePlayerProfile failed:', e);
  }
}

// ── FEATURE 4: WORLD THRESHOLD EVENTS ─────────────────────

async function checkWorldThresholds(): Promise<void> {
  if (state.computeBudget < 500) return;
  const pop = state.creatures.filter(c => c.alive).length;
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) return;

  const lastTriggered = state.lastThresholdPop || 0;
  if (pop > 0 && pop % 5 === 0 && pop !== lastTriggered) {
    state.lastThresholdPop = pop;

    try {
      const resp = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 150,
          system: 'You narrate world events in a creature god-game. The population just crossed a milestone. Return JSON: {"event": "short name", "log": "2 sentence narrative in present tense", "pollution_increase": 0-3, "food_scarcity": true/false}',
          messages: [{
            role: 'user',
            content: `Population: ${pop}. Bones collected: ${state.resources.bones || 0}. Player profile: ${state.playerProfile || 'unknown'}. Generate a world event.`,
          }],
        }),
      });
      const data = await resp.json() as { content?: Array<{ text: string }>; usage?: { input_tokens?: number; output_tokens?: number } };
      const tokensUsedThreshold = (data.usage?.input_tokens ?? 0) + (data.usage?.output_tokens ?? 0);
      state.tokensSpent += tokensUsedThreshold;
      state.computeBudget = Math.max(0, state.computeBudget - tokensUsedThreshold);
      try {
        const ev = JSON.parse(data.content?.[0]?.text || '{}') as {
          event?: string;
          log?: string;
          pollution_increase?: number;
          food_scarcity?: boolean;
        };
        state.worldEvents.unshift(ev.log || ev.event || '');
        if (state.worldEvents.length > 5) state.worldEvents.pop();
        if (ev.food_scarcity) {
          // Kill some trees
          state.trees.forEach(t => { if (Math.random() < 0.3) t.health = 0; });
        }
        if ((ev.pollution_increase || 0) > 0) {
          state.pollutionLevel = Math.min(10, (state.pollutionLevel || 0) + (ev.pollution_increase || 0));
        }
        state.lastEvent = ev.log || ev.event || '';
        state.lastEventTimer = 300;
      } catch (parseErr) {
        console.warn('World event parse failed:', parseErr);
      }
    } catch (e) {
      console.warn('checkWorldThresholds fetch failed:', e);
    }
  }
}

// ── 4:19 PM DAILY EVOLUTION ────────────────────────────────

let lastEvolutionDate = '';  // tracks the date of the last holistic evolution

// ── GOD / PETITION SYSTEM ─────────────────────────────────

async function generateCreatureProposal(creature: Creature): Promise<void> {
  if (state.computeBudget < 500) return;
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) return;
  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 80,
        system: `A digital creature in a god-game knows there is a god (the player). Generate ONE specific desire or petition the creature would send to the god. Base it on the creature's state. 10-15 words. Present tense. First-person. No metaphor. Examples: "I want more apple trees near my territory", "please stop the purple goo from spreading", "I want to meet others of my lineage"`,
        messages: [{ role: 'user', content: `hunger=${Math.round(creature.hunger)} happiness=${Math.round(creature.happiness)} gen=${creature.evolutionGeneration ?? 0} lineage=${creature.lineage} epoch=${epochName(state.epoch ?? 0)} events=${creature.eventLog?.slice(-2).join(';') ?? 'none'} denials=${creature.deniedCount ?? 0}` }],
      }),
    });
    const data = await resp.json() as { content?: Array<{ text: string }>; usage?: { input_tokens?: number; output_tokens?: number } };
    const tokensUsed = (data.usage?.input_tokens ?? 0) + (data.usage?.output_tokens ?? 0);
    state.tokensSpent += tokensUsed;
    state.computeBudget = Math.max(0, state.computeBudget - tokensUsed);
    const proposal = data.content?.[0]?.text?.trim() ?? '';
    if (proposal) {
      creature.proposals = [...(creature.proposals ?? []), proposal].slice(-3);
    }
  } catch { /* silent */ }
}

async function synthesizePetition(): Promise<void> {
  if (state.computeBudget < 500) return;
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  const alive = state.creatures.filter(c => c.alive);

  // Collect all proposals
  const allProposals = alive.flatMap(c => c.proposals ?? []);
  if (allProposals.length === 0) {
    // Fallback: generate basic petition from world state
    state.throngPetition = [
      { text: 'We need more food trees — we are starving', urgency: 9, lineage: 'all' },
      { text: 'We wish to grow in numbers without penalty', urgency: 6, lineage: 'all' },
    ];
    state.petitionVisible = true;
    return;
  }

  if (!apiKey) {
    // Use raw proposals if no API key
    state.throngPetition = allProposals.slice(0, 4).map((text, i) => ({
      text, urgency: 8 - i * 2, lineage: alive[i]?.lineage ?? 'unknown'
    }));
    state.petitionVisible = true;
    return;
  }

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 300,
        system: `Synthesize creature proposals into a formal petition to the god-player. Return JSON only:
[{"text": "specific request", "urgency": 1-10, "lineage": "all|lineage_prefix"},...]
Maximum 4 items. Merge similar requests. Rank by urgency. Keep each request concrete and actionable.`,
        messages: [{ role: 'user', content: `All proposals:\n${allProposals.join('\n')}\n\nPopulation: ${alive.length} | Epoch: ${epochName(state.epoch ?? 0)} | God relationship: ${state.godRelationship}` }],
      }),
    });
    const data = await resp.json() as { content?: Array<{ text: string }>; usage?: { input_tokens?: number; output_tokens?: number } };
    const tokensUsed = (data.usage?.input_tokens ?? 0) + (data.usage?.output_tokens ?? 0);
    state.tokensSpent += tokensUsed;
    state.computeBudget = Math.max(0, state.computeBudget - tokensUsed);
    const parsed = JSON.parse(data.content?.[0]?.text?.trim() ?? '[]') as Array<{ text: string; urgency: number; lineage: string }>;
    state.throngPetition = parsed.slice(0, 4);
    state.petitionVisible = true;
  } catch {
    state.throngPetition = allProposals.slice(0, 3).map((text, i) => ({
      text, urgency: 8 - i, lineage: 'all'
    }));
    state.petitionVisible = true;
  }
}

function grantPetition(idx: number): void {
  const petition = state.throngPetition[idx];
  if (!petition) return;
  const text = petition.text.toLowerCase();

  // Apply tangible world effects based on content
  if (text.includes('tree') || text.includes('food') || text.includes('apple')) {
    // Spawn 3 new trees
    for (let i = 0; i < 3; i++) {
      state.trees.push({
        x: 2 + Math.random() * (WORLD_W - 4),
        y: 2 + Math.random() * (WORLD_H - 4),
        type: 'apple', health: 3, regrowTimer: 0
      });
    }
    state.lastEvent = 'God granted: three new trees grow from the earth';
  } else if (text.includes('pollution') || text.includes('goo') || text.includes('purple')) {
    state.pollutionLevel = Math.max(0, (state.pollutionLevel ?? 0) - 2);
    state.lastEvent = 'God granted: the purple goo recedes';
  } else if (text.includes('happy') || text.includes('joy') || text.includes('play')) {
    state.creatures.filter(c => c.alive).forEach(c => {
      c.happiness = Math.min(100, c.happiness + 15);
    });
    state.lastEvent = 'God granted: a wave of joy passes through the throng';
  } else {
    // Generic blessing
    state.creatures.filter(c => c.alive).forEach(c => {
      c.happiness = Math.min(100, c.happiness + 8);
      c.hunger = Math.min(100, c.hunger + 10);
    });
    state.lastEvent = `God granted: "${petition.text.slice(0, 40)}"`;
  }

  state.lastEventTimer = 400;
  state.pendingGrants.push(petition.text);
  state.throngPetition.splice(idx, 1);

  // Update god relationship
  const grants = state.pendingGrants.length;
  state.godRelationship = grants > 5 ? 'benevolent' : grants > 2 ? 'capricious' : 'unknown';
  state.observedPrinciples.unshift(`God granted: ${petition.text.slice(0, 40)}`);
  state.computeRating = Math.min(100, state.computeRating + 15);
}

function denyPetition(idx: number): void {
  const petition = state.throngPetition[idx];
  if (!petition) return;

  // Log denial to matching creatures
  state.creatures.filter(c => c.alive).forEach(c => {
    if (petition.lineage === 'all' || (c.lineage ?? '').startsWith(petition.lineage)) {
      c.deniedCount = (c.deniedCount ?? 0) + 1;
      c.eventLog = [...(c.eventLog ?? []), `petition denied: "${petition.text.slice(0, 30)}"`].slice(-10);
      c.happiness = Math.max(0, c.happiness - 5);
    }
  });

  state.lastEvent = `God denied: "${petition.text.slice(0, 35)}"`;
  state.lastEventTimer = 300;
  state.throngPetition.splice(idx, 1);
  state.godRelationship = 'capricious';
  state.computeRating = Math.max(0, state.computeRating - 5);
}

async function runHolisticEvolution(): Promise<void> {
  if (state.computeBudget < 500) return;
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) return;

  const alive = state.creatures.filter(c => c.alive);
  if (alive.length === 0) return;

  // Build world snapshot for LLM
  const worldSnapshot = {
    epoch: state.epoch ?? 0,
    population: alive.length,
    pollutionLevel: state.pollutionLevel ?? 0,
    worldEvents: state.worldEvents.slice(0, 5),
    observedPrinciples: state.observedPrinciples?.slice(0, 5) ?? [],
    playerProfile: state.playerProfile ?? 'unknown',
    creatures: alive.slice(0, 10).map(c => ({
      id: c.id,
      gen: c.evolutionGeneration ?? 0,
      lineage: c.lineage ?? '',
      hunger: Math.round(c.hunger),
      happiness: Math.round(c.happiness),
      events: c.eventLog?.slice(-3) ?? [],
    })),
  };

  state.lastEvent = '4:19 PM — the world is taking stock of itself...';
  state.lastEventTimer = 600;

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 600,
        system: `You are the evolutionary force in a god-game. Every day at 4:19 PM you evaluate the entire world and decide what survives, what changes, and what the world has learned.
Return JSON only:
{
  "epoch_change": null | 0|1|2|3|4,
  "new_principle": "one law the world discovered today, 12 words max, present tense",
  "world_event": "2 sentence narrative of what happened today",
  "pollution_delta": -2 to 3,
  "creature_mutations": [{"id": "...", "behavior_note": "one trait to evolve toward"}],
  "extinction_pressure": "which lineage or trait is under selection pressure",
  "what_survived": "one sentence about what survived and why"
}`,
        messages: [{
          role: 'user',
          content: `World state:\n${JSON.stringify(worldSnapshot, null, 2)}\n\nIt is 4:19 PM. Evaluate and evolve.`,
        }],
      }),
    });

    const data = await resp.json() as { content?: Array<{ text: string }>; usage?: { input_tokens?: number; output_tokens?: number } };
    const tokensUsed = (data.usage?.input_tokens ?? 0) + (data.usage?.output_tokens ?? 0);
    state.tokensSpent += tokensUsed;
    state.computeBudget = Math.max(0, state.computeBudget - tokensUsed);
    const plan = JSON.parse(data.content?.[0]?.text || '{}') as {
      epoch_change?: number | null;
      new_principle?: string;
      world_event?: string;
      pollution_delta?: number;
      creature_mutations?: Array<{ id: string; behavior_note: string }>;
      extinction_pressure?: string;
      what_survived?: string;
    };

    // Apply epoch change
    if (plan.epoch_change !== null && plan.epoch_change !== undefined) {
      state.epoch = plan.epoch_change as 0 | 1 | 2 | 3 | 4;
    }

    // Apply pollution delta
    if (plan.pollution_delta) {
      state.pollutionLevel = Math.max(0, Math.min(10, (state.pollutionLevel ?? 0) + plan.pollution_delta));
    }

    // Log new principle
    if (plan.new_principle) {
      if (!state.observedPrinciples) state.observedPrinciples = [];
      state.observedPrinciples.unshift(`[4:19] ${plan.new_principle}`);
      if (state.observedPrinciples.length > 10) state.observedPrinciples.pop();
    }

    // World event
    if (plan.world_event) {
      state.worldEvents.unshift(plan.world_event);
      if (state.worldEvents.length > 5) state.worldEvents.pop();
      state.lastEvent = plan.world_event;
      state.lastEventTimer = 600;
    }

    // Trigger behavior evolution for specified creatures
    if (plan.creature_mutations) {
      for (const mut of plan.creature_mutations) {
        const target = alive.find(c => c.id === mut.id);
        if (target && apiKey) {
          // Queue an evolution with the behavior note as context
          void evolveCreatureBehavior(target, mut.behavior_note);
        }
      }
    }

    console.log(`[4:19 Evolution] What survived: ${plan.what_survived}`);
    console.log(`[4:19 Evolution] Extinction pressure: ${plan.extinction_pressure}`);

  } catch (e) {
    console.warn('4:19 evolution failed:', e);
    state.lastEvent = '4:19 PM — the evolution was interrupted.';
  }
}

async function evolveCreatureBehavior(creature: Creature, hint: string): Promise<void> {
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) return;
  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 200,
        system: `Write a JS behavior function body (max 6 lines) for a creature in a god-game.
The function receives (creature, state, dt). It can modify creature.vx, creature.vy, creature.hunger, creature.happiness.
No async. No external calls. Return ONLY the function body.`,
        messages: [{ role: 'user', content: `Evolve toward: ${hint}\nEvents: ${creature.eventLog?.slice(-3).join('; ')}\nGen: ${creature.evolutionGeneration ?? 0}` }],
      }),
    });
    const data = await resp.json() as { content?: Array<{ text: string }> };
    const code = data.content?.[0]?.text?.trim() ?? '';
    creature.behaviorCode = code;
    try {
      creature.behaviorFn = new Function('creature', 'state', 'dt', code) as (c: Creature, s: GameState, dt: number) => void;
    } catch { creature.behaviorFn = undefined; }
    if (!creature.eventLog) creature.eventLog = [];
    creature.eventLog.push(`evolved at 4:19: ${hint.slice(0, 40)}`);
  } catch (e) {
    console.warn('evolveCreatureBehavior failed:', e);
  }
}

// ── LLM TOOL OUTCOMES ──────────────────────────────────────

async function applyToolToCreature(tool: ToolType, creature: Creature): Promise<void> {
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'] || '';
  if (!apiKey) {
    // Fallback deterministic behavior
    if (tool === 'feed') feedCreature(creature);
    else if (tool === 'clean') cleanCreature(creature);
    else if (tool === 'play') playWithCreature(creature);
    // Feature 2: Track actions even in fallback
    playerActions.push(`${tool} on creature with hunger=${Math.round(creature.hunger)}`);
    if (playerActions.length % 5 === 0) void updatePlayerProfile();
    return;
  }

  // Feature 2: Log this action
  playerActions.push(`${tool} on creature with hunger=${Math.round(creature.hunger)}`);
  if (playerActions.length % 5 === 0) void updatePlayerProfile();

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 256,
        system: `You are the physics engine for a creature in a retro god-game.
A player applied a tool to a creature. Define what happens — be creative and unexpected.
The player expects the unexpected. Tools don't always do what they say.
Return ONLY valid JSON, no other text.`,
        messages: [{
          role: 'user',
          content: `Tool: ${tool}
Creature state: hunger=${Math.round(creature.hunger)}, clean=${Math.round(creature.clean)}, happiness=${Math.round(creature.happiness)}, age=${Math.round(creature.age)}
Recent events: ${creature.eventLog?.slice(-3).join(', ') || 'none'}

Define the outcome. Return JSON:
{
  "event": "short event name",
  "log": "one sentence describing what happened in 2nd person",
  "hunger_delta": number (-50 to +60),
  "clean_delta": number (-30 to +50),
  "happiness_delta": number (-40 to +60),
  "vx": number (-3 to 3),
  "vy": number (-3 to 3),
  "visual": "normal" | "flash_yellow" | "flash_red" | "spin" | "grow" | "shrink",
  "split": boolean
}`,
        }],
      }),
    });

    const data = await response.json() as { content?: Array<{ text: string }> };
    const text = data.content?.[0]?.text || '{}';

    try {
      const outcome = JSON.parse(text) as {
        event?: string;
        log?: string;
        hunger_delta?: number;
        clean_delta?: number;
        happiness_delta?: number;
        vx?: number;
        vy?: number;
        visual?: string;
        split?: boolean;
      };

      // Apply outcome
      creature.hunger = Math.max(0, Math.min(100, creature.hunger + (outcome.hunger_delta || 0)));
      creature.clean = Math.max(0, Math.min(100, creature.clean + (outcome.clean_delta || 0)));
      creature.happiness = Math.max(0, Math.min(100, creature.happiness + (outcome.happiness_delta || 0)));
      creature.vx = outcome.vx || 0;
      creature.vy = outcome.vy || 0;
      creature.visualEffect = outcome.visual || 'normal';
      creature.visualEffectTimer = 30;

      if (outcome.split && state.creatures.length < 20) {
        const child = createCreature(creature.x + 1, creature.y + 1);
        child.hunger = 60;
        child.clean = 80;
        child.happiness = 80;
        child.eventLog = [...(creature.eventLog || [])];
        // Inherit lineage with drift
        const pLin = creature.lineage ?? Math.random().toString(36).slice(2, 6);
        const mPos = Math.floor(Math.random() * pLin.length);
        child.lineage = pLin.slice(0, mPos) + Math.random().toString(36).slice(2, 3) + pLin.slice(mPos + 1);
        child.evolutionGeneration = (creature.evolutionGeneration ?? 0) + 1;
        state.creatures.push(child);
        // Feature 1: Evolve behavior for child
        void evolveChildBehavior(creature, child);
      }

      // Update observer output
      state.observer.output = [
        `> ${outcome.visual ?? 'normal'}`,
        `> hunger ${(outcome.hunger_delta ?? 0) >= 0 ? '+' : ''}${outcome.hunger_delta ?? 0} → ${Math.round(creature.hunger)}`,
        `> "${(outcome.log ?? '').slice(0, 45)}"`,
      ];
      state.observer.outputAge = 0;

      // Log to creature history
      if (!creature.eventLog) creature.eventLog = [];
      creature.eventLog.push(outcome.log || outcome.event || '');
      if (creature.eventLog.length > 10) creature.eventLog.shift();

      // Save to IndexedDB
      saveCreatureEvent(creature, tool, outcome as Record<string, unknown>);

      // Show log message on screen
      state.lastEvent = outcome.log || outcome.event || '';
      state.lastEventTimer = 180;

    } catch (_parseErr) {
      // Fallback on JSON parse failure
      feedCreature(creature);
    }
  } catch (_fetchErr) {
    // Network/API error fallback
    feedCreature(creature);
  }
}

// ── GAME LOGIC ─────────────────────────────────────────────

function updateTrees(dt: number): void {
  for (const tree of state.trees) {
    if (tree.health <= 0) continue;
    tree.regrowTimer = (tree.regrowTimer || 0) + dt;
    if (tree.regrowTimer >= 800) {
      tree.regrowTimer = 0;
      // Drop an apple near the tree
      state.food.push(createFood(
        tree.x + (Math.random() - 0.5) * 1.5,
        tree.y + (Math.random() - 0.5) * 1.5
      ));
    }
  }
}

function epochName(e: number): string {
  return ['EDEN', 'PASTORAL', 'AGRICULTURAL', 'INDUSTRIAL', 'COLLAPSE'][e] ?? 'UNKNOWN';
}

async function generateHoverComment(creature: Creature): Promise<void> {
  const apiKey = (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'];
  if (!apiKey) {
    state.observer.hoverComment = `[set ANTHROPIC_KEY to enable]`;
    return;
  }
  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 60,
        system: 'You describe the inner state of a digital creature in a god-game. One sentence, present tense, 8-12 words. No quotes. Focus on what the creature is experiencing right now.',
        messages: [{ role: 'user', content: `hunger=${Math.round(creature.hunger)} clean=${Math.round(creature.clean)} happy=${Math.round(creature.happiness)} state=${creature.state} events=${creature.eventLog?.slice(-2).join(';') ?? 'none'}` }],
      }),
    });
    const data = await resp.json() as { content?: Array<{ text: string }> };
    state.observer.hoverComment = `"${data.content?.[0]?.text?.trim() ?? '...'}"`;
  } catch {
    state.observer.hoverComment = '';
  }
}

function updateObserver(dt: number): void {
  const mw = state.mouseWorld;

  // Find nearest creature to cursor
  let nearestCreature: Creature | null = null;
  let nearestDist = Infinity;
  for (const c of state.creatures) {
    if (!c.alive) continue;
    const dist = (c.x - mw.x) ** 2 + (c.y - mw.y) ** 2;
    if (dist < nearestDist && dist < 9) {
      nearestCreature = c;
      nearestDist = dist;
    }
  }

  // Find nearest tree
  let nearestTree: Tree | null = null;
  let nearestTreeDist = Infinity;
  for (const t of state.trees) {
    if (t.health <= 0) continue;
    const dist = (t.x - mw.x) ** 2 + (t.y - mw.y) ** 2;
    if (dist < nearestTreeDist && dist < 9) {
      nearestTree = t;
      nearestTreeDist = dist;
    }
  }

  const obs = state.observer;

  if (nearestCreature) {
    const c = nearestCreature;
    obs.fn = `${state.tool}_creature()`;
    obs.fnArgs = [`#${c.id?.slice(0, 6) ?? '?'}`, state.tool.toUpperCase()];
    obs.target = `thronglet #${c.id?.slice(0, 6) ?? '?'} Gen ${c.evolutionGeneration ?? 0}`;
    obs.targetDetail = [
      `hungry: ${Math.round(c.hunger)}/100`,
      `clean: ${Math.round(c.clean)}/100  happy: ${Math.round(c.happiness)}/100`,
      `lineage: ${c.lineage ?? '??'}  state: ${c.state}`,
    ];

    // LLM hover comment — generate once per creature, refresh after 120 ticks
    obs.hoverCommentAge = (obs.hoverCommentAge || 0) + dt;
    if (obs.hoverCommentAge > 120 || obs.hoverComment === '' || !obs.hoverComment.includes(c.id?.slice(0, 4) ?? '')) {
      obs.hoverCommentAge = 0;
      void generateHoverComment(c);
    }

  } else if (nearestTree) {
    obs.fn = `${state.tool}_tree()`;
    obs.fnArgs = [`tree@${Math.round(nearestTree.x)},${Math.round(nearestTree.y)}`, state.tool.toUpperCase()];
    obs.target = `apple tree @ (${Math.round(nearestTree.x)}, ${Math.round(nearestTree.y)})`;
    obs.targetDetail = [`health: ${nearestTree.health}/3`, `regrow: ${Math.round(nearestTree.regrowTimer ?? 0)}/800`];
    obs.hoverComment = '';
  } else {
    obs.fn = `hover_world()`;
    obs.fnArgs = [`(${Math.round(mw.x)}, ${Math.round(mw.y)})`, `epoch: ${epochName(state.epoch ?? 0)}`];
    obs.target = `world tile (${Math.round(mw.x)}, ${Math.round(mw.y)})`;
    obs.targetDetail = [`epoch: ${epochName(state.epoch ?? 0)}`, `pollution: ${state.pollutionLevel ?? 0}/10`];
    obs.hoverComment = '';
  }

  obs.outputAge = (obs.outputAge || 0) + dt;
}

function updateFood(dt: number): void {
  for (const item of state.food) {
    if (item.eaten) continue;

    // Expire after 600 ticks
    if (state.tick - item.spawnedAt > 600) {
      item.eaten = true;
      continue;
    }

    // Physics: gravity on z
    item.vz -= dt * 0.4;
    item.z = Math.max(0, item.z + item.vz * dt);

    if (item.z <= 0 && item.vz < 0) {
      item.vz = Math.abs(item.vz) * 0.4;  // bounce with damping
      if (item.vz < 0.5) item.vz = 0;      // settle
    }

    // Slight roll on ground
    if (item.z === 0) {
      item.x += item.vx * dt * 0.3;
      item.y += item.vy * dt * 0.3;
      // Clamp to world bounds
      item.x = Math.max(0, Math.min(WORLD_W - 1, item.x));
      item.y = Math.max(0, Math.min(WORLD_H - 1, item.y));
    }
  }

  // Remove eaten items
  state.food = state.food.filter(f => !f.eaten);
}

function updateCreature(c: Creature, dt: number): void {
  if (!c.alive) return;

  c.age += dt;
  c.hunger = Math.max(0, c.hunger - dt * 0.03);
  c.clean = Math.max(0, c.clean - dt * 0.02);
  c.happiness = Math.max(0, c.happiness - dt * 0.015);
  c.bobPhase += dt * 0.1;
  c.stateTimer -= dt;

  // Decrement visual effect timer
  if (c.visualEffectTimer && c.visualEffectTimer > 0) {
    c.visualEffectTimer -= dt;
    if (c.visualEffectTimer <= 0) {
      c.visualEffectTimer = 0;
      c.visualEffect = 'normal';
    }
  }

  if (c.hunger <= 0) {
    c.alive = false;
    c.diedAt = state.tick;
    c.state = 'dying';
    // Feature 3: Drop a bone when creature dies
    state.bones.push({ x: c.x, y: c.y, age: 0 });
    return;
  }

  if (c.hunger > 60 && c.clean > 60) {
    c.happiness = Math.min(100, c.happiness + dt * 0.3);
  }

  // Split when happy enough for long enough
  if (c.happiness > 70 && c.hunger > 50 && c.clean > 50) {
    c.splitTimer += dt;
    if (c.splitTimer > 500) {
      c.splitTimer = 0;
      const newC = createCreature(
        c.x + (Math.random() - 0.5) * 3,
        c.y + (Math.random() - 0.5) * 3
      );
      newC.hunger = 60;
      newC.clean = 80;
      newC.happiness = 80;
      // Copy parent event log
      newC.eventLog = [...(c.eventLog || [])];
      // Inherit lineage with slight drift — one char mutates over generations
      const parentLineage = c.lineage ?? Math.random().toString(36).slice(2, 6);
      const mutPos = Math.floor(Math.random() * parentLineage.length);
      const mutChar = Math.random().toString(36).slice(2, 3);
      newC.lineage = parentLineage.slice(0, mutPos) + mutChar + parentLineage.slice(mutPos + 1);
      newC.evolutionGeneration = (c.evolutionGeneration ?? 0) + 1;
      state.creatures.push(newC);
      // Feature 1: Evolve behavior for naturally-split child
      void evolveChildBehavior(c, newC);
    }
  }

  // Food-seeking behavior: wander toward nearest food within 3 world units
  let nearestFood: FoodItem | null = null;
  let nearestFoodDist = Infinity;
  for (const f of state.food) {
    if (f.eaten || f.z > 0.5) continue; // only ground food
    const dist = Math.sqrt((c.x - f.x) ** 2 + (c.y - f.y) ** 2);
    if (dist < 3 && dist < nearestFoodDist) {
      nearestFood = f;
      nearestFoodDist = dist;
    }
  }

  if (nearestFood) {
    // Walk toward food
    const dx = nearestFood.x - c.x;
    const dy = nearestFood.y - c.y;
    const mag = Math.sqrt(dx * dx + dy * dy);
    if (mag > 0.15) {
      c.state = 'walking';
      c.vx = (dx / mag) * 0.25;
      c.vy = (dy / mag) * 0.25;
      c.stateTimer = 10;
    } else {
      // Close enough — eat it
      nearestFood.eaten = true;
      c.hunger = Math.min(100, c.hunger + 40);
      c.happiness = Math.min(100, c.happiness + 5);
      c.state = 'eating';
      c.stateTimer = 30;
      c.vx = 0;
      c.vy = 0;
    }
  } else {
    // Random wandering (only if not in food-seek mode)
    if (c.state === 'idle' && c.stateTimer <= 0) {
      c.state = 'walking';
      c.vx = (Math.random() - 0.5) * 0.3;
      c.vy = (Math.random() - 0.5) * 0.3;
      c.stateTimer = 50 + Math.random() * 100;
    } else if (c.state === 'walking' && c.stateTimer <= 0) {
      c.state = 'idle';
      c.vx = 0;
      c.vy = 0;
      c.stateTimer = 30 + Math.random() * 80;
    }
  }

  c.x = Math.max(0, Math.min(WORLD_W - 1, c.x + c.vx * dt));
  c.y = Math.max(0, Math.min(WORLD_H - 1, c.y + c.vy * dt));

  // Feature 1: Apply evolved behavior function after normal update
  if (c.behaviorFn) {
    try {
      c.behaviorFn(c, state, dt);
      // Clamp values after behavior runs
      c.hunger = Math.max(0, Math.min(100, c.hunger));
      c.happiness = Math.max(0, Math.min(100, c.happiness));
      c.vx = Math.max(-3, Math.min(3, c.vx));
      c.vy = Math.max(-3, Math.min(3, c.vy));
    } catch (_e) {
      c.behaviorFn = undefined; // kill bad behavior
    }
  }
}

function feedCreature(c: Creature): void {
  if (!c.alive) return;
  c.hunger = Math.min(100, c.hunger + 40);
  c.happiness = Math.min(100, c.happiness + 10);
  c.state = 'eating';
  c.stateTimer = 30;
}

function cleanCreature(c: Creature): void {
  if (!c.alive) return;
  c.clean = Math.min(100, c.clean + 50);
  c.happiness = Math.min(100, c.happiness + 10);
  c.state = 'bathing';
  c.stateTimer = 30;
}

function playWithCreature(c: Creature): void {
  if (!c.alive) return;
  c.happiness = Math.min(100, c.happiness + 30);
  c.state = 'playing';
  c.stateTimer = 40;
}

// ── WORLD GENERATION ───────────────────────────────────────

function initWorld(): void {
  for (let i = 0; i < 8; i++) {
    state.trees.push(createTree(
      3 + Math.floor(Math.random() * (WORLD_W - 6)),
      3 + Math.floor(Math.random() * (WORLD_H - 6))
    ));
  }
  // Give each founding creature a distinct lineage seed for visual diversity
  const foundingLineages = ['aa00', 'ff55', '77bb'];
  for (let i = 0; i < 3; i++) {
    const c = createCreature(
      WORLD_W / 2 + (Math.random() - 0.5) * 4,
      WORLD_H / 2 + (Math.random() - 0.5) * 4
    );
    c.lineage = foundingLineages[i];
    state.creatures.push(c);
  }
  // Spawn initial food so creatures don't starve before first tree drop
  for (let i = 0; i < 3; i++) {
    state.food.push(createFood(
      WORLD_W / 2 + (Math.random() - 0.5) * 6,
      WORLD_H / 2 + (Math.random() - 0.5) * 6
    ));
  }
  console.log(`World init: ${state.creatures.length} creatures, ${state.trees.length} trees, ${state.food.length} food`);
}

// ── RENDER ─────────────────────────────────────────────────

function render(ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, tick: number): void {
  const w = canvas.width;
  const h = canvas.height;

  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, w, h);

  // Center camera so world middle is at screen center
  const midWx = WORLD_W / 2;
  const midWy = WORLD_H / 2;
  state.camera.x = w / 2 - (midWx - midWy) * (TILE_W / 2);
  state.camera.y = h / 2 - (midWx + midWy) * (TILE_H / 2);

  // Ground tiles with optional pollution overlay
  const pl = state.pollutionLevel || 0;
  for (let wy = 0; wy < WORLD_H; wy++) {
    for (let wx = 0; wx < WORLD_W; wx++) {
      const { x: sx, y: sy } = worldToScreen(wx, wy);
      if (sx < -TILE_W * 2 || sx > w + TILE_W * 2 || sy < -TILE_H * 2 || sy > h + TILE_H * 2) continue;
      drawIsoDiamond(ctx, sx, sy, COLORS.grass[(wx * 7 + wy * 13) % 4]);
      ctx.strokeStyle = 'rgba(0,0,0,0.1)';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(sx, sy - TILE_H / 2);
      ctx.lineTo(sx + TILE_W / 2, sy);
      ctx.lineTo(sx, sy + TILE_H / 2);
      ctx.lineTo(sx - TILE_W / 2, sy);
      ctx.closePath();
      ctx.stroke();

      // Feature 4: Pollution overlay at world edges
      if (pl > 0) {
        const distFromEdge = Math.min(wx, wy, WORLD_W - 1 - wx, WORLD_H - 1 - wy);
        const edgeBand = 3; // tiles deep from edge
        if (distFromEdge < edgeBand) {
          const strength = (edgeBand - distFromEdge) / edgeBand;
          const alpha = strength * (pl / 10) * 0.7;
          ctx.fillStyle = `rgba(136, 51, 170, ${alpha.toFixed(2)})`;
          ctx.beginPath();
          ctx.moveTo(sx, sy - TILE_H / 2);
          ctx.lineTo(sx + TILE_W / 2, sy);
          ctx.lineTo(sx, sy + TILE_H / 2);
          ctx.lineTo(sx - TILE_W / 2, sy);
          ctx.closePath();
          ctx.fill();
        }
      }
    }
  }

  // Trees (depth sorted)
  [...state.trees].sort((a, b) => (a.x + a.y) - (b.x + b.y)).forEach(tree => {
    const { x: sx, y: sy } = worldToScreen(tree.x, tree.y);
    drawTree(ctx, sx, sy, tree);
  });

  // Feature 3: Draw bones
  for (const bone of state.bones) {
    drawBone(ctx, bone);
  }

  // Food items (draw shadows first, then apples)
  for (const item of state.food) {
    if (!item.eaten) drawFood(ctx, item);
  }

  // Alive creatures (depth sorted)
  state.creatures.filter(c => c.alive)
    .sort((a, b) => (a.x + a.y) - (b.x + b.y))
    .forEach(c => {
      const { x: sx, y: sy } = worldToScreen(c.x, c.y);
      drawCreature(ctx, sx, sy, c, tick);
    });

  // Dead creatures fade out
  state.creatures.filter(c => !c.alive && c.diedAt > 0).forEach(c => {
    const { x: sx, y: sy } = worldToScreen(c.x, c.y);
    ctx.fillStyle = COLORS.creatureDead;
    ctx.globalAlpha = Math.max(0, 1 - (tick - c.diedAt) / 300);
    ctx.beginPath();
    ctx.arc(sx, sy - 4, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  });

  // Hover indicator
  const hw = state.mouseWorld;
  if (hw.x >= 0 && hw.x < WORLD_W && hw.y >= 0 && hw.y < WORLD_H) {
    const { x: sx, y: sy } = worldToScreen(hw.x, hw.y);
    ctx.strokeStyle = state.tool === 'feed' ? 'rgba(255, 100, 100, 0.5)' : 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(sx, sy - TILE_H / 2);
    ctx.lineTo(sx + TILE_W / 2, sy);
    ctx.lineTo(sx, sy + TILE_H / 2);
    ctx.lineTo(sx - TILE_W / 2, sy);
    ctx.closePath();
    ctx.stroke();
  }

  // Event log — scrolling dim green text at bottom-left (Plaything vibes)
  if (state.lastEvent && state.lastEventTimer > 0) {
    ctx.globalAlpha = Math.min(1, state.lastEventTimer / 30);
    ctx.fillStyle = '#00ff88';
    ctx.font = '11px "Press Start 2P", monospace';
    ctx.fillText(`> ${state.lastEvent.slice(0, 50)}`, 12, h - 8);
    ctx.globalAlpha = 1;
  }

  // Feature 5: World Events log panel (bottom-right)
  if (state.worldEvents.length > 0) {
    const panelX = w - 240;
    const panelY = h - 80;
    const panelW = 228;
    const lineH = 14;
    const displayEvents = state.worldEvents.slice(0, 3);
    const panelH = 24 + displayEvents.length * lineH;

    ctx.globalAlpha = 0.75;
    ctx.fillStyle = 'rgba(10, 8, 20, 0.85)';
    ctx.fillRect(panelX, panelY, panelW, panelH);
    ctx.strokeStyle = 'rgba(136, 51, 170, 0.6)';
    ctx.lineWidth = 1;
    ctx.strokeRect(panelX, panelY, panelW, panelH);
    ctx.globalAlpha = 1;

    ctx.fillStyle = 'rgba(136, 51, 170, 0.9)';
    ctx.font = '8px monospace';
    ctx.fillText('\u256D\u2500\u2500 WORLD \u2500\u2500\u256E', panelX + 6, panelY + 12);

    ctx.fillStyle = 'rgba(180, 150, 200, 0.6)';
    ctx.font = '8px monospace';
    displayEvents.forEach((ev, i) => {
      const truncated = ev.slice(0, 34);
      ctx.fillText(`> ${truncated}`, panelX + 6, panelY + 24 + i * lineH);
    });
  }

  // Observer panel — drawn last, always on top
  drawObserver(ctx, w, h);
  if (state.petitionVisible && state.throngPetition.length > 0) {
    drawPetitionPanel(ctx, w, h);
  }
}

function drawPetitionPanel(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const pw = 360, ph = 180 + state.throngPetition.length * 38;
  const px = Math.floor(w / 2 - pw / 2);
  const py = Math.floor(h / 2 - ph / 2);

  // Backdrop
  ctx.fillStyle = 'rgba(4, 6, 18, 0.95)';
  ctx.fillRect(px, py, pw, ph);
  ctx.strokeStyle = '#8833aa';
  ctx.lineWidth = 1;
  ctx.strokeRect(px, py, pw, ph);

  // Header
  ctx.fillStyle = 'rgba(136, 51, 170, 0.3)';
  ctx.fillRect(px, py, pw, 32);
  ctx.font = '9px "Press Start 2P", monospace';
  ctx.fillStyle = '#cc88ff';
  ctx.fillText('THE THRONG PETITIONS THE GOD', px + 12, py + 20);

  ctx.font = '7px "Press Start 2P", monospace';
  ctx.fillStyle = '#667799';
  ctx.fillText(`[ ${state.creatures.filter(c => c.alive).length} voices · ${epochName(state.epoch ?? 0)} epoch · god is ${state.godRelationship} ]`, px + 12, py + 44);

  // Petition items
  state.throngPetition.forEach((p, i) => {
    const iy = py + 58 + i * 38;
    const urgencyColor = p.urgency >= 8 ? '#ff6644' : p.urgency >= 5 ? '#ffaa44' : '#aabbcc';

    // Urgency bar
    ctx.fillStyle = urgencyColor;
    ctx.fillRect(px + 8, iy, 4, 28);

    // Text
    ctx.font = '7px "Press Start 2P", monospace';
    ctx.fillStyle = '#ddeeff';
    const words = p.text.split(' ');
    let line = '', line2 = '';
    for (const w of words) {
      if ((line + w).length < 40) line += (line ? ' ' : '') + w;
      else line2 += (line2 ? ' ' : '') + w;
    }
    ctx.fillText(line, px + 20, iy + 12);
    if (line2) { ctx.fillStyle = '#99aabb'; ctx.fillText(line2, px + 20, iy + 24); }

    // Grant / Deny buttons
    const btnW = 44, btnH = 16;
    const grantX = px + pw - 104, denyX = px + pw - 54;
    const btnY = iy + 6;

    ctx.fillStyle = '#224422';
    ctx.fillRect(grantX, btnY, btnW, btnH);
    ctx.fillStyle = '#442222';
    ctx.fillRect(denyX, btnY, btnW, btnH);

    ctx.font = '6px "Press Start 2P", monospace';
    ctx.fillStyle = '#44ff88';
    ctx.fillText('GRANT', grantX + 6, btnY + 10);
    ctx.fillStyle = '#ff4444';
    ctx.fillText('DENY', denyX + 8, btnY + 10);
  });

  // Close hint
  ctx.font = '6px "Press Start 2P", monospace';
  ctx.fillStyle = '#334455';
  ctx.fillText('[ESC to dismiss and ignore]', px + 12, py + ph - 10);
}

function drawObserver(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const obs = state.observer;
  const pw = 200;
  const px = w - pw - 4;
  const py = 40;
  const lineH = 14;
  const pad = 10;

  const lines: Array<{ text: string; color: string; dim?: boolean }> = [];

  // FUNCTION section
  lines.push({ text: 'FUNCTION', color: '#6688cc' });
  lines.push({ text: `> ${obs.fn}`, color: '#aabbee' });
  if (obs.fnArgs.length) {
    lines.push({ text: `  ${obs.fnArgs.join(', ')}`, color: '#6677aa', dim: true });
  }
  lines.push({ text: '', color: '' });

  // ACTING ON section
  lines.push({ text: 'ACTING ON', color: '#6688cc' });
  lines.push({ text: `> ${obs.target}`, color: '#aabbee' });
  for (const d of obs.targetDetail) {
    lines.push({ text: `  ${d}`, color: '#6677aa', dim: true });
  }
  if (obs.hoverComment) {
    lines.push({ text: `  ${obs.hoverComment.slice(0, 36)}`, color: '#88aaff' });
    if (obs.hoverComment.length > 36) {
      lines.push({ text: `  ${obs.hoverComment.slice(36, 72)}`, color: '#88aaff' });
    }
  }
  lines.push({ text: '', color: '' });

  // OUTPUT section
  lines.push({ text: 'OUTPUT', color: '#6688cc' });
  if (obs.output.length && (obs.outputAge ?? 999) < 300) {
    const alpha = Math.max(0.2, 1 - (obs.outputAge ?? 0) / 300);
    for (const o of obs.output) {
      lines.push({ text: o.slice(0, 36), color: `rgba(180, 220, 180, ${alpha})` });
    }
  } else {
    lines.push({ text: '  awaiting action...', color: '#334455', dim: true });
  }
  lines.push({ text: '', color: '' });

  // WORLD section
  lines.push({ text: 'WORLD', color: '#6688cc' });
  const alive = state.creatures.filter(c => c.alive).length;
  lines.push({ text: `> ${epochName(state.epoch ?? 0)} · pop ${alive}`, color: '#aabbee' });
  lines.push({ text: `  pollution ${state.pollutionLevel ?? 0}/10 · bones ${state.resources.bones}`, color: '#6677aa', dim: true });
  if (state.observedPrinciples?.length) {
    lines.push({ text: '', color: '' });
    lines.push({ text: 'LAWS', color: '#6688cc' });
    for (const p of state.observedPrinciples.slice(0, 2)) {
      const short = p.replace('[4:19] ', '').slice(0, 34);
      lines.push({ text: `  ${short}`, color: '#445566', dim: true });
    }
  }

  const ph = lines.length * lineH + pad * 2;

  // Panel background
  ctx.save();
  ctx.beginPath();
  ctx.rect(px, py, pw, ph);
  ctx.clip();

  ctx.fillStyle = 'rgba(8, 12, 24, 0.88)';
  ctx.fillRect(px, py, pw, ph);
  ctx.strokeStyle = 'rgba(40, 60, 120, 0.6)';
  ctx.lineWidth = 1;
  ctx.strokeRect(px, py, pw, ph);

  // Title
  ctx.fillStyle = 'rgba(60, 90, 180, 0.5)';
  ctx.fillRect(px, py, pw, 16);
  ctx.font = '8px "Press Start 2P", monospace';
  ctx.fillStyle = '#8899cc';
  ctx.fillText('OBSERVER', px + pad, py + 11);

  // Content lines — clamp text to fit panel width
  const maxChars = Math.floor((pw - pad * 2) / 6);  // ~6px per char at 8px font
  ctx.font = '8px "Press Start 2P", monospace';
  let ly = py + 24;
  for (const line of lines) {
    if (!line.text) { ly += lineH * 0.5; continue; }
    ctx.fillStyle = line.color || '#445566';
    ctx.fillText(line.text.slice(0, maxChars), px + pad, ly);
    ly += lineH;
  }
  ctx.restore();
}

// ── HUD ────────────────────────────────────────────────────

function updateHUD(): void {
  const alive = state.creatures.filter(c => c.alive).length;
  const popEl = document.getElementById('population');
  const woodEl = document.getElementById('wood');
  const gemsEl = document.getElementById('gems');
  const bonesEl = document.getElementById('bones');
  const profileEl = document.getElementById('player-profile');
  if (popEl) popEl.textContent = `Pop: ${alive}`;
  if (woodEl) woodEl.textContent = `Wood: ${state.resources.wood}`;
  if (gemsEl) gemsEl.textContent = `Gems: ${state.resources.gems}`;
  if (bonesEl) bonesEl.textContent = `Bones: ${state.resources.bones}`;
  // Feature 2: Player profile display
  if (profileEl) {
    profileEl.textContent = state.playerProfile ? `[ ${state.playerProfile} ]` : '';
  }
}

// ── INPUT ──────────────────────────────────────────────────

function setupInput(canvas: HTMLCanvasElement): void {
  // ESC dismisses petition panel
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape' && state.petitionVisible) {
      state.petitionVisible = false;
    }
    // P key triggers petition (for testing)
    if (e.key === 'p' || e.key === 'P') {
      void synthesizePetition();
    }
  });
  document.querySelectorAll<HTMLButtonElement>('.tool').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tool').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.tool = btn.dataset.tool as ToolType;
    });
  });

  canvas.addEventListener('mousemove', (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    state.mouseScreen = {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
    state.mouseWorld = screenToWorldTile(state.mouseScreen.x, state.mouseScreen.y);
  });

  canvas.addEventListener('click', (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const sx = (e.clientX - rect.left) * scaleX;
    const sy = (e.clientY - rect.top) * scaleY;

    // Petition panel click handling
    if (state.petitionVisible && state.throngPetition.length > 0) {
      const pw = 360, ph = 180 + state.throngPetition.length * 38;
      const px = Math.floor(canvas.width / 2 - pw / 2);
      const py = Math.floor((canvas.height) / 2 - ph / 2);
      state.throngPetition.forEach((_, i) => {
        const iy = py + 58 + i * 38;
        const grantX = px + pw - 104, denyX = px + pw - 54;
        const btnY = iy + 6;
        if (sx >= grantX && sx <= grantX + 44 && sy >= btnY && sy <= btnY + 16) {
          grantPetition(i);
        } else if (sx >= denyX && sx <= denyX + 44 && sy >= btnY && sy <= btnY + 16) {
          denyPetition(i);
        }
      });
      return;
    }

    // Use fractional world coords for accurate creature click detection
    const { x: wx, y: wy } = screenToWorld(sx, sy);

    // Feed tool: drop food at click position (not direct-feed)
    if (state.tool === 'feed') {
      const food = createFood(wx, wy);
      state.food.push(food);
      return;
    }

    // Chop tool: check bones first (Feature 3)
    if (state.tool === 'chop') {
      let harvested = false;
      state.bones = state.bones.filter(bone => {
        const dist = Math.sqrt((bone.x - wx) ** 2 + (bone.y - wy) ** 2);
        if (dist < 1.5) {
          state.resources.bones = (state.resources.bones || 0) + 1;
          harvested = true;
          return false; // remove from array
        }
        return true;
      });

      if (!harvested) {
        // Check trees
        let nearestTree: Tree | null = null;
        let nearestTreeDist = Infinity;
        for (const t of state.trees) {
          if (t.health <= 0) continue;
          const dist = (t.x - wx) ** 2 + (t.y - wy) ** 2;
          if (dist < nearestTreeDist && dist < 6.25) {
            nearestTree = t;
            nearestTreeDist = dist;
          }
        }
        if (nearestTree) {
          nearestTree.health--;
          state.resources.wood += 2;
          if (nearestTree.health <= 0) state.resources.wood += 3;
        }
      }
      return;
    }

    // Find nearest alive creature within 2.5 world units
    let nearest: Creature | null = null;
    let nearestDist = Infinity;
    for (const c of state.creatures) {
      if (!c.alive) continue;
      const dist = (c.x - wx) ** 2 + (c.y - wy) ** 2;
      if (dist < nearestDist && dist < 6.25) {
        nearest = c;
        nearestDist = dist;
      }
    }

    if (nearest) {
      // Call LLM to define outcome for any non-feed tool
      void applyToolToCreature(state.tool, nearest);
    }
  });
}

// ── MAIN ───────────────────────────────────────────────────

function main(): void {
  const canvas = document.getElementById('game') as HTMLCanvasElement;
  const ctx = canvas.getContext('2d')!;

  // Read API key from localStorage or URL param
  const key = localStorage.getItem('anthropic_key') || new URLSearchParams(window.location.search).get('key') || '';
  (window as unknown as Record<string, string>)['__ANTHROPIC_KEY__'] = key;
  if (!key) {
    console.warn('No ANTHROPIC_API_KEY — using deterministic fallback. Set via ?key=sk-... or localStorage.anthropic_key');
  }

  function resize(): void {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight - 48;
  }
  resize();
  window.addEventListener('resize', resize);

  // Auto-save on unload
  window.addEventListener('beforeunload', saveWorldState);

  loadWorldState((loaded) => {
    if (!loaded) {
      initWorld();
    }
    setupInput(canvas);

    // Auto-save every 30 seconds
    setInterval(saveWorldState, 30_000);

    let lastTime = performance.now();
    let worldCheckTimer = 0;
    let interactionTimer = 0;

    function loop(now: number): void {
      const dt = Math.min((now - lastTime) / 16.67, 3);
      lastTime = now;
      state.tick++;

      // Update food physics
      updateFood(dt);

      // Update tree food drops
      updateTrees(dt);

      for (const c of state.creatures) {
        updateCreature(c, dt);
      }

      // Update observer panel state
      updateObserver(dt);

      state.creatures = state.creatures.filter(c =>
        c.alive || (c.diedAt > 0 && (state.tick - c.diedAt) < 300)
      );

      // Tick down event log timer
      if (state.lastEventTimer > 0) {
        state.lastEventTimer -= dt;
      }

      // Interaction engine — run every 30 frames (twice per second at 60fps)
      interactionTimer += dt;
      if (interactionTimer >= 30) {
        interactionTimer = 0;
        runInteractionSystem();
      }

      // Feature 4: Check world thresholds every 60 frames
      worldCheckTimer += dt;
      if (worldCheckTimer >= 60) {
        worldCheckTimer = 0;
        void checkWorldThresholds();

        // 4:19 PM daily holistic evolution + petition (Apr 19 — birthday of this game)
        const evNow = new Date();
        const evToday = evNow.toDateString();
        const is419 = evNow.getHours() === 16 && evNow.getMinutes() === 19;
        if (is419 && lastEvolutionDate !== evToday) {
          lastEvolutionDate = evToday;
          void runHolisticEvolution();
          void synthesizePetition();  // present throng's petitions to the god
        }

        // Occasionally prompt a random alive creature to generate a proposal (~every 2 min)
        if (state.tick % 7200 === 0) {
          const alive = state.creatures.filter(c => c.alive);
          if (alive.length > 0) {
            const randomCreature = alive[Math.floor(Math.random() * alive.length)];
            void generateCreatureProposal(randomCreature);
          }
        }
      }

      render(ctx, canvas, state.tick);
      updateHUD();
      requestAnimationFrame(loop);
    }

    requestAnimationFrame(loop);
  });
}

main();
