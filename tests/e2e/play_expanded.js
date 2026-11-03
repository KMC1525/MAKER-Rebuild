// E2E: jogo MV após `expand` com o provedor mock (NPC novo entrega "Poção Mock"). uso: node play_expanded.js <pasta>
const { chromium } = require('playwright');
const game = process.argv[2];
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto('file://' + game + '/Game.html');
  await page.waitForFunction(() => MR.scene() instanceof MR.SceneTitle, null, { timeout: 8000 });
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => MR.scene() instanceof MR.SceneMap && !MR.sceneMap.loading, null, { timeout: 8000 });
  await page.evaluate(() => { const p = MR.sceneMap.player; p.setPos(2, 3); p.dir = 8; });
  await page.waitForTimeout(100);
  await page.keyboard.press('Enter');
  for (let i = 0; i < 30; i++) {
    if (await page.evaluate(() => MR.G.numItems('item', 2) === 1 && !MR.sceneMap.msg.busy())) break;
    await page.keyboard.press('Enter'); await page.waitForTimeout(120);
  }
  const ok = await page.evaluate(() => MR.G.numItems('item', 2) === 1 && MR.data.db.items[2].name === 'Poção Mock');
  console.log(ok ? 'PASS NPC criado pela IA entrega o item criado pela IA' : 'FAIL item não recebido');
  console.log(errors.length ? 'FAIL erros: ' + errors.join('|') : 'PASS sem erros de runtime');
  await browser.close();
  process.exit(ok && !errors.length ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
