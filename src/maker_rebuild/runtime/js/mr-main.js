/*!
 * MAKER-Rebuild runtime — inicialização, pilha de cenas e laço principal (60 Hz fixo).
 */
(function () {
  'use strict';
  const MR = window.MR;

  MR.stack = [];
  MR.pushScene = (s) => { MR.stack.push(s); };
  MR.popScene = () => { MR.stack.pop(); };
  MR.gotoScene = (s) => { MR.stack.length = 0; MR.stack.push(s); };
  MR.scene = () => MR.stack[MR.stack.length - 1];

  MR.fatal = function (msg) {
    console.error('[MAKER-Rebuild] ' + msg);
    MR.stopped = true;
    const el = document.getElementById('mr-error');
    if (el) { el.hidden = false; el.querySelector('pre').textContent = msg; }
  };

  function resize() {
    const c = document.getElementById('mr-canvas');
    const W = MR.config.screen.w, H = MR.config.screen.h;
    const k = Math.min(window.innerWidth / W, window.innerHeight / H);
    const s = MR.config.integerScale ? Math.max(1, Math.floor(k)) : k;
    c.style.width = Math.floor(W * s) + 'px';
    c.style.height = Math.floor(H * s) + 'px';
  }

  MR.boot = function () {
    const canvas = document.getElementById('mr-canvas');
    canvas.width = MR.config.screen.w; canvas.height = MR.config.screen.h;
    const ctx = MR.ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = !MR.config.pixelated;
    if (MR.config.pixelated) canvas.classList.add('pixelated');
    MR.ui.init(); MR.input.init(canvas);
    window.addEventListener('resize', resize); resize();
    window.addEventListener('error', (e) => { if (!MR.stopped) MR.fatal((e.error && e.error.stack) || e.message); });
    window.addEventListener('unhandledrejection', (e) => { if (!MR.stopped) MR.fatal(String(e.reason && e.reason.stack || e.reason)); });
    (MR.ext.hooks.boot || []).forEach((f) => f());

    const pre = ['Window', 'IconSet', 'Balloon'].map((n) => MR.assets.image('system', n, true));
    const sys = MR.data.db.system || {};
    pre.push(MR.assets.image('titles1', sys.title1Name, true), MR.assets.image('titles2', sys.title2Name, true));
    const font = document.fonts && MR.config.fonts && MR.config.fonts.length ? document.fonts.load('28px GameFont').catch(() => {}) : Promise.resolve();
    Promise.all([MR.assets.whenLoaded(pre, 8000), font]).then(() => {
      document.getElementById('mr-loading').hidden = true;
      MR.gotoScene(new MR.SceneTitle());
      if (/[?&]autostart/.test(location.search)) { MR.G.newGame(); MR.gotoScene(new MR.SceneMap()); }
    });

    let last = performance.now(), acc = 0;
    const STEP = 1000 / 60;
    function frame(now) {
      if (MR.stopped) return;
      acc += Math.min(100, now - last); last = now;
      let n = 0;
      while (acc >= STEP && n++ < 5) {
        acc -= STEP;
        MR.input.update();
        const s = MR.scene();
        try { if (s) s.update(); } catch (e) { MR.fatal((e && e.stack) || String(e)); return; }
        MR.input.endFrame();
      }
      try { render(); } catch (e) { MR.fatal((e && e.stack) || String(e)); return; }
      requestAnimationFrame(frame);
    }
    function render() {
      const s = MR.scene();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!s) return;
      if (s.overlay) { const below = MR.stack[MR.stack.length - 2]; if (below) below.draw(ctx); }
      s.draw(ctx);
      if (MR.debug) drawDebug(ctx);
    }
    function drawDebug(c) {
      const w = MR.warnings || [];
      c.fillStyle = 'rgba(0,0,0,0.75)'; c.fillRect(0, 0, 420, 14 * (Math.min(12, w.length) + 2));
      c.fillStyle = '#9f9'; c.font = '12px monospace';
      c.fillText('MAKER-Rebuild debug — ' + w.length + ' aviso(s)  [F9 fecha]', 6, 14);
      w.slice(-12).forEach((m, i) => { c.fillStyle = '#fd8'; c.fillText(String(m).slice(0, 62), 6, 28 + i * 14); });
    }
    window.addEventListener('keydown', (e) => { if (e.code === 'F9') MR.debug = !MR.debug; });
    requestAnimationFrame(frame);
  };
})();
