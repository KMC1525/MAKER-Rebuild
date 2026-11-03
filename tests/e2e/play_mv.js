// Roteiro E2E (Playwright): joga o jogo gerado a partir do projeto sintético MV.
// uso: node play_mv.js <pasta-do-jogo> <prefixo-screenshots>
const { chromium } = require('playwright');
const game = process.argv[2], shots = process.argv[3] || '';
const results = [];
const check = (name, ok, extra) => { results.push({ name, ok: !!ok, extra }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (extra !== undefined ? ' ' + JSON.stringify(extra) : '')); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('PAGEERROR ' + e.message));
  await page.goto('file://' + game + '/Game.html');
  const W = (fn, t) => page.waitForFunction(fn, null, { timeout: t || 8000 });
  const shot = async (n) => { if (shots) await page.screenshot({ path: `${shots}-${n}.png` }); };
  const top = () => page.evaluate(() => { const s = MR.scene(); return s && (s instanceof MR.SceneTitle ? 'title' : s instanceof MR.SceneMap ? 'map' : s instanceof MR.SceneBattle ? 'battle' : s instanceof MR.SceneMenu ? 'menu' : 'other'); });

  await W(() => MR.scene() instanceof MR.SceneTitle);
  check('título aparece', true);
  await page.keyboard.press('Enter');
  await W(() => MR.scene() instanceof MR.SceneMap && !MR.sceneMap.loading);
  check('novo jogo carrega o mapa 1', await page.evaluate(() => MR.G.mapId === 1 && MR.sceneMap.events.length === 5));
  await page.waitForTimeout(600);
  await shot('map');

  // colisão: andar contra a árvore da borda esquerda
  await page.evaluate(() => { MR.sceneMap.player.setPos(2, 3); MR.sceneMap.player.dir = 4; });
  await page.keyboard.down('ArrowLeft'); await page.waitForTimeout(700); await page.keyboard.up('ArrowLeft');
  check('árvore bloqueia o jogador (x>=2? sim x=1 é árvore)', await page.evaluate(() => MR.sceneMap.player.x === 1 || MR.sceneMap.player.x === 2), await page.evaluate(() => MR.sceneMap.player.x));
  const px = await page.evaluate(() => MR.sceneMap.player.x);
  check('jogador não atravessa a árvore em x=0', px >= 1);

  // diálogo + escolha + inventário
  await page.evaluate(() => { const p = MR.sceneMap.player; p.setPos(5, 4); p.dir = 6; });
  await page.waitForTimeout(100);
  await page.keyboard.press('Enter');
  await W(() => MR.sceneMap.msg.state !== 'idle');
  await page.waitForTimeout(1200);
  await shot('dialog');
  const lines = await page.evaluate(() => MR.sceneMap.msg.lay && MR.sceneMap.msg.lay.items.filter((i) => i.k === 'c').map((i) => i.ch).join(''));
  check('texto com \\N[1] e \\V[1] expandido', lines && lines.indexOf('Heroi') >= 0 && lines.indexOf('0 até agora') >= 0, lines);
  for (let i = 0; i < 40; i++) {
    const st = await page.evaluate(() => MR.sceneMap.msg.state);
    if (st === 'choices') break;
    await page.keyboard.press('Enter'); await page.waitForTimeout(120);
  }
  await shot('choices');
  check('escolhas aparecem', await page.evaluate(() => MR.sceneMap.msg.state === 'choices'));
  await page.keyboard.press('Enter');
  for (let i = 0; i < 60; i++) {
    const done = await page.evaluate(() => MR.G.sw(1) && !MR.sceneMap.msg.busy() && !(MR.sceneMap.interp && MR.sceneMap.interp.running()));
    if (done) break;
    await page.keyboard.press('Enter'); await page.waitForTimeout(120);
  }
  const inv = await page.evaluate(() => ({ potion: MR.G.items[1], sw1: MR.G.sw(1), sw2: MR.G.sw(2), v1: MR.G.v(1) }));
  check('escolher "Sim" dá poção + liga interruptores + incrementa variável', inv.potion === 1 && inv.sw1 && inv.sw2 && inv.v1 === 1, inv);
  check('página condicional do evento 5 ativa após o interruptor', await page.evaluate(() => MR.sceneMap.events.find((e) => e.id === 5).pageIndex === 0));

  // menu
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  check('Esc abre o menu', (await top()) === 'menu');
  await shot('menu');
  await page.keyboard.press('Escape'); await page.waitForTimeout(300);

  // teletransporte (evento 201 com toque do jogador)
  await page.evaluate(() => { const p = MR.sceneMap.player; p.setPos(7, 7); p.dir = 2; });
  await page.keyboard.down('ArrowDown'); await page.waitForTimeout(350); await page.keyboard.up('ArrowDown');
  await W(() => MR.G.mapId === 2 && MR.sceneMap && !MR.sceneMap.loading);
  await page.waitForTimeout(800);
  const pos2 = await page.evaluate(() => ({ x: MR.sceneMap.player.x, y: MR.sceneMap.player.y, m: MR.G.mapId }));
  check('porta teletransporta para o mapa 2 (3,3)', pos2.m === 2 && pos2.x === 3 && pos2.y === 3, pos2);
  await shot('map2');
  await page.evaluate(() => { const p = MR.sceneMap.player; p.setPos(3, 3); p.dir = 2; });
  await page.keyboard.down('ArrowDown'); await page.waitForTimeout(350); await page.keyboard.up('ArrowDown');
  await W(() => MR.G.mapId === 1 && !MR.sceneMap.loading);
  check('saída volta ao mapa 1', true);
  await page.waitForTimeout(600);

  // batalha
  await page.evaluate(() => { const p = MR.sceneMap.player; p.setPos(4, 5); p.dir = 2; });
  await page.waitForTimeout(100);
  await page.keyboard.press('Enter');
  await W(() => MR.scene() instanceof MR.SceneBattle, 5000);
  check('evento inicia batalha', true);
  await page.waitForTimeout(1200);
  await shot('battle');
  const t0 = Date.now();
  while ((await top()) === 'battle' && Date.now() - t0 < 40000) { await page.keyboard.press('Enter'); await page.waitForTimeout(110); }
  check('batalha termina e volta ao mapa', (await top()) === 'map');
  for (let i = 0; i < 30; i++) {   // “Venceu!” da ramificação 601
    const busy = await page.evaluate(() => MR.sceneMap.msg.busy() || (MR.sceneMap.interp && MR.sceneMap.interp.running()));
    if (!busy) break;
    await page.keyboard.press('Enter'); await page.waitForTimeout(120);
  }
  const after = await page.evaluate(() => ({ gold: MR.G.gold, exp: MR.G.actor(1).exp, potions: MR.G.items[1] }));
  check('recompensas: ouro, EXP e drop', after.gold === 8 && after.exp >= 12 && after.potions === 2, after);

  // salvar / carregar
  await page.evaluate(() => MR.save.write(1));
  check('save grava no localStorage', await page.evaluate(() => !!MR.save.read(1)));

  const warns = await page.evaluate(() => MR.warnings || []);
  check('sem erros de runtime', errors.length === 0, errors);
  check('sem avisos de comandos não suportados', !warns.some((w) => /não suportado/.test(w)), warns);
  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} verificações OK`);
  process.exit(failed.length ? 1 : 0);
})().catch((e) => { console.error('E2E falhou:', e); process.exit(2); });
