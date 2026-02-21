/**
 * Thronglets — retro pixel-art god-game inspired by Black Mirror: Plaything
 *
 * Isometric world with yellow fuzzy creatures that need feeding, cleaning,
 * and playing with. They multiply when happy. They die when neglected.
 * The population grows exponentially. You can't keep up. That's the point.
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
  splitTimer: number;
  state: 'idle' | 'walking' | 'eating' | 'bathing' | 'playing' | 'dying';
  stateTimer: number;
  animFrame: number;
  size: number;
  bobPhase: number;
}

interface Tree {
  x: number;
  y: number;
  type: 'apple';
  health: number;
  regrowTimer: number;
}

type ToolType = 'feed' | 'clean' | 'play' | 'chop';

interface GameState {
  creatures: Creature[];
  trees: Tree[];
  resources: { wood: number; gems: number };
  tool: ToolType;
  tick: number;
  camera: { x: number; y: number };
  mouseWorld: { x: number; y: number };
  mouseScreen: { x: number; y: number };
}

// ── CONSTANTS ──────────────────────────────────────────────

const TILE_W = 32;
const TILE_H = 16;
const WORLD_W = 20;
const WORLD_H = 20;

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

// ── GAME STATE ─────────────────────────────────────────────

const state: GameState = {
  creatures: [],
  trees: [],
  resources: { wood: 0, gems: 0 },
  tool: 'feed',
  tick: 0,
  camera: { x: 0, y: 0 },
  mouseWorld: { x: 0, y: 0 },
  mouseScreen: { x: 0, y: 0 },
};

// ── FACTORIES ──────────────────────────────────────────────

function createCreature(wx: number, wy: number): Creature {
  return {
    x: wx, y: wy, vx: 0, vy: 0,
    hunger: 100, clean: 100, happiness: 100,
    age: 0, alive: true, splitTimer: 0,
    state: 'idle', stateTimer: 0, animFrame: 0,
    size: 1, bobPhase: Math.random() * Math.PI * 2,
  };
}

function createTree(wx: number, wy: number): Tree {
  return { x: wx, y: wy, type: 'apple', health: 3, regrowTimer: 0 };
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
    x: Math.floor((cx / (TILE_W / 2) + cy / (TILE_H / 2)) / 2),
    y: Math.floor((cy / (TILE_H / 2) - cx / (TILE_W / 2)) / 2),
  };
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
  drawPixelRect(ctx, sx - 2, sy - 16, 4, 12, COLORS.treeTrunk);
  const leafColor = tree.health > 0 ? COLORS.treeLeaf : '#555';
  ctx.fillStyle = leafColor;
  ctx.beginPath();
  ctx.arc(sx, sy - 20, 8, 0, Math.PI * 2);
  ctx.fill();
  if (tree.type === 'apple' && tree.health > 0) {
    drawPixelRect(ctx, sx - 4, sy - 22, 3, 3, COLORS.food);
    drawPixelRect(ctx, sx + 2, sy - 18, 3, 3, COLORS.food);
  }
}

function drawCreature(ctx: CanvasRenderingContext2D, sx: number, sy: number, creature: Creature, tick: number): void {
  if (!creature.alive) return;

  const bob = Math.sin(creature.bobPhase + tick * 0.08) * 2;
  const cy = sy + bob;

  let bodyColor: string;
  if (creature.hunger < 20 || creature.clean < 20 || creature.happiness < 20) {
    bodyColor = COLORS.creatureSad;
  } else {
    bodyColor = creature.happiness > 70 ? COLORS.creatureHappy : COLORS.creature;
  }

  const s = 8 + Math.min(creature.age / 100, 4);

  // Body
  ctx.fillStyle = bodyColor;
  ctx.beginPath();
  ctx.ellipse(sx, cy - s, s, s * 0.8, 0, 0, Math.PI * 2);
  ctx.fill();

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
}

// ── GAME LOGIC ─────────────────────────────────────────────

function updateCreature(c: Creature, dt: number): void {
  if (!c.alive) return;

  c.age += dt;
  c.hunger = Math.max(0, c.hunger - dt * 0.5);
  c.clean = Math.max(0, c.clean - dt * 0.3);
  c.happiness = Math.max(0, c.happiness - dt * 0.2);
  c.bobPhase += dt * 0.1;
  c.stateTimer -= dt;

  if (c.hunger <= 0) {
    c.alive = false;
    c.state = 'dying';
    return;
  }

  if (c.hunger > 60 && c.clean > 60) {
    c.happiness = Math.min(100, c.happiness + dt * 0.3);
  }

  // Split when happy enough for long enough
  if (c.happiness > 70 && c.hunger > 50 && c.clean > 50) {
    c.splitTimer += dt;
    if (c.splitTimer > 300) {
      c.splitTimer = 0;
      const newC = createCreature(
        c.x + (Math.random() - 0.5) * 3,
        c.y + (Math.random() - 0.5) * 3
      );
      newC.hunger = 60;
      newC.clean = 80;
      newC.happiness = 80;
      state.creatures.push(newC);
    }
  }

  // Random wandering
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

  c.x = Math.max(0, Math.min(WORLD_W - 1, c.x + c.vx * dt));
  c.y = Math.max(0, Math.min(WORLD_H - 1, c.y + c.vy * dt));
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
  for (let i = 0; i < 3; i++) {
    state.creatures.push(createCreature(
      WORLD_W / 2 + (Math.random() - 0.5) * 4,
      WORLD_H / 2 + (Math.random() - 0.5) * 4
    ));
  }
  console.log(`World init: ${state.creatures.length} creatures, ${state.trees.length} trees`);
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

  // Ground tiles
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
    }
  }

  // Trees (depth sorted)
  [...state.trees].sort((a, b) => (a.x + a.y) - (b.x + b.y)).forEach(tree => {
    const { x: sx, y: sy } = worldToScreen(tree.x, tree.y);
    drawTree(ctx, sx, sy, tree);
  });

  // Alive creatures (depth sorted)
  state.creatures.filter(c => c.alive)
    .sort((a, b) => (a.x + a.y) - (b.x + b.y))
    .forEach(c => {
      const { x: sx, y: sy } = worldToScreen(c.x, c.y);
      drawCreature(ctx, sx, sy, c, tick);
    });

  // Dead creatures fade out
  state.creatures.filter(c => !c.alive).forEach(c => {
    const { x: sx, y: sy } = worldToScreen(c.x, c.y);
    ctx.fillStyle = COLORS.creatureDead;
    ctx.globalAlpha = Math.max(0, 1 - (tick - c.age) / 200);
    ctx.beginPath();
    ctx.arc(sx, sy - 4, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  });

  // Hover indicator
  const hw = state.mouseWorld;
  if (hw.x >= 0 && hw.x < WORLD_W && hw.y >= 0 && hw.y < WORLD_H) {
    const { x: sx, y: sy } = worldToScreen(hw.x, hw.y);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(sx, sy - TILE_H / 2);
    ctx.lineTo(sx + TILE_W / 2, sy);
    ctx.lineTo(sx, sy + TILE_H / 2);
    ctx.lineTo(sx - TILE_W / 2, sy);
    ctx.closePath();
    ctx.stroke();
  }
}

// ── HUD ────────────────────────────────────────────────────

function updateHUD(): void {
  const alive = state.creatures.filter(c => c.alive).length;
  document.getElementById('population')!.textContent = `Pop: ${alive}`;
  document.getElementById('wood')!.textContent = `Wood: ${state.resources.wood}`;
  document.getElementById('gems')!.textContent = `Gems: ${state.resources.gems}`;
}

// ── INPUT ──────────────────────────────────────────────────

function setupInput(canvas: HTMLCanvasElement): void {
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
    state.mouseWorld = screenToWorld(state.mouseScreen.x, state.mouseScreen.y);
  });

  canvas.addEventListener('click', (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const sx = (e.clientX - rect.left) * scaleX;
    const sy = (e.clientY - rect.top) * scaleY;
    const { x: wx, y: wy } = screenToWorld(sx, sy);

    // Find nearest alive creature
    let nearest: Creature | null = null;
    let nearestDist = Infinity;
    for (const c of state.creatures) {
      if (!c.alive) continue;
      const dist = (c.x - wx) ** 2 + (c.y - wy) ** 2;
      if (dist < nearestDist && dist < 4) {
        nearest = c;
        nearestDist = dist;
      }
    }

    if (nearest) {
      switch (state.tool) {
        case 'feed': feedCreature(nearest); break;
        case 'clean': cleanCreature(nearest); break;
        case 'play': playWithCreature(nearest); break;
      }
    }

    if (state.tool === 'chop') {
      let nearestTree: Tree | null = null;
      let nearestTreeDist = Infinity;
      for (const t of state.trees) {
        if (t.health <= 0) continue;
        const dist = (t.x - wx) ** 2 + (t.y - wy) ** 2;
        if (dist < nearestTreeDist && dist < 4) {
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
  });
}

// ── BOOT SCREEN ────────────────────────────────────────────

function drawBootScreen(ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, callback: () => void): void {
  const w = canvas.width;
  const h = canvas.height;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, w, h);

  const lines = [
    'TUCKERSOFT SYSTEMS (C) 1994',
    '',
    'LOADING THRONGLETS V1.0',
    '========================',
    '',
    'INITIALIZING BIOME...',
    'SEEDING POPULATION...',
    'CALIBRATING NURTURE PROTOCOLS...',
    '',
    'READY.',
    '',
    '> RUN THRONGLETS.EXE',
  ];

  let lineIdx = 0;
  let charIdx = 0;

  function typeLine(): void {
    if (lineIdx >= lines.length) {
      setTimeout(callback, 800);
      return;
    }

    const line = lines[lineIdx];
    if (charIdx <= line.length) {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, w, h);
      ctx.font = '14px "Press Start 2P", monospace';
      ctx.fillStyle = '#00ff00';

      for (let i = 0; i < lineIdx; i++) {
        ctx.fillText(lines[i], 20, 40 + i * 24);
      }
      ctx.fillText(line.substring(0, charIdx), 20, 40 + lineIdx * 24);

      if (Math.floor(Date.now() / 500) % 2 === 0) {
        const cursorX = 20 + charIdx * 9.5;
        ctx.fillRect(cursorX, 40 + lineIdx * 24 - 12, 10, 14);
      }

      charIdx++;
      setTimeout(typeLine, 30 + Math.random() * 40);
    } else {
      lineIdx++;
      charIdx = 0;
      setTimeout(typeLine, line === '' ? 100 : 200);
    }
  }

  typeLine();
}

// ── MAIN ───────────────────────────────────────────────────

function main(): void {
  const canvas = document.getElementById('game') as HTMLCanvasElement;
  const ctx = canvas.getContext('2d')!;

  function resize(): void {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight - 48;
  }
  resize();
  window.addEventListener('resize', resize);

  // Click or press any key to skip boot screen
  let booting = true;
  const skipBoot = () => {
    if (!booting) return;
    booting = false;
    initWorld();
    setupInput(canvas);
    startGame();
  };
  canvas.addEventListener('click', skipBoot, { once: true });
  document.addEventListener('keydown', skipBoot, { once: true });

  drawBootScreen(ctx, canvas, skipBoot);

  function startGame() {

    let lastTime = performance.now();

    function loop(now: number): void {
      const dt = Math.min((now - lastTime) / 16.67, 3);
      lastTime = now;
      state.tick++;

      for (const c of state.creatures) {
        updateCreature(c, dt);
      }

      state.creatures = state.creatures.filter(c =>
        c.alive || (state.tick - c.age) < 500
      );

      render(ctx, canvas, state.tick);
      updateHUD();
      requestAnimationFrame(loop);
    }

    requestAnimationFrame(loop);
  }
}

main();
