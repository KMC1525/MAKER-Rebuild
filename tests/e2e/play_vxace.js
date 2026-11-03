// E2E: jogo convertido de VX Ace (tile 32px, 544x416). uso: node play_vxace.js <pasta-do-jogo> [prefixo-screenshots]
const { chromium } = require('playwright');
const game = process.argv[2], shots = process.argv[3] || '';
const results = [];
const check = (name, ok, extra) => { results.push(ok); console.log((ok ? 'PASS ' : 'FAIL ') + name + (extra !== undefined ? ' ' + JSON.stringify(extra) : '')); };
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 700, height: 560 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('PAGEERROR ' + e.message));
  await page.goto('file://' + game + '/Game.html');
  const W = (fn) => page.waitForFunction(fn, null, { timeout: 8000 });
  await W(() => MR.scene() instanceof MR.SceneTitle);
  check('config VX Ace', await page.evaluate(() => MR.config.engine === 'vxace' && MR.config.tileSize === 32 && MR.config.screen.w === 544));
  await page.keyboard.press('Enter');
  await W(() => MR.scene() instanceof MR.SceneMap && !MR.sceneMap.loading);
  await page.waitForTimeout(500);
  if (shots) await page.screenshot({ path: shots + '-map.png' });
  await page.evaluate(() => { const p = MR.sceneMap.player; p.setPos(5, 4); p.dir = 8; });
  await page.keyboard.press('Enter');
  await W(() => MR.sceneMap.msg.state !== 'idle');
  for (let i = 0; i < 30 && (await page.evaluate(() => MR.sceneMap.msg.state)) !== 'choices'; i++) { await page.keyboard.press('Enter'); await page.waitForTimeout(100); }
  check('escolhas (convertidas de VXA) aparecem', await page.evaluate(() => MR.sceneMap.msg.state === 'choices'));
  if (shots) await page.screenshot({ path: shots + '-choices.png' });
  await page.keyboard.press('Enter');                       // "Sim"
  for (let i = 0; i < 40; i++) {
    if (await page.evaluate(() => MR.G.sw(1) && !MR.sceneMap.msg.busy() && !(MR.sceneMap.interp && MR.sceneMap.interp.running()))) break;
    await page.waitForTimeout(100);
  }
  check('ramo "Sim" liga o interruptor 1', await page.evaluate(() => MR.G.sw(1)));
  const w = await page.evaluate(() => MR.warnings || []);
  check('script Ruby sem port é sinalizado (não executa nem quebra)', w.some((x) => /Ruby/.test(x)), w);
  check('sem erros de runtime', errors.length === 0, errors);
  await browser.close();
  process.exit(results.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
