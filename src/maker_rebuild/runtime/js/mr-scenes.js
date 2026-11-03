/*!
 * MAKER-Rebuild runtime — cenas: título, menu, status, loja, save/load, game over.
 */
(function () {
  'use strict';
  const MR = window.MR;
  const IN = MR.input;
  const G = MR.G;

  /* ---------------------------------------------------------------- título */
  MR.SceneTitle = class {
    constructor() {
      const sys = MR.data.db.system || {};
      this.b1 = MR.assets.image('titles1', sys.title1Name); this.b2 = MR.assets.image('titles2', sys.title2Name);
      MR.audio.playBgm(sys.titleBgm);
      MR.audio.stopBgm && void 0;
      if (sys.titleBgm && sys.titleBgm.name) MR.audio.playBgm(sys.titleBgm); else MR.audio.stopBgm();
      const W = MR.config.screen.w, H = MR.config.screen.h;
      const items = [{ text: MR.t('newGame'), k: 'new' }, { text: MR.t('continue'), k: 'cont', enabled: MR.save.any() }];
      if ((MR.config.extraMenu || []).length) MR.config.extraMenu.forEach((m) => items.push({ text: m.label, k: m.id }));
      const w = 240 * MR.ui.sc * 1.2;
      this.menu = new MR.ListWin({
        x: Math.round((W - w) / 2), y: Math.round(H * 0.62), w, rows: items.length, items, cancel: false,
        onOk: (i, it) => {
          if (it.k === 'new') { G.newGame(); MR.gotoScene(new MR.SceneMap()); }
          else if (it.k === 'cont') MR.pushScene(new MR.SceneSave(false, null));
          else if (MR.ext.hooks.titleCommand) MR.ext.hooks.titleCommand.forEach((f) => f(it.k));
        },
      });
      this.menu.index = items[1].enabled === false ? 0 : 1;
      this.t = 0;
    }
    update() { this.t++; this.menu.update(); }
    draw(ctx) {
      const W = MR.config.screen.w, H = MR.config.screen.h;
      const g = ctx.createLinearGradient(0, 0, 0, H);
      g.addColorStop(0, '#101830'); g.addColorStop(1, '#2a1a40');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      [this.b1, this.b2].forEach((im) => { if (im.mrReady) ctx.drawImage(im, 0, 0, W, H); });
      const title = MR.config.title || (MR.data.db.system || {}).gameTitle || '';
      ctx.save();
      ctx.font = 'bold ' + Math.round(72 * MR.ui.sc) + 'px ' + MR.ui.font; ctx.textAlign = 'center';
      ctx.lineWidth = 8 * MR.ui.sc; ctx.strokeStyle = 'rgba(0,0,0,0.8)'; ctx.lineJoin = 'round';
      ctx.strokeText(title, W / 2, H * 0.3, W - 40); ctx.fillStyle = '#fff'; ctx.fillText(title, W / 2, H * 0.3, W - 40);
      ctx.restore();
      this.menu.draw(ctx);
      ctx.fillStyle = 'rgba(255,255,255,0.45)'; ctx.font = Math.round(12 * MR.ui.sc) + 'px ' + MR.ui.font;
      ctx.fillText(MR.t('credit'), 8, H - 8);
    }
  };

  /* ---------------------------------------------------------------- game over */
  MR.SceneGameOver = class {
    constructor() {
      const sys = MR.data.db.system || {};
      MR.audio.stopBgm(); MR.audio.playMe(sys.gameoverMe);
      this.img = MR.assets.image('titles2', sys.gameOverName || 'GameOver'); this.t = 0;
    }
    update() { this.t++; if (this.t > 30 && (IN.okTriggered() || IN.cancelTriggered())) MR.gotoScene(new MR.SceneTitle()); }
    draw(ctx) {
      const W = MR.config.screen.w, H = MR.config.screen.h;
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      ctx.globalAlpha = Math.min(1, this.t / 60);
      if (this.img.mrReady) ctx.drawImage(this.img, 0, 0, W, H);
      else { ctx.fillStyle = '#c33'; ctx.font = 'bold ' + Math.round(64 * MR.ui.sc) + 'px ' + MR.ui.font; ctx.textAlign = 'center'; ctx.fillText(MR.t('gameOver'), W / 2, H / 2); ctx.textAlign = 'left'; }
      ctx.globalAlpha = 1;
    }
  };

  /* ---------------------------------------------------------------- menu principal */
  MR.SceneMenu = class {
    constructor() {
      this.mode = 'main'; this.overlay = true;
      const W = MR.config.screen.w, H = MR.config.screen.h, w = 220 * MR.ui.sc * 1.2;
      // (menus de habilidades/equipamento ainda não implementados: aparecem só quando um módulo ext os registrar)
      const items = [{ text: MR.cmd('item'), k: 'item' }, { text: MR.cmd('status'), k: 'status' },
        { text: MR.cmd('save'), k: 'save', enabled: !G.saveDisabled }, { text: MR.cmd('quit'), k: 'end' }];
      (MR.config.extraMenu || []).forEach((m) => items.splice(items.length - 1, 0, { text: m.label, k: m.id }));
      this.main = new MR.ListWin({
        x: W - w, y: 0, w, rows: items.length, items,
        onOk: (i, it) => this.pick(it.k), onCancel: () => MR.popScene(),
      });
      this.sel = 0;
    }
    pick(k) {
      if (k === 'item') { this.mode = 'item'; this.openItems(); }
      else if (k === 'status' || k === 'equip' || k === 'skill') { this.mode = 'actor'; this.after = k; this.openActors(); }
      else if (k === 'save') { MR.pushScene(new MR.SceneSave(true, null)); }
      else if (k === 'end') { MR.gotoScene(new MR.SceneTitle()); }
      else if (MR.ext.hooks.menuCommand) MR.ext.hooks.menuCommand.forEach((f) => f(k));
    }
    openItems() {
      const db = MR.data.db, W = MR.config.screen.w, H = MR.config.screen.h;
      const items = [];
      [['item', db.items], ['weapon', db.weapons], ['armor', db.armors]].forEach(([kind, arr]) => {
        Object.keys(G.container(kind)).forEach((id) => { const it = arr[id]; if (it) items.push({ text: it.name, d: it, kind, n: G.container(kind)[id], icon: it.iconIndex, enabled: kind === 'item' && (it.itypeId || 1) === 1 && it.occasion !== 3 && it.occasion !== 2 }); });
      });
      this.list = new MR.ListWin({
        x: 0, y: 0, w: W - 220 * MR.ui.sc * 1.2, rows: 9, cols: 2, items: items.length ? items : [{ text: MR.t('empty'), enabled: false }],
        drawItem: (ctx, it, r) => { MR.ui.icon(ctx, it.icon, r.x, r.y + 2); MR.ui.text(ctx, it.text, r.x + MR.ui.iconSize() + 6, r.y, r.w, 'left'); if (it.n) MR.ui.text(ctx, '×' + it.n, r.x, r.y, r.w - 6, 'right'); },
        onOk: (i, it) => { if (it.kind === 'item') this.useItem(it.d); },
        onCancel: () => { this.list = null; this.mode = 'main'; },
      });
      this.info = '';
    }
    useItem(it) {
      const ms = G.members();
      if (!ms.length) return;
      this.selItem = it;
      this.mode = 'target';
      this.targetList = new MR.ListWin({
        x: 0, y: 0, w: MR.config.screen.w - 220 * MR.ui.sc * 1.2, rows: 4, items: ms.map((m) => ({ text: m.name, a: m })),
        drawItem: (ctx, o, r) => { MR.ui.text(ctx, o.text, r.x, r.y, r.w, 'left'); MR.ui.text(ctx, 'HP ' + o.a.hp + '/' + MR.rules.param(o.a, 0) + '   MP ' + o.a.mp + '/' + MR.rules.param(o.a, 1), r.x, r.y, r.w, 'right', MR.ui.fs() * 0.8); },
        onOk: (i, o) => {
          const a = o.a; let used = false;
          (it.effects || []).forEach((e) => {
            if (e.code === 11) { const v = Math.round(MR.rules.param(a, 0) * e.value1 + e.value2); if (a.hp < MR.rules.param(a, 0) && a.hp > 0) { a.hp = Math.min(MR.rules.param(a, 0), a.hp + v); used = true; } }
            if (e.code === 12) { const v = Math.round(MR.rules.param(a, 1) * e.value1 + e.value2); if (a.mp < MR.rules.param(a, 1)) { a.mp = Math.min(MR.rules.param(a, 1), a.mp + v); used = true; } }
            if (e.code === 22 && e.dataId === 1 && a.hp <= 0) { a.hp = 1; used = true; }
          });
          if (it.effects && it.effects.some((e) => e.code === 44)) { // chama evento comum
            const ce = MR.data.db.commonEvents[it.effects.find((e) => e.code === 44).dataId]; if (ce && MR.sceneMap) { MR.sceneMap.startCommon(ce.list, 0); used = true; MR.popScene(); }
          }
          if (used) { MR.audio.playSe((MR.data.db.system.sounds || [])[4] || null); if (it.consumable !== false) G.gain('item', it.id, -1); this.mode = 'item'; this.openItems(); }
          else MR.audio.sys(3);
        },
        onCancel: () => { this.mode = 'item'; this.targetList = null; },
      });
    }
    openActors() {
      const ms = G.members();
      this.actorList = new MR.ListWin({
        x: 0, y: 0, w: MR.config.screen.w - 220 * MR.ui.sc * 1.2, rows: 4, items: ms.map((m) => ({ text: m.name, a: m })),
        drawItem: (ctx, o, r) => { MR.ui.text(ctx, o.text + '  ' + MR.t('level') + ' ' + o.a.level, r.x, r.y, r.w, 'left'); },
        onOk: (i, o) => { this.mode = 'detail'; this.detail = o.a; },
        onCancel: () => { this.actorList = null; this.mode = 'main'; },
      });
    }
    update() {
      if (this.mode === 'main') this.main.update();
      else if (this.mode === 'item') this.list && this.list.update();
      else if (this.mode === 'target') this.targetList && this.targetList.update();
      else if (this.mode === 'actor') this.actorList && this.actorList.update();
      else if (this.mode === 'detail') { if (IN.cancelTriggered() || IN.okTriggered()) { MR.audio.sys(2); this.mode = 'actor'; } }
    }
    draw(ctx) {
      const W = MR.config.screen.w, H = MR.config.screen.h, mw = 220 * MR.ui.sc * 1.2, lw = W - mw;
      ctx.fillStyle = 'rgba(0,0,0,0.45)'; ctx.fillRect(0, 0, W, H);
      this.main.active = this.mode === 'main'; this.main.draw(ctx);
      MR.ui.window(ctx, 0, this.main.h, mw, 90 * MR.ui.sc * 1.2);
      MR.ui.text(ctx, MR.rules.currency() + ' ' + G.gold, 6, this.main.h + MR.ui.pad(), mw - 12, 'right');
      MR.ui.text(ctx, MR.t('time') + ' ' + Math.floor(G.playtime / 3600) + ':' + MR.u.pad(Math.floor(G.playtime / 60) % 60, 2), 6, this.main.h + MR.ui.pad() + MR.ui.lh(), mw - 12, 'right', MR.ui.fs() * 0.8);
      if (this.mode === 'main' || this.mode === 'actor' && !this.actorList) {
        MR.ui.window(ctx, 0, 0, lw, H * 0.8);
        G.members().forEach((m, i) => {
          const y = MR.ui.pad() + i * (MR.ui.lh() * 3.2), x = MR.ui.pad();
          const fw = MR.ui.face(ctx, m.faceName, m.faceIndex, x, y, MR.ui.lh() * 2.8) || 0;
          MR.ui.text(ctx, m.name + '  ' + MR.t('level') + ' ' + m.level, x + fw + 12, y, lw, 'left');
          MR.ui.text(ctx, 'HP ' + m.hp + '/' + MR.rules.param(m, 0), x + fw + 12, y + MR.ui.lh() * 0.9, 300 * MR.ui.sc, 'left', MR.ui.fs() * 0.85);
          MR.ui.gauge(ctx, x + fw + 12, y + MR.ui.lh() * 1.75, 200 * MR.ui.sc, m.hp / MR.rules.param(m, 0), '#e44', '#f96');
          MR.ui.text(ctx, 'MP ' + m.mp + '/' + MR.rules.param(m, 1), x + fw + 12, y + MR.ui.lh() * 1.8, 300 * MR.ui.sc, 'left', MR.ui.fs() * 0.85);
          MR.ui.gauge(ctx, x + fw + 12, y + MR.ui.lh() * 2.65, 200 * MR.ui.sc, m.mp / Math.max(1, MR.rules.param(m, 1)), '#48e', '#6cf');
        });
      }
      if (this.list && (this.mode === 'item' || this.mode === 'target')) this.list.draw(ctx);
      if (this.mode === 'target' && this.targetList) this.targetList.draw(ctx);
      if (this.actorList && (this.mode === 'actor')) this.actorList.draw(ctx);
      if (this.mode === 'detail') this.drawDetail(ctx, lw);
    }
    drawDetail(ctx, lw) {
      const a = this.detail, H = MR.config.screen.h;
      MR.ui.window(ctx, 0, 0, lw, H);
      const pad = MR.ui.pad(), lh = MR.ui.lh();
      const fw = MR.ui.face(ctx, a.faceName, a.faceIndex, pad, pad, lh * 4) || 0;
      MR.ui.text(ctx, a.name + (a.nickname ? '  ' + a.nickname : ''), pad + fw + 12, pad, lw, 'left');
      const cls = (MR.data.db.classes || [])[a.classId];
      MR.ui.text(ctx, (cls ? cls.name : '') + '  ' + MR.t('level') + ' ' + a.level, pad + fw + 12, pad + lh, lw, 'left');
      MR.ui.text(ctx, MR.t('exp') + ' ' + a.exp + ' / ' + MR.rules.expForLevel(a, a.level + 1), pad + fw + 12, pad + lh * 2, lw, 'left', MR.ui.fs() * 0.85);
      const names = ['mhp', 'mmp', 'atk', 'def', 'mat', 'mdf', 'agi', 'luk'].map((k) => MR.t(k));
      names.forEach((n, i) => {
        const col = i % 2, row = Math.floor(i / 2);
        const x = pad + col * (lw / 2), y = pad + lh * 4.4 + row * lh;
        MR.ui.text(ctx, MR.rules.term('params', i, n), x, y, lw / 2 - pad * 2, 'left', MR.ui.fs() * 0.9);
        MR.ui.text(ctx, String(MR.rules.param(a, i)), x, y, lw / 2 - pad * 2, 'right', MR.ui.fs() * 0.9);
      });
      MR.ui.text(ctx, a.profile || '', pad, pad + lh * 9.2, lw - pad * 2, 'left', MR.ui.fs() * 0.8);
    }
  };

  /* ---------------------------------------------------------------- loja */
  MR.SceneShop = class {
    constructor(goods, purchaseOnly, cb) {
      this.overlay = true; this.cb = cb; this.mode = 'cmd'; this.buyOnly = purchaseOnly;
      const db = MR.data.db, W = MR.config.screen.w, H = MR.config.screen.h;
      this.goods = goods.map((g) => {
        const kind = ['item', 'weapon', 'armor'][g[0]], it = G.db(kind)[g[1]];
        return it ? { text: it.name, d: it, kind, price: g[2] === 0 ? it.price : g[3], icon: it.iconIndex } : null;
      }).filter(Boolean);
      const items = [{ text: MR.t('buy'), k: 'buy' }, { text: MR.t('sell'), k: 'sell', enabled: !purchaseOnly }, { text: MR.t('exit'), k: 'exit' }];
      this.cmd = new MR.ListWin({ x: 0, y: 0, w: 300 * MR.ui.sc, rows: 3, items, onOk: (i, it) => this.pick(it.k), onCancel: () => this.exit() });
      void db; void H; void W;
    }
    pick(k) {
      if (k === 'exit') return this.exit();
      const W = MR.config.screen.w;
      this.mode = k;
      const src = k === 'buy' ? this.goods : this.sellList();
      this.list = new MR.ListWin({
        x: 0, y: this.cmd.h, w: W, rows: 8, items: src.length ? src : [{ text: MR.t('empty'), enabled: false }],
        drawItem: (ctx, it, r) => { MR.ui.icon(ctx, it.icon, r.x, r.y + 2); MR.ui.text(ctx, it.text, r.x + MR.ui.iconSize() + 6, r.y, r.w, 'left'); MR.ui.text(ctx, String(it.price) + (it.n ? '   ×' + it.n : ''), r.x, r.y, r.w - 8, 'right'); },
        onOk: (i, it) => this.trade(it), onCancel: () => { this.list = null; this.mode = 'cmd'; },
      });
    }
    sellList() {
      const out = [];
      [['item', MR.data.db.items], ['weapon', MR.data.db.weapons], ['armor', MR.data.db.armors]].forEach(([kind, arr]) => {
        Object.keys(G.container(kind)).forEach((id) => { const it = arr[id]; if (it && it.price > 0) out.push({ text: it.name, d: it, kind, price: Math.floor(it.price / 2), icon: it.iconIndex, n: G.container(kind)[id] }); });
      });
      return out;
    }
    trade(it) {
      if (!it.d) return;
      if (this.mode === 'buy') {
        if (G.gold < it.price || G.numItems(it.kind, it.d.id) >= 99) return MR.audio.sys(3);
        G.gold -= it.price; G.gain(it.kind, it.d.id, 1); MR.audio.sys(1);
      } else {
        G.gold += it.price; G.gain(it.kind, it.d.id, -1); MR.audio.sys(1); this.pick('sell');
      }
    }
    exit() { MR.popScene(); if (this.cb) this.cb(); }
    update() { if (this.list) this.list.update(); else this.cmd.update(); }
    draw(ctx) {
      const W = MR.config.screen.w, H = MR.config.screen.h;
      ctx.fillStyle = 'rgba(0,0,0,0.35)'; ctx.fillRect(0, 0, W, H);
      this.cmd.active = !this.list; this.cmd.draw(ctx);
      MR.ui.window(ctx, 300 * MR.ui.sc, 0, W - 300 * MR.ui.sc, this.cmd.h);
      MR.ui.text(ctx, MR.t('money') + ': ' + G.gold + ' ' + MR.rules.currency(), 300 * MR.ui.sc + 12, MR.ui.pad(), W - 300 * MR.ui.sc - 24, 'right');
      if (this.list) {
        this.list.draw(ctx);
        const it = this.list.items[this.list.index];
        if (it && it.d) { MR.ui.window(ctx, 0, H - MR.ui.lh() * 2 - MR.ui.pad() * 2, W, MR.ui.lh() * 2 + MR.ui.pad() * 2); MR.text.draw(ctx, MR.text.layout(ctx, it.d.description || '', W - 40, MR.ui.fs() * 0.9), MR.ui.pad(), H - MR.ui.lh() * 2 - MR.ui.pad(), MR.ui.lh(), null); }
      }
    }
  };

  /* ---------------------------------------------------------------- salvar / carregar */
  MR.SceneSave = class {
    constructor(saving, cb) {
      this.overlay = true; this.saving = saving; this.cb = cb;
      const W = MR.config.screen.w, H = MR.config.screen.h, items = [];
      for (let i = 1; i <= MR.save.max; i++) {
        const s = MR.save.read(i);
        items.push({ text: s ? MR.t('slot', i) + (s.title ? ' — ' + s.title : '') + '   ' + new Date(s.when).toLocaleString() : MR.t('slot', i) + ' — ' + MR.t('emptySlot'), slot: i, enabled: saving || !!s });
      }
      this.list = new MR.ListWin({
        x: 0, y: 0, w: W, rows: Math.min(8, MR.save.max), items,
        onOk: (i, it) => {
          if (this.saving) { MR.save.write(it.slot); this.done(); }
          else if (MR.save.load(it.slot)) MR.gotoScene(new MR.SceneMap());
        },
        onCancel: () => this.done(),
      });
    }
    done() { MR.popScene(); if (this.cb) this.cb(); }
    update() { this.list.update(); }
    draw(ctx) { ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(0, 0, MR.config.screen.w, MR.config.screen.h); this.list.draw(ctx); }
  };
})();
