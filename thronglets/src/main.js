/**
 * Thronglets — retro pixel-art god-game inspired by Black Mirror: Plaything
 *
 * Isometric world with yellow fuzzy creatures that need feeding, cleaning,
 * and playing with. They multiply when happy. They die when neglected.
 * The population grows exponentially. You can't keep up. That's the point.
 */

// ── CONSTANTS ──────────────────────────────────────────────
const TILE_W = 32;
const TILE_H = 16;
const WORLD_W = 20;  // grid tiles wide
const WORLD_H = 20;  // grid tiles tall
const PIXEL_SCALE = 2;

// Color palette — retro VGA-inspired
const COLORS = {
  grass:     ['#2d5a27', '#3a7d32', '#4a9a3c', '#3a7d32'],  // 4 grass shades
  dirt:      '#8b6914',
  water:     '#2856a6',
  treeTrunk: '#5c3a1e',
  treeLeaf:  '#2d8a2e',
  creature:  '#ffd700',  // yellow thronglet
  creatureHappy: '#ffe44d',
  creatureSad:   '#cc9900',
  creatureDead:  '#666666',
  egg:       '#fff5cc',
  food:      '#ff4444',
  pollution: '#8833aa',
  ui_bg:     '#16213e',
  ui_border: '#0f3460',
  ui_accent: '#e94560',
};

// ── GAME STATE ─────────────────────────────────────────────
const state = {
  creatures: [],
  trees: [],
  buildings: [],
  resources: { wood: 0, gems: 0 },
  tool: 'feed',
  tick: 0,
  camera: { x: 0, y: 0 },
  mouseWorld: { x: 0, y: 0 },
  mouseScreen: { x: 0, y: 0 },
};

// ── CREATURE ───────────────────────────────────────────────
function createCreature(wx, wy) {
  return {
    x: wx,
    y: wy,
    vx: 0,
    vy: 0,
    hunger: 100,     // 0 = starving, 100 = full
    clean: 100,      // 0 = filthy, 100 = spotless
    happiness: 100,  // 0 = miserable, 100 = ecstatic
    age: 0,
    alive: true,
    splitTimer: 0,   // counts up; splits at 300
    state: 'idle',   // idle, walking, eating, bathing, playing, dying
    stateTimer: 0,
    animFrame: 0,
    size: 1,         // grows slightly with age
    bobPhase: Math.random() * Math.PI * 2,
  };
}

function createTree(wx, wy) {
  return { x: wx, y: wy, type: 'apple', health: 3, regrowTimer: 0 };
}

// ── ISO PROJECTION ─────────────────────────────────────────
function worldToScreen(wx, wy) {
  const sx = (wx - wy) * (TILE_W / 2) + state.camera.x;
  const sy = (wx + wy) * (TILE_H / 2) + state.camera.y;
  return { x: sx, y: sy };
}

function screenToWorld(sx, sy) {
  const cx = sx - state.camera.x;
  const cy = sy - state.camera.y;
  const wx = (cx / (TILE_W / 2) + cy / (TILE_H / 2)) / 2;
  const wy = (cy / (TILE_H / 2) - cx / (TILE_W / 2)) / 2;
  return { x: Math.floor(wx), y: Math.floor(wy) };
}

// ── PIXEL ART DRAWING ──────────────────────────────────────
function drawPixelRect(ctx, x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.floor(x), Math.floor(y), w, h);
}

function drawIsoDiamond(ctx, sx, sy, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(sx, sy - TILE_H / 2);
  ctx.lineTo(sx + TILE_W / 2, sy);
  ctx.lineTo(sx, sy + TILE_H / 2);
  ctx.lineTo(sx - TILE_W / 2, sy);
  ctx.closePath();
  ctx.fill();
}

function drawTree(ctx, sx, sy, tree) {
  // Trunk — 4px wide brown rectangle
  drawPixelRect(ctx, sx - 2, sy - 16, 4, 12, COLORS.treeTrunk);
  // Canopy — green diamond/circle
  const leafColor = tree.health > 0 ? COLORS.treeLeaf : '#555';
  ctx.fillStyle = leafColor;
  ctx.beginPath();
  ctx.arc(sx, sy - 20, 8, 0, Math.PI * 2);
  ctx.fill();
  // Fruit dots if apple tree
  if (tree.type === 'apple' && tree.health > 0) {
    drawPixelRect(ctx, sx - 4, sy - 22, 3, 3, COLORS.food);
    drawPixelRect(ctx, sx + 2, sy - 18, 3, 3, COLORS.food);
  }
}

