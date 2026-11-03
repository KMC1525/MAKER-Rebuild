/*!
 * MAKER-Rebuild runtime — batalha por turnos (fórmulas de dano do banco de dados do jogo).
 */
(function () {
  'use strict';
  const MR = window.MR;
  const IN = MR.input;
  const G = MR.G;
  const PARAMS = ['mhp', 'mmp', 'atk', 'def', 'mat', 'mdf', 'agi', 'luk'];

  /* ---- Battler: casca uniforme para atores e inimigos (usada nas fórmulas a.atk / b.def) */
  class Battler {
    constructor(src, isActor) {
      this.src = src; this.isActor = isActor; this.guarding = false; this.states = isActor ? src.states : [];
      if (isActor) {
        this.name = src.name; this.level = src.level;
      } else {
        const d = (MR.data.db.enemies || [])[src.enemyId] || { name: '???', params: [10, 0, 5, 5, 5, 5, 5, 5], actions: [], dropItems: [] };
        this.d = d; this.name = d.name; this.level = d.level || 1; this._hp = d.params[0]; this._mp = d.params[1];
        this.x = src.x; this.y = src.y; this.hidden = !!src.hidden; this.flash = 0; this.fadeOut = 0;
      }
      PARAMS.forEach((p, i) => Object.defineProperty(this, p, { get: () => (this.isActor ? MR.rules.param(this.src, i) : this.d.params[i]) }));
    }
    get hp() { return this.isActor ? this.src.hp : this._hp; }
    set hp(v) { v = MR.u.clamp(Math.round(v), 0, this.mhp); if (this.isActor) this.src.hp = v; else this._hp = v; }
    get mp() { return this.isActor ? this.src.mp : this._mp; }
    set mp(v) { v = MR.u.clamp(Math.round(v), 0, this.mmp); if (this.isActor) this.src.mp = v; else this._mp = v; }
    get tp() { return 0; }
    alive() { return this.hp > 0; }
    agiRoll() { return this.agi + MR.u.rand(Math.max(1, Math.floor(5 + this.agi / 4))); }
  }

  const VARS = new Proxy({}, { get: (_, k) => G.v(+k) });
  function evalFormula(f, a, b) {
    try {
      const val = new Function('a', 'b', 'v', 'return (' + f + ');')(a, b, VARS);
      return isFinite(val) ? val : 0;
    } catch (e) { MR.warn('formula:' + f, 'fórmula de dano inválida "' + f + '": ' + e.message); return 0; }
  }

  MR.startBattle = function (troopId, canEscape, canLose, cb) {
    G.battleCount = (G.battleCount || 0) + 1;
    MR.pushScene(new MR.SceneBattle(troopId, canEscape, canLose, cb));
  };

  MR.SceneBattle = class {
    constructor(troopId, canEscape, canLose, cb) {
      this.cb = cb; this.canEscape = canEscape; this.canLose = canLose;
      const troop = (MR.data.db.troops || [])[troopId] || { name: '', members: [] };
      this.enemies = (troop.members || []).map((m) => new Battler(m, false));
      this.party = G.members().map((a) => new Battler(a, true));
      this.log = []; this.logT = 0; this.phase = 'start'; this.turn = 0; this.popups = []; this.t = 0;
      this.queue = []; this.actions = []; this.escapeRatio = 0.5 * this.avgAgi(this.party) / Math.max(1, this.avgAgi(this.enemies));
      this.fade = 1; this.result = null; this.win = null; this.cmdWin = null; this.listWin = null; this.targetWin = null;
      const sys = MR.data.db.system || {};
      if (sys.battleBgm && sys.battleBgm.name) { MR.audio.saveBgm(); MR.audio.playBgm(sys.battleBgm); }
      const names = this.enemies.map((e) => e.name);
      this.say(names.length ? MR.t('appeared', names.join(', ')) : MR.t('battle'));
      this.imgs = this.enemies.map((e) => {
        const im = MR.assets.image('enemies', e.d && e.d.battlerName);
        return im.mrFail ? MR.assets.image('sv_enemies', e.d && e.d.battlerName) : im;
      });
      this.bb1 = MR.assets.image('battlebacks1', (MR.sceneMap && MR.sceneMap.mapData.battleback1Name) || ((sys.battleback1Name) || ''));
      this.bb2 = MR.assets.image('battlebacks2', (MR.sceneMap && MR.sceneMap.mapData.battleback2Name) || ((sys.battleback2Name) || ''));
    }
    avgAgi(l) { return l.length ? l.reduce((s, b) => s + b.agi, 0) / l.length : 1; }
    say(t) { this.log.push(t); }
    foes() { return this.enemies.filter((e) => e.alive() && !e.hidden); }
    allies() { return this.party.filter((p) => p.alive()); }

    update() {
      this.t++;
      this.popups = this.popups.filter((p) => (p.t += 1) < 50);
      if (this.fade > 0) this.fade = Math.max(0, this.fade - 0.04);
      if (this.log.length && this.phase !== 'input' && !this.cmdWin && !this.listWin && !this.targetWin) {
        this.logT++;
        if (IN.okTriggered() || this.logT > 70) { this.log.shift(); this.logT = 0; }
        return;
      }
      switch (this.phase) {
        case 'start': this.beginInput(); break;
        case 'input': this.updateInput(); break;
        case 'turn': this.runNextAction(); break;
        case 'end': this.finish(); break;
        default: break;
      }
    }

    /* ---------- entrada de comandos */
    beginInput() {
      this.turn++;
      this.actions = [];
      this.inputIdx = -1;
      this.phase = 'input';
      this.nextActor();
    }
    nextActor() {
      this.inputIdx++;
      while (this.inputIdx < this.party.length && !this.party[this.inputIdx].alive()) this.inputIdx++;
      if (this.inputIdx >= this.party.length) { this.startTurn(); return; }
      this.openCommands();
    }
    openCommands() {
      const b = this.party[this.inputIdx], sw = MR.config.screen.w, sh = MR.config.screen.h;
      const items = [{ text: MR.cmd('attack'), k: 'attack' }, { text: MR.cmd('skill'), k: 'skill', enabled: b.src.skills.length > 0 }, { text: MR.cmd('guard'), k: 'guard' },
        { text: MR.cmd('item'), k: 'item', enabled: Object.keys(G.items).length > 0 }, { text: MR.cmd('escape'), k: 'escape', enabled: this.canEscape }];
      const w = 170 * MR.ui.sc * 1.2;
      this.cmdWin = new MR.ListWin({
        x: 8, y: sh - (items.length * MR.ui.lh() + MR.ui.pad() * 2) - 4 - 120 * MR.ui.sc, w, rows: items.length, items,
        onOk: (i, it) => this.pickCommand(b, it.k),
        onCancel: () => { if (this.inputIdx > 0) { let j = this.inputIdx - 1; while (j >= 0 && !this.party[j].alive()) j--; if (j >= 0) { this.actions.pop(); this.inputIdx = j - 1; this.cmdWin = null; this.nextActor(); } } },
      });
    }
    pickCommand(b, k) {
      this.cmdWin = null;
      if (k === 'attack') return this.chooseTarget(b, { skillId: 1, scope: 1 });
      if (k === 'guard') { this.actions.push({ b, guard: true }); return this.nextActor(); }
      if (k === 'escape') { this.actions.push({ b, escape: true }); return this.nextActor(); }
      const sw = MR.config.screen.w, sh = MR.config.screen.h;
      const db = MR.data.db;
      let items;
      if (k === 'skill') items = b.src.skills.map((id) => db.skills[id]).filter(Boolean).map((s) => ({ text: s.name, d: s, enabled: b.mp >= (s.mpCost || 0), kind: 'skill', icon: s.iconIndex }));
      else items = Object.keys(G.items).map((id) => db.items[id]).filter((it) => it && it.consumable !== undefined || it).map((it) => ({ text: it.name, d: it, enabled: (it.itypeId || 1) === 1, kind: 'item', icon: it.iconIndex, n: G.items[it.id] }));
      this.listWin = new MR.ListWin({
        x: 0, y: sh - 150 * MR.ui.sc * 1.4 - 4, w: sw, rows: 3, cols: 2, items,
        drawItem: (ctx, it, r) => { MR.ui.icon(ctx, it.icon, r.x, r.y + 2); MR.ui.text(ctx, it.text, r.x + MR.ui.iconSize() + 6, r.y, r.w, 'left'); const cost = it.kind === 'skill' ? (it.d.mpCost ? it.d.mpCost + ' MP' : '') : '×' + it.n; if (cost) MR.ui.text(ctx, cost, r.x, r.y, r.w - 6, 'right'); },
        onOk: (i, it) => { this.listWin = null; this.chooseTarget(b, { skillId: it.kind === 'skill' ? it.d.id : 0, item: it.kind === 'item' ? it.d : null, scope: it.d.scope }); },
        onCancel: () => { this.listWin = null; this.openCommands(); },
      });
    }
    chooseTarget(b, act) {
      const sc = act.scope;
      const friendly = [7, 8, 9, 10, 11].indexOf(sc) >= 0;
      if (sc === 2 || sc === 8 || sc === 11 || sc === 4 || sc === 5 || sc === 6 || sc === 3 || sc === 10) { act.b = b; this.actions.push(act); return this.nextActor(); }
      const pool = friendly ? (sc === 9 ? this.party.filter((p) => !p.alive()) : this.party) : this.foes();
      if (!pool.length) { return this.openCommands(); }
      this.targetWin = new MR.ListWin({
        x: MR.config.screen.w / 2 - 120 * MR.ui.sc, y: 20 * MR.ui.sc, w: 240 * MR.ui.sc, rows: Math.min(5, pool.length),
        items: pool.map((t) => ({ text: t.name + (t.isActor ? '  ' + t.hp + '/' + t.mhp : ''), t })),
        onOk: (i, it) => { this.targetWin = null; act.b = b; act.target = it.t; this.actions.push(act); this.nextActor(); },
        onCancel: () => { this.targetWin = null; this.openCommands(); },
        onMove: (i, it) => { this.cursorTarget = it.t; },
      });
      this.cursorTarget = pool[0];
    }
    updateInput() {
      if (this.targetWin) this.targetWin.update();
      else if (this.listWin) this.listWin.update();
      else if (this.cmdWin) this.cmdWin.update();
    }

    /* ---------- execução do turno */
    startTurn() {
      this.cmdWin = this.listWin = this.targetWin = null;
      // inimigos escolhem ações
      this.enemies.forEach((e) => { if (e.alive() && !e.hidden) { const a = this.enemyAction(e); if (a) this.actions.push(a); } });
      this.actions.sort((x, y) => (y.b.agiRoll() + (y.guard ? 1e3 : 0)) - (x.b.agiRoll() + (x.guard ? 1e3 : 0)));
      this.party.forEach((p) => { p.guarding = false; });
      this.phase = 'turn';
    }
    enemyAction(e) {
      const acts = (e.d.actions || []).filter((a) => this.condOk(e, a));
      if (!acts.length) return { b: e, skillId: 1, scope: 1, target: this.rndAlly() };
      const max = Math.max(...acts.map((a) => a.rating)), zero = max - 3;
      const pool = acts.filter((a) => a.rating > zero);
      if (!pool.length) return null;
      let sum = pool.reduce((s, a) => s + a.rating - zero, 0), r = MR.u.rand(Math.max(1, sum)), pick = pool[0];
      for (const a of pool) { r -= a.rating - zero; if (r < 0) { pick = a; break; } }
      const sk = (MR.data.db.skills || [])[pick.skillId] || { scope: 1 };
      return { b: e, skillId: pick.skillId, scope: sk.scope || 1, target: [7, 8, 9, 10, 11].indexOf(sk.scope) >= 0 ? e : this.rndAlly() };
    }
    condOk(e, a) {
      const p1 = a.conditionParam1, p2 = a.conditionParam2;
      switch (a.conditionType) {
        case 0: return true;
        case 1: return p2 === 0 ? this.turn === p1 : this.turn >= p1 && (this.turn - p1) % p2 === 0;
        case 2: return e.hp / e.mhp >= p1 && e.hp / e.mhp <= p2;
        case 3: return e.mmp > 0 && e.mp / e.mmp >= p1 && e.mp / e.mmp <= p2;
        case 6: return G.sw(p1);
        default: return true;
      }
    }
    rndAlly() { const a = this.allies(); return a[MR.u.rand(a.length)]; }
    runNextAction() {
      if (this.checkEnd()) return;
      const act = this.actions.shift();
      if (!act) { this.phase = 'start'; return; }
      const b = act.b;
      if (!b.alive()) return;
      if (act.guard) { b.guarding = true; this.say(MR.t('defends', b.name)); return; }
      if (act.escape) {
        if (Math.random() < this.escapeRatio) { this.say(MR.t('fled')); this.result = 1; this.phase = 'end'; this.actions = []; }
        else { this.say(MR.t('fleeFail')); this.escapeRatio += 0.1; }
        return;
      }
      const db = MR.data.db;
      const skill = act.item || db.skills[act.skillId] || { name: 'Ataque', scope: 1, damage: { type: 1, formula: 'a.atk * 4 - b.def * 2', variance: 20 } };
      let targets = this.resolveTargets(act, skill);
      if (!targets.length) return;
      if (b.isActor && act.item) { G.gain('item', act.item.id, -1); }
      else if (skill.mpCost) b.mp -= skill.mpCost;
      this.say(act.item ? MR.t('usedItem', b.name, act.item.name) : (act.skillId === 1 ? MR.t('attacks', b.name) : MR.t('usesSkill', b.name, skill.name)));
      targets.forEach((t) => this.applyEffect(b, t, skill));
    }
    resolveTargets(act, skill) {
      const sc = skill.scope == null ? act.scope : skill.scope;
      const foesOf = (b) => (b.isActor ? this.foes() : this.allies());
      const alliesOf = (b) => (b.isActor ? this.party : this.enemies.filter((e) => !e.hidden));
      let t;
      if (sc === 2) t = foesOf(act.b);
      else if (sc === 8) t = alliesOf(act.b).filter((x) => x.alive());
      else if (sc === 11) t = [act.b];
      else if (sc >= 3 && sc <= 6) { const f = foesOf(act.b); t = Array.from({ length: sc - 2 }, () => f[MR.u.rand(f.length)]).filter(Boolean); }
      else if (sc === 10) t = alliesOf(act.b).filter((x) => !x.alive());
      else { t = act.target ? [act.target] : []; if (t[0] && !t[0].alive() && sc === 1) { const f = foesOf(act.b); t = f.length ? [f[MR.u.rand(f.length)]] : []; } }
      return t;
    }
    applyEffect(user, t, skill) {
      const d = skill.damage || { type: 0 };
      const sr = skill.successRate == null ? 100 : skill.successRate;
      if (MR.u.rand(100) >= sr) { this.say(MR.t('miss')); return; }
      if (d.type > 0 && d.formula) {
        let v = evalFormula(d.formula, user, t);
        if (d.type <= 2 || d.type >= 5) v = Math.max(0, v);
        v *= 1 + (MR.u.rand((d.variance || 0) * 2 + 1) - (d.variance || 0)) / 100;
        if (t.guarding && d.type <= 2) v /= 2;
        v = Math.round(v);
        const isHp = d.type === 1 || d.type === 3 || d.type === 5;
        const heal = d.type === 3 || d.type === 4;
        if (isHp) t.hp += heal ? v : -v; else t.mp += heal ? v : -v;
        this.pop(t, (heal ? '+' : '') + v, heal ? '#7f7' : '#fff');
        if (!heal) t.flash = 10;
        if (d.type === 5) user.hp += v; if (d.type === 6) user.mp += v;
        this.say(MR.t(heal ? 'recovers' : 'takes', t.name, v, isHp ? 'HP' : 'MP'));
        if (!t.alive()) { this.say(MR.t('defeated', t.name)); if (!t.isActor) t.fadeOut = 1; }
      }
      (skill.effects || []).forEach((e) => {
        if (e.code === 11) { const v = Math.round(t.mhp * e.value1 + e.value2); t.hp += v; this.pop(t, '+' + v, '#7f7'); }
        else if (e.code === 12) { const v = Math.round(t.mmp * e.value1 + e.value2); t.mp += v; this.pop(t, '+' + v, '#7cf'); }
        else if (e.code === 22 && e.dataId === 1 && !t.alive()) { t.hp = 1; }
      });
    }
    pop(t, text, color) { this.popups.push({ t: 0, text, color, x: t.isActor ? 0 : t.x, y: t.isActor ? 0 : t.y - 80, who: t }); }
    checkEnd() {
      if (!this.enemies.some((e) => e.alive() && !e.hidden)) { this.victory(); return true; }
      if (!this.party.some((p) => p.alive())) { this.defeat(); return true; }
      return false;
    }
    victory() {
      this.actions = [];
      this.say(MR.t('victory'));
      const exp = this.enemies.reduce((s, e) => s + (e.d.exp || 0), 0), gold = this.enemies.reduce((s, e) => s + (e.d.gold || 0), 0);
      this.say(MR.t('gains', exp, gold, MR.rules.currency()));
      G.gainGold(gold);
      this.party.forEach((p) => { if (p.alive()) { p.src.exp += exp; MR.rules.levelUp(p.src).forEach((m) => this.say(m)); } });
      this.enemies.forEach((e) => (e.d.dropItems || []).forEach((di) => {
        if (di.kind > 0 && MR.u.rand(di.denominator || 1) === 0) {
          const kind = ['', 'item', 'weapon', 'armor'][di.kind], it = G.db(kind)[di.dataId];
          if (it) { G.gain(kind, di.dataId, 1); this.say(MR.t('got', it.name)); }
        }
      }));
      this.result = 0; this.phase = 'end';
    }
    defeat() {
      this.actions = [];
      this.say(MR.t('wiped'));
      this.result = 2; this.phase = 'end';
      if (this.canLose) this.party.forEach((p) => { if (!p.alive()) p.hp = 1; });
    }
    finish() {
      if (this.endT == null) this.endT = 0;
      this.fade = Math.min(1, this.fade + 0.05);
      if (this.fade < 1) return;
      MR.popScene();
      MR.audio.replayBgm();
      if (this.result === 2 && !this.canLose) { MR.gotoScene(new MR.SceneGameOver()); return; }
      if (this.cb) this.cb(this.result);
    }

    /* ---------- desenho */
    draw(ctx) {
      const W = MR.config.screen.w, H = MR.config.screen.h;
      const g = ctx.createLinearGradient(0, 0, 0, H);
      g.addColorStop(0, '#26304f'); g.addColorStop(1, '#0c1020');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      [this.bb1, this.bb2].forEach((im) => { if (im && im.mrReady) ctx.drawImage(im, 0, 0, W, H); });
      this.enemies.forEach((e, i) => {
        if (e.hidden) return;
        const im = this.imgs[i];
        let a = 1;
        if (!e.alive()) a = Math.max(0, 1 - (e.fadeOut += 0.03));
        if (a <= 0) return;
        ctx.save(); ctx.globalAlpha = a * (e.flash > 0 && (e.flash-- % 2) ? 0.4 : 1);
        if (im && im.mrReady) ctx.drawImage(im, e.x - im.width / 2, e.y - im.height);
        else { ctx.fillStyle = '#a44'; ctx.fillRect(e.x - 30, e.y - 60, 60, 60); }
        ctx.restore();
        if (this.targetWin && this.cursorTarget === e) { ctx.fillStyle = 'rgba(255,255,255,0.9)'; ctx.fillText('▼', e.x - 6, e.y - (im && im.mrReady ? im.height : 60) - 6); }
      });
      // painel do grupo
      const n = Math.max(1, this.party.length), pw = Math.min(W / n, 220 * MR.ui.sc * 1.4), py = H - 118 * MR.ui.sc;
      MR.ui.window(ctx, 0, py - 8, W, H - py + 8, { opacity: 0.9 });
      this.party.forEach((p, i) => {
        const x = 12 + i * pw, active = this.phase === 'input' && i === this.inputIdx;
        if (active) { ctx.fillStyle = 'rgba(255,255,255,0.15)'; ctx.fillRect(x - 4, py - 4, pw - 4, H - py); }
        ctx.globalAlpha = p.alive() ? 1 : 0.5;
        MR.ui.text(ctx, p.name, x, py - 2, pw - 12, 'left', MR.ui.fs() * 0.85);
        MR.ui.text(ctx, 'HP ' + p.hp + '/' + p.mhp, x, py + MR.ui.lh() * 0.8, pw - 12, 'left', MR.ui.fs() * 0.7);
        MR.ui.gauge(ctx, x, py + MR.ui.lh() * 1.55, pw - 20, p.hp / p.mhp, '#e44', '#f96');
        MR.ui.text(ctx, 'MP ' + p.mp + '/' + p.mmp, x, py + MR.ui.lh() * 1.6, pw - 12, 'left', MR.ui.fs() * 0.7);
        MR.ui.gauge(ctx, x, py + MR.ui.lh() * 2.35, pw - 20, p.mmp ? p.mp / p.mmp : 0, '#48e', '#6cf');
        ctx.globalAlpha = 1;
      });
      this.popups.forEach((p) => {
        const px = p.who.isActor ? 12 + this.party.indexOf(p.who) * pw + 40 : p.x, py2 = p.who.isActor ? H - 150 * MR.ui.sc : p.y;
        ctx.save(); ctx.globalAlpha = 1 - p.t / 50; ctx.font = 'bold ' + (MR.ui.fs() * 1.3) + 'px ' + MR.ui.font;
        ctx.lineWidth = 5; ctx.strokeStyle = '#000'; ctx.strokeText(p.text, px, py2 - p.t * 0.8); ctx.fillStyle = p.color; ctx.fillText(p.text, px, py2 - p.t * 0.8); ctx.restore();
      });
      if (this.log.length) {
        const w = Math.min(W - 20, MR.ui.measure(ctx, this.log[0]) + 60);
        MR.ui.window(ctx, (W - w) / 2, 8, w, MR.ui.lh() + MR.ui.pad());
        MR.ui.text(ctx, this.log[0], (W - w) / 2 + 4, 8 + MR.ui.pad() / 2, w - 8, 'center');
      }
      if (this.cmdWin) this.cmdWin.draw(ctx);
      if (this.listWin) this.listWin.draw(ctx);
      if (this.targetWin) this.targetWin.draw(ctx);
      if (this.fade > 0) { ctx.fillStyle = 'rgba(0,0,0,' + this.fade + ')'; ctx.fillRect(0, 0, W, H); }
    }
  };
})();