function drawCreature(ctx, sx, sy, creature, tick) {
  if (!creature.alive) return;

  const bob = Math.sin(creature.bobPhase + tick * 0.08) * 2;
  const cy = sy + bob;

  // Body color based on mood
  let bodyColor;
  if (creature.hunger < 20 || creature.clean < 20 || creature.happiness < 20) {
    bodyColor = COLORS.creatureSad;
  } else {
    bodyColor = creature.happiness > 70 ? COLORS.creatureHappy : COLORS.creature;
  }

  const s = 4 + Math.min(creature.age / 100, 2);  // size grows with age

  // Body — round yellow blob
  ctx.fillStyle = bodyColor;
  ctx.beginPath();
  ctx.ellipse(sx, cy - s, s, s * 0.8, 0, 0, Math.PI * 2);
  ctx.fill();

  // Eyes — two black dots
  const eyeY = cy - s - 1;
  drawPixelRect(ctx, sx - 2, eyeY, 2, 2, '#000');
  drawPixelRect(ctx, sx + 1, eyeY, 2, 2, '#000');

  // Mouth — happy or sad
  if (creature.happiness > 50) {
    // Happy smile
    drawPixelRect(ctx, sx - 1, eyeY + 3, 3, 1, '#000');
  } else {
    // Sad frown
    drawPixelRect(ctx, sx - 1, eyeY + 4, 3, 1, '#000');
  }

  // Status indicators (floating above)
  if (creature.hunger < 30) {
    ctx.fillStyle = COLORS.food;
    ctx.font = '8px monospace';
    ctx.fillText('!', sx - 2, cy - s * 2 - 4);
  }
  if (creature.clean < 30) {
    ctx.fillStyle = '#88aaff';
    ctx.font = '8px monospace';
    ctx.fillText('~', sx + 4, cy - s * 2 - 4);
  }
}

// ── GAME LOGIC ─────────────────────────────────────────────
function updateCreature(c, dt) {
  if (!c.alive) return;

  c.age += dt;
  c.hunger = Math.max(0, c.hunger - dt * 0.5);
  c.clean = Math.max(0, c.clean - dt * 0.3);
  c.happiness = Math.max(0, c.happiness - dt * 0.2);
  c.bobPhase += dt * 0.1;
  c.stateTimer -= dt;

  // Die if too hungry
  if (c.hunger <= 0) {
    c.alive = false;
    c.state = 'dying';
    return;
  }

  // Mood affects happiness
  if (c.hunger > 60 && c.clean > 60) {
    c.happiness = Math.min(100, c.happiness + dt * 0.3);
  }

  // Split when happy enough for long enough
  if (c.happiness > 70 && c.hunger > 50 && c.clean > 50) {
    c.splitTimer += dt;
    if (c.splitTimer > 300) {
      c.splitTimer = 0;
      // Spawn new creature nearby
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

  // Move
  c.x += c.vx * dt;
  c.y += c.vy * dt;

  // Keep in bounds
  c.x = Math.max(0, Math.min(WORLD_W - 1, c.x));
  c.y = Math.max(0, Math.min(WORLD_H - 1, c.y));
}

function feedCreature(c) {
  if (!c.alive) return;
  c.hunger = Math.min(100, c.hunger + 40);
  c.happiness = Math.min(100, c.happiness + 10);
  c.state = 'eating';
  c.stateTimer = 30;
}

function cleanCreature(c) {
  if (!c.alive) return;
  c.clean = Math.min(100, c.clean + 50);
  c.happiness = Math.min(100, c.happiness + 10);
  c.state = 'bathing';
  c.stateTimer = 30;
}

function playWithCreature(c) {
  if (!c.alive) return;
  c.happiness = Math.min(100, c.happiness + 30);
  c.state = 'playing';
  c.stateTimer = 40;
}

// ── WORLD GENERATION ───────────────────────────────────────
function initWorld() {
  // Place some initial trees
  for (let i = 0; i < 8; i++) {
    state.trees.push(createTree(
      3 + Math.floor(Math.random() * (WORLD_W - 6)),
      3 + Math.floor(Math.random() * (WORLD_H - 6))
    ));
  }

  // First creature — hatches from an egg
  const first = createCreature(WORLD_W / 2, WORLD_H / 2);
  state.creatures.push(first);
}

// ── RENDER ─────────────────────────────────────────────────
function render(ctx, canvas, tick) {
  const w = canvas.width;
  const h = canvas.height;

  // Clear with dark background
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, w, h);

  // Center camera on world
  state.camera.x = w / 2;
  state.camera.y = h / 4;

  // Draw ground tiles (isometric)
  for (let wy = 0; wy < WORLD_H; wy++) {
    for (let wx = 0; wx < WORLD_W; wx++) {
      const { x: sx, y: sy } = worldToScreen(wx, wy);
      // Skip if off screen
      if (sx < -TILE_W || sx > w + TILE_W || sy < -TILE_H || sy > h + TILE_H) continue;

      const grassIdx = ((wx * 7 + wy * 13) % 4);
      drawIsoDiamond(ctx, sx, sy, COLORS.grass[grassIdx]);

      // Grid lines (very subtle)
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

  // Draw trees (sorted by y for depth)
  const sortedTrees = [...state.trees].sort((a, b) => (a.x + a.y) - (b.x + b.y));
  for (const tree of sortedTrees) {
    const { x: sx, y: sy } = worldToScreen(tree.x, tree.y);
    drawTree(ctx, sx, sy, tree);
  }

  // Draw creatures (sorted by y for depth)
  const sortedCreatures = [...state.creatures].filter(c => c.alive)
    .sort((a, b) => (a.x + a.y) - (b.x + b.y));
  for (const c of sortedCreatures) {
    const { x: sx, y: sy } = worldToScreen(c.x, c.y);
    drawCreature(ctx, sx, sy, c, tick);
  }

  // Draw dead creatures as grey dots (fade out)
  for (const c of state.creatures.filter(c => !c.alive)) {
    const { x: sx, y: sy } = worldToScreen(c.x, c.y);
    ctx.fillStyle = COLORS.creatureDead;
    ctx.globalAlpha = Math.max(0, 1 - (tick - c.age) / 200);
    ctx.beginPath();
    ctx.arc(sx, sy - 4, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

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

// ── UPDATE HUD ─────────────────────────────────────────────
function updateHUD() {
  const alive = state.creatures.filter(c => c.alive).length;
  document.getElementById('population').textContent = `Pop: ${alive}`;
  document.getElementById('wood').textContent = `Wood: ${state.resources.wood}`;
  document.getElementById('gems').textContent = `Gems: ${state.resources.gems}`;
}

// ── INPUT ──────────────────────────────────────────────────
function setupInput(canvas) {
  // Tool selection
  document.querySelectorAll('.tool').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tool').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.tool = btn.dataset.tool;
    });
  });

  // Mouse tracking
  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    state.mouseScreen = {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
    state.mouseWorld = screenToWorld(state.mouseScreen.x, state.mouseScreen.y);
  });

  // Click to interact
  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const sx = (e.clientX - rect.left) * scaleX;
    const sy = (e.clientY - rect.top) * scaleY;
    const { x: wx, y: wy } = screenToWorld(sx, sy);

    // Find nearest alive creature to click
    let nearest = null;
    let nearestDist = Infinity;
    for (const c of state.creatures) {
      if (!c.alive) continue;
      const dx = c.x - wx;
      const dy = c.y - wy;
      const dist = dx * dx + dy * dy;
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
        case 'chop':
          // Chop nearest tree instead
          break;
      }
    }

    // Chop tool — find nearest tree
    if (state.tool === 'chop') {
      let nearestTree = null;
      let nearestTreeDist = Infinity;
      for (const t of state.trees) {
        if (t.health <= 0) continue;
        const dx = t.x - wx;
        const dy = t.y - wy;
        const dist = dx * dx + dy * dy;
        if (dist < nearestTreeDist && dist < 4) {
          nearestTree = t;
          nearestTreeDist = dist;
        }
      }
      if (nearestTree) {
        nearestTree.health--;
        state.resources.wood += 2;
        if (nearestTree.health <= 0) {
          state.resources.wood += 3;
        }
      }
    }
  });
}

// ── BOOT SCREEN ────────────────────────────────────────────
function drawBootScreen(ctx, canvas, callback) {
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

  function typeLine() {
    if (lineIdx >= lines.length) {
      setTimeout(callback, 800);
      return;
    }

    const line = lines[lineIdx];
    if (charIdx <= line.length) {
      // Redraw all previous lines + current partial
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, w, h);
      ctx.font = '14px "Press Start 2P", monospace';
      ctx.fillStyle = '#00ff00';

      for (let i = 0; i < lineIdx; i++) {
        ctx.fillText(lines[i], 20, 40 + i * 24);
      }
      ctx.fillText(line.substring(0, charIdx), 20, 40 + lineIdx * 24);

      // Blinking cursor
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

// ── MAIN LOOP ──────────────────────────────────────────────
function main() {
  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d');

  // Size canvas to window
  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight - 48;
  }
  resize();
  window.addEventListener('resize', resize);

  // Boot screen first, then game
  drawBootScreen(ctx, canvas, () => {
    initWorld();
    setupInput(canvas);

    let lastTime = performance.now();

    function loop(now) {
      const dt = Math.min((now - lastTime) / 16.67, 3);  // normalize to ~60fps units
      lastTime = now;
      state.tick++;

      // Update all creatures
      for (const c of state.creatures) {
        updateCreature(c, dt);
      }

      // Cull very old dead creatures
      state.creatures = state.creatures.filter(c =>
        c.alive || (state.tick - c.age) < 500
      );

      // Render
      render(ctx, canvas, state.tick);
      updateHUD();

      requestAnimationFrame(loop);
    }

    requestAnimationFrame(loop);
  });
}

// Start
main();
