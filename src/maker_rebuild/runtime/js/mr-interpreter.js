/*!
 * MAKER-Rebuild runtime — interpretador de eventos (códigos de comando do RPG Maker).
 * Para estender: MR.ext.commands[codigo] = function (params, cmd) { /* this = interpretador *\/ };
 */
(function () {
  'use strict';
  const MR = window.MR;
  const G = MR.G;

  /* ------------------------------------------------------------------ API de compatibilidade (scripts JS do MV/MZ) */
  const db = () => MR.data.db;
  MR.api = {
    $gameVariables: { value: (i) => G.v(i), setValue: (i, v) => G.setV(i, v) },
    $gameSwitches: { value: (i) => G.sw(i), setValue: (i, v) => G.setSw(i, v) },
    $gameSelfSwitches: {
      value: (k) => G.ss(k[0], k[1], k[2]), setValue: (k, v) => G.setSs(k[0], k[1], k[2], v),
    },
    $gameParty: {
      gold: () => G.gold, gainGold: (n) => G.gainGold(n), loseGold: (n) => G.gainGold(-n),
      members: () => G.members(), size: () => G.party.length,
      gainItem: (it, n) => { if (it) G.gain(it.__kind || kindOf(it), it.id, n); },
      hasItem: (it) => !!it && G.numItems(it.__kind || kindOf(it), it.id) > 0,
      numItems: (it) => (it ? G.numItems(it.__kind || kindOf(it), it.id) : 0),
      addActor: (id) => G.addMember(id), removeActor: (id) => { G.party = G.party.filter((x) => x !== id); G.dirty = true; },
    },
    $gameMessage: {
      _buf: [], add(t) { this._buf.push(t); }, isBusy: () => MR.sceneMap && MR.sceneMap.msg.busy(),
    },
    $gamePlayer: {
      reserveTransfer(mapId, x, y, d, fade) { if (MR.sceneMap) MR.sceneMap.transfer = { mapId, x, y, d: d || 2, fade: fade || 0 }; },
      get x() { return MR.sceneMap ? MR.sceneMap.player.x : 0; }, get y() { return MR.sceneMap ? MR.sceneMap.player.y : 0; },
      direction: () => (MR.sceneMap ? MR.sceneMap.player.dir : 2),
    },
    $gameMap: {
      mapId: () => G.mapId, event: (id) => (MR.sceneMap ? MR.sceneMap.eventById(id) : null),
      displayName: () => (MR.sceneMap ? MR.sceneMap.mapData.displayName : ''),
    },
    $gameTemp: {},
    AudioManager: {
      playSe: (s) => MR.audio.playSe(s), playBgm: (s) => MR.audio.playBgm(s), playBgs: (s) => MR.audio.playBgs(s),
      stopBgm: () => MR.audio.stopBgm(), fadeOutBgm: (s) => MR.audio.fadeOut('bgm', s),
    },
    SoundManager: { playOk: () => MR.audio.sys(1), playCancel: () => MR.audio.sys(3), playBuzzer: () => MR.audio.sys(3) },
  };
  function kindOf(it) {
    if (db().items.indexOf(it) >= 0) return 'item';
    if (db().weapons.indexOf(it) >= 0) return 'weapon';
    return 'armor';
  }
  Object.defineProperties(MR.api, {
    $dataItems: { get: () => db().items }, $dataWeapons: { get: () => db().weapons }, $dataArmors: { get: () => db().armors },
    $dataActors: { get: () => db().actors }, $dataSkills: { get: () => db().skills }, $dataSystem: { get: () => db().system },
  });
  MR.api.run = function (code, interp) {
    const names = Object.keys(MR.api).filter((k) => k !== 'run');
    try {
      const fn = new Function(...names, 'MR', code);
      return fn.apply(interp || {}, names.map((n) => MR.api[n]).concat([MR]));
    } catch (e) { MR.warn('script:' + code.slice(0, 40), 'erro em script de evento: ' + e.message); return undefined; }
  };

  /* ------------------------------------------------------------------ interpretador */
  MR.Interpreter = class {
    constructor(scene, depth) {
      this.scene = scene; this.depth = depth || 0;
      this.list = null; this.index = 0; this.eventId = 0; this.branch = {}; this.indent = 0;
      this.waitCount = 0; this.waitFn = null; this.child = null;
    }
    setup(list, eventId) {
      this.list = list; this.index = 0; this.eventId = eventId || 0; this.branch = {};
      this.waitCount = 0; this.waitFn = null; this.child = null;
    }
    running() { return !!this.list; }
    terminate() { this.list = null; this.child = null; this.waitFn = null; }
    update() {
      let guard = 0;
      while (this.list) {
        if (this.child) { this.child.update(); if (this.child.running()) return; this.child = null; }
        if (this.waitCount > 0) { this.waitCount--; return; }
        if (this.waitFn) { if (this.waitFn()) return; this.waitFn = null; }
        if (this.index >= this.list.length) { this.terminate(); return; }
        this.exec();
        if (++guard > 4000) { MR.warn('loop', 'evento com possível laço infinito sem espera (evento ' + this.eventId + ')'); return; }
      }
    }
    exec() {
      const cmd = this.list[this.index];
      if (!cmd) { this.terminate(); return; }
      this.indent = cmd.indent || 0;
      const h = H[cmd.code] || MR.ext.commands[cmd.code];
      if (cmd.lang === 'ruby' && cmd.code === 355) { MR.warn('ruby-script', 'script Ruby sem port para JS ignorado (rode `maker-rebuild port`)'); }
      else if (h) h.call(this, cmd.parameters || [], cmd);
      else if (!NOOP[cmd.code]) MR.warn('cmd' + cmd.code, 'comando de evento ' + cmd.code + ' não suportado (ignorado)');
      this.index++;
    }
    // helpers
    wait(n) { this.waitCount = n; }
    waitUntil(fn) { this.waitFn = fn; }
    character(id) {
      if (id < 0) return this.scene.player;
      return this.scene.eventById(id === 0 ? this.eventId : id);
    }
    skipBranch() { while (this.list[this.index + 1] && this.list[this.index + 1].indent > this.indent) this.index++; }
    nextText(code) {
      const out = [];
      while (this.list[this.index + 1] && this.list[this.index + 1].code === code) out.push(this.list[++this.index].parameters[0]);
      return out;
    }
    operate(v, op, n) { return op === 0 ? v + n : v - n; }
    operand(type, val) { return type === 0 ? val : G.v(val); }
    actorsFor(fixed, id) {
      if (fixed === 0) return fixed === 0 && id === 0 ? G.members() : [G.actor(id)].filter(Boolean);
      return [G.actor(G.v(id))].filter(Boolean);
    }
    endMsgWait() { this.waitFn = () => this.scene.msg.state !== 'idle' && this.scene.msg.state !== 'held'; }
    condition(p) {
      switch (p[0]) {
        case 0: return G.sw(p[1]) === (p[2] === 0);
        case 1: {
          const a = G.v(p[1]), b = p[2] === 0 ? p[3] : G.v(p[3]);
          return [a === b, a >= b, a <= b, a > b, a < b, a !== b][p[4]];
        }
        case 2: return this.eventId > 0 ? G.ss(G.mapId, this.eventId, p[1]) === (p[2] === 0) : false;
        case 3: return p[2] === 0 ? Math.floor(G.timer.frames / 60) >= p[1] : Math.floor(G.timer.frames / 60) <= p[1];
        case 4: {
          const a = G.actor(p[1]);
          if (!a) return false;
          switch (p[2]) {
            case 0: return G.party.indexOf(a.id) >= 0;
            case 1: return a.name === p[3];
            case 2: return a.classId === p[3];
            case 3: return a.skills.indexOf(p[3]) >= 0;
            case 4: return a.equips[0] === p[3];
            case 5: return a.equips.indexOf(p[3]) > 0;
            case 6: return a.states.indexOf(p[3]) >= 0;
            default: return false;
          }
        }
        case 6: { const c = this.character(p[1]); return !!c && c.dir === p[2]; }
        case 7: return p[2] === 0 ? G.gold >= p[1] : p[2] === 1 ? G.gold <= p[1] : G.gold < p[1];
        case 8: return G.numItems('item', p[1]) > 0;
        case 9: return G.numItems('weapon', p[1]) > 0 || G.members().some((m) => m.equips[0] === p[1] && p[2]);
        case 10: return G.numItems('armor', p[1]) > 0 || G.members().some((m) => m.equips.indexOf(p[1]) > 0 && p[2]);
        case 11: return MR.input.pressed(String(p[1]));
        case 12: return !!MR.api.run('return (' + p[1] + ');', this);
        default: MR.warn('cond' + p[0], 'condição de evento tipo ' + p[0] + ' não suportada'); return false;
      }
    }
    gameData(t, a, b) {
      const s = this.scene;
      switch (t) {
        case 0: return G.numItems('item', a);
        case 1: return G.numItems('weapon', a);
        case 2: return G.numItems('armor', a);
        case 3: {
          const ac = G.actor(a);
          if (!ac) return 0;
          return [ac.level, ac.exp, ac.hp, ac.mp, ...[0, 1, 2, 3, 4, 5, 6, 7].map((i) => MR.rules.param(ac, i))][b] || 0;
        }
        case 5: {
          const c = this.character(a);
          if (!c) return 0;
          const tw = MR.config.tileSize;
          return [c.x, c.y, c.dir, Math.round(c.rx * tw - s.offX + tw / 2), Math.round(c.ry * tw - s.offY)][b] || 0;
        }
        case 6: return G.party[a] || 0;
        case 7: return [G.mapId, G.party.length, G.gold, G.steps, Math.floor(G.playtime / 60), Math.floor(G.timer.frames / 60), 0, G.battleCount || 0, 0, 0][a] || 0;
        default: return 0;
      }
    }
  };

  // comandos que podem ser ignorados sem aviso (marcadores de fim, comentários, efeitos puramente visuais)
  const NOOP = { 0: 1, 108: 1, 408: 1, 401: 1, 402: 0, 404: 1, 405: 1, 412: 1, 413: 0, 504: 1, 505: 1, 655: 1, 605: 1, 604: 1, 212: 1, 216: 1, 217: 1, 261: 1,
    138: 1, 137: 1, 139: 1, 140: 1, 202: 1, 206: 1, 236: 1, 233: 1, 234: 1, 251: 1, 283: 1, 285: 0, 132: 1, 133: 1, 134: 0, 322: 0 };

  /* ------------------------------------------------------------------ comandos */
  const H = {};

  // --- mensagens
  H[101] = function (p) {
    const lines = this.nextText(401);
    const nxt = this.list[this.index + 1];
    const hold = !!nxt && (nxt.code === 102 || nxt.code === 103 || nxt.code === 104);
    this.msgWait = true;
    const speaker = MR.config.engine === 'mz' ? p[4] : '';
    this.scene.msg.show(lines, { face: p[0], faceIndex: p[1], bg: p[2], pos: p[3], speaker, hold }, () => { this.msgWait = false; });
    this.waitFn = () => this.msgWait;
  };
  H[102] = function (p) {
    this.msgWait = true;
    const idx = this.indent;
    this.scene.msg.choices(p[0], { cancelType: p[1] == null ? -1 : (p[1] < p[0].length ? p[1] : -2), defaultType: p[2] || 0, pos: p[3] == null ? 2 : p[3] }, (i) => { this.branch[idx] = i; this.msgWait = false; });
    this.waitFn = () => this.msgWait;
  };
  H[402] = function (p) { if (this.branch[this.indent] !== p[0]) this.skipBranch(); };
  H[403] = function () { if (this.branch[this.indent] >= 0) this.skipBranch(); };
  H[103] = function (p) {
    this.msgWait = true;
    this.scene.msg.inputNumber(p[1] || 1, G.v(p[0]), (v) => { G.setV(p[0], v); this.scene.msg.reset(); this.msgWait = false; });
    this.waitFn = () => this.msgWait;
  };
  H[104] = function (p) {
    this.msgWait = true;
    this.scene.msg.selectItem(p[1] || 1, (id) => { G.setV(p[0], id); this.scene.msg.reset(); this.msgWait = false; });
    this.waitFn = () => this.msgWait;
  };
  H[105] = function (p) {
    const lines = this.nextText(405);
    this.msgWait = true;
    this.scene.msg.scrollText(lines, { speed: p[0] || 2, noFast: !!p[1] }, () => { this.msgWait = false; });
    this.waitFn = () => this.msgWait;
  };

  // --- fluxo
  H[111] = function (p) {
    const r = this.condition(p);
    this.branch[this.indent] = r;
    if (!r) this.skipBranch();
  };
  H[411] = function () { if (this.branch[this.indent] !== false) this.skipBranch(); };
  H[112] = function () {};
  H[113] = function () {
    while (this.index < this.list.length - 1) {
      this.index++;
      const c = this.list[this.index];
      if (c.code === 413 && c.indent < this.indent) break;
    }
  };
  H[413] = function () {
    while (this.index > 0) { this.index--; const c = this.list[this.index]; if (c.code === 112 && c.indent === this.indent) break; }
  };
  H[115] = function () { this.index = this.list.length; };
  H[116] = function () { const e = this.scene.eventById(this.eventId); if (e) { e.permErased = true; e.erased = true; e.ghost = true; } };
  H[117] = function (p) {
    const ce = (db().commonEvents || [])[p[0]];
    if (ce && this.depth < 8) { this.child = new MR.Interpreter(this.scene, this.depth + 1); this.child.setup(ce.list, this.eventId); }
  };
  H[118] = function () {};
  H[119] = function (p) {
    for (let i = 0; i < this.list.length; i++) {
      const c = this.list[i];
      if (c.code === 118 && c.parameters[0] === p[0]) { this.index = i; return; }
    }
  };

  // --- estado
  H[121] = function (p) { for (let i = p[0]; i <= p[1]; i++) G.setSw(i, p[2] === 0); };
  H[122] = function (p) {
    let v = 0;
    switch (p[3]) {
      case 0: v = p[4]; break;
      case 1: v = G.v(p[4]); break;
      case 2: v = MR.u.randRange(p[4], Math.max(p[4], p[5])); break;
      case 3: v = this.gameData(p[4], p[5], p[6]); break;
      case 4: v = Number(MR.api.run('return (' + p[4] + ');', this)) || 0; break;
      default: break;
    }
    for (let i = p[0]; i <= p[1]; i++) {
      const cur = G.v(i);
      const o = [v, cur + v, cur - v, cur * v, v === 0 ? cur : Math.floor(cur / v), v === 0 ? cur : cur % v][p[2]];
      G.setV(i, o);
    }
  };
  H[123] = function (p) { if (this.eventId > 0) G.setSs(G.mapId, this.eventId, p[0], p[1] === 0); };
  H[124] = function (p) { if (p[0] === 0) { G.timer.on = true; G.timer.frames = p[1] * 60; } else G.timer.on = false; };
  H[125] = function (p) { G.gainGold(this.operate(0, p[0], this.operand(p[1], p[2]))); };
  const itemCmd = (kind) => function (p) {
    const n = this.operate(0, p[1], this.operand(p[2], p[3]));
    G.gain(kind, p[0], n);
  };
  H[126] = itemCmd('item'); H[127] = itemCmd('weapon'); H[128] = itemCmd('armor');
  H[129] = function (p) {
    if (p[1] === 0) G.addMember(p[0]); else { G.party = G.party.filter((x) => x !== p[0]); G.dirty = true; }
  };
  H[132] = function () {}; H[133] = function () {};
  H[134] = function (p) { G.saveDisabled = p[0] !== 0; };
  H[135] = function (p) { G.menuDisabled = p[0] !== 0; };
  H[136] = function (p) { G.encounterDisabled = p[0] !== 0; };

  // --- movimento / mapa
  H[201] = function (p) {
    if (this.scene.msg.busy()) { this.index--; this.waitFn = () => this.scene.msg.busy(); return; }
    const direct = p[0] === 0;
    const mapId = direct ? p[1] : G.v(p[1]), x = direct ? p[2] : G.v(p[2]), y = direct ? p[3] : G.v(p[3]);
    const fade = p[5] == null ? 0 : p[5];
    this.scene.transfer = { mapId, x, y, d: p[4] || 0, fade };
    if (fade !== 2) { this.scene.fade.target = 1; this.scene.fade.speed = 1 / 24; }
    this.waitFn = () => !!this.scene.transfer || this.scene.loading;
  };
  H[203] = function (p) {
    const c = this.character(p[0]);
    if (!c) return;
    let x, y;
    if (p[1] === 0) { x = p[2]; y = p[3]; } else if (p[1] === 1) { x = G.v(p[2]); y = G.v(p[3]); }
    else { const o = this.character(p[2]); if (!o) return; x = o.x; y = o.y; }
    c.setPos(x, y);
    if (p[4]) c.setDir(p[4]);
  };
  H[204] = function (p) {
    const d = p[0], n = p[1], speed = p[2], tw = MR.config.tileSize;
    const frames = Math.max(1, Math.round(n * tw / (Math.pow(2, speed) / 256 * tw)));
    const dx = d === 4 ? -n : d === 6 ? n : 0, dy = d === 8 ? -n : d === 2 ? n : 0;
    this.scene.scrollTo = { dx: dx * tw / frames, dy: dy * tw / frames, t: frames };
    if (p[3]) this.wait(frames);
  };
  H[205] = function (p) {
    const c = this.character(p[0]);
    if (!c) return;
    c.forceRoute(p[1]);
    if (p[1] && p[1].wait) this.waitFn = () => !!c.route && !c.routeDone;
  };
  H[211] = function (p) { this.scene.player.transparent = p[0] === 0; };
  H[213] = function (p) {
    const c = this.character(p[0]);
    if (c) c.balloon = { id: p[1], t: 0 };
    if (p[2]) this.wait(60);
  };
  H[214] = H[116];
  H[221] = function () { this.scene.fade.target = 1; this.scene.fade.speed = 1 / 24; this.waitFn = () => this.scene.fade.a < 0.999; };
  H[222] = function () { this.scene.fade.target = 0; this.scene.fade.speed = 1 / 24; this.waitFn = () => this.scene.fade.a > 0.001; };
  H[223] = function (p) {
    const t = this.scene.tint;
    t.tgt = p[0].slice(); t.d = Math.max(1, p[1]);
    if (p[2]) this.wait(p[1]);
  };
  H[224] = function (p) { this.scene.flash = { c: p[0], t: p[1], d: Math.max(1, p[1]) }; if (p[2]) this.wait(p[1]); };
  H[225] = function (p) { this.scene.shake = { p: p[0], s: p[1], d: p[2] }; this.scene.shakeT = 0; if (p[3]) this.wait(p[2]); };
  H[230] = function (p) { this.wait(p[0]); };
  H[231] = function (p) {
    const d = p[3] === 0;
    this.scene.pictures[p[0]] = { name: p[1], origin: p[2] === 1, x: d ? p[4] : G.v(p[4]), y: d ? p[5] : G.v(p[5]), sx: p[6], sy: p[7], op: p[8] };
  };
  H[232] = function (p) {
    const pic = this.scene.pictures[p[0]];
    if (!pic) return;
    const d = p[3] === 0;
    pic.move = { x: d ? p[4] : G.v(p[4]), y: d ? p[5] : G.v(p[5]), sx: p[6], sy: p[7], op: p[8], t: Math.max(1, p[10] || 1) };
    if (p[11]) this.wait(p[10]);
  };
  H[235] = function (p) { delete this.scene.pictures[p[0]]; };

  // --- áudio
  H[241] = function (p) { MR.audio.playBgm(p[0]); };
  H[242] = function (p) { MR.audio.fadeOut('bgm', p[0]); };
  H[243] = function () { MR.audio.saveBgm(); };
  H[244] = function () { MR.audio.replayBgm(); };
  H[245] = function (p) { MR.audio.playBgs(p[0]); };
  H[246] = function (p) { MR.audio.fadeOut('bgs', p[0]); };
  H[249] = function (p) { MR.audio.playMe(p[0]); };
  H[250] = function (p) { MR.audio.playSe(p[0]); };

  // --- mapa
  H[281] = function (p) { this.scene.mapData.disableDisplayName = p[0] !== 0; };
  H[282] = function (p) {
    const ts = (db().tilesets || [])[p[0]];
    if (ts) { this.scene.tilemap = new MR.Tilemap(this.scene.mapData, ts); this.waitFn = () => this.scene.tilemap.pending().some((i) => !i.mrReady && !i.mrFail); }
  };
  H[284] = function (p) {
    const m = this.scene.mapData;
    m.parallaxName = p[0]; m.parallaxLoopX = p[1]; m.parallaxLoopY = p[2];
  };
  H[285] = function (p) {
    const d = p[2] === 0, x = d ? p[3] : G.v(p[3]), y = d ? p[4] : G.v(p[4]), s = this.scene;
    let r = 0;
    if (p[1] === 1 || p[1] === 0) r = s.tid(x, y, 0);
    else if (p[1] === 5) r = s.regionId(x, y);
    G.setV(p[0], r);
  };

  // --- batalha / lojas / sistema
  H[301] = function (p) {
    const troopId = p[0] === 0 ? p[1] : p[0] === 1 ? G.v(p[1]) : this.scene.randomTroopId ? this.scene.randomTroopId() : p[1];
    this.msgWait = true;
    const idx = this.indent;
    MR.startBattle(troopId, !!p[2], !!p[3], (result) => { this.branch[idx] = result; this.msgWait = false; });
    this.waitFn = () => this.msgWait;
  };
  H[601] = function () { if (this.branch[this.indent] !== 0) this.skipBranch(); };
  H[602] = function () { if (this.branch[this.indent] !== 1) this.skipBranch(); };
  H[603] = function () { if (this.branch[this.indent] !== 2) this.skipBranch(); };
  H[302] = function (p) {
    const goods = [[p[0], p[1], p[2], p[3]]];
    while (this.list[this.index + 1] && this.list[this.index + 1].code === 605) goods.push(this.list[++this.index].parameters);
    this.msgWait = true;
    MR.pushScene(new MR.SceneShop(goods, !!p[4], () => { this.msgWait = false; }));
    this.waitFn = () => this.msgWait;
  };
  H[303] = function (p) {
    const a = G.actor(p[0]);
    if (!a) return;
    const v = window.prompt(MR.t('namePrompt'), a.name);
    if (v) a.name = v.slice(0, p[1] || 8);
  };
  const actorOps = (fn) => function (p) { this.actorsFor(p[0], p[1]).forEach((a) => fn.call(this, a, p)); };
  H[311] = actorOps(function (a, p) {
    const v = this.operate(0, p[2], this.operand(p[3], p[4])), mhp = MR.rules.param(a, 0);
    a.hp = MR.u.clamp(a.hp + v, p[5] ? 0 : 1, mhp);
  });
  H[312] = actorOps(function (a, p) { a.mp = MR.u.clamp(a.mp + this.operate(0, p[2], this.operand(p[3], p[4])), 0, MR.rules.param(a, 1)); });
  H[313] = actorOps(function (a, p) {
    const i = a.states.indexOf(p[3]);
    if (p[2] === 0 && i < 0) a.states.push(p[3]); else if (p[2] === 1 && i >= 0) a.states.splice(i, 1);
  });
  H[314] = actorOps(function (a) { a.hp = MR.rules.param(a, 0); a.mp = MR.rules.param(a, 1); a.states = []; });
  H[315] = actorOps(function (a, p) {
    a.exp = Math.max(0, a.exp + this.operate(0, p[2], this.operand(p[3], p[4])));
    MR.rules.levelUp(a);
  });
  H[316] = actorOps(function (a, p) {
    a.level = MR.u.clamp(a.level + this.operate(0, p[2], this.operand(p[3], p[4])), 1, 99);
    a.exp = MR.rules.expForLevel(a, a.level);
  });
  H[318] = actorOps(function (a, p) {
    const i = a.skills.indexOf(p[3]);
    if (p[2] === 0 && i < 0) a.skills.push(p[3]); else if (p[2] === 1 && i >= 0) a.skills.splice(i, 1);
  });
  H[319] = function (p) { const a = G.actor(p[0]); if (a) a.equips[p[1] - 1] = p[2]; };
  H[320] = function (p) { const a = G.actor(p[0]); if (a) a.name = p[1]; };
  H[321] = function (p) { const a = G.actor(p[0]); if (a) a.classId = p[1]; };
  H[322] = function (p) { const a = G.actor(p[0]); if (a) { a.characterName = p[1]; a.characterIndex = p[2]; a.faceName = p[3]; a.faceIndex = p[4]; } };
  H[324] = function (p) { const a = G.actor(p[0]); if (a) a.nickname = p[1]; };
  H[325] = function (p) { const a = G.actor(p[0]); if (a) a.profile = p[1]; };
  H[351] = function () { MR.pushScene(new MR.SceneMenu()); };
  H[352] = function () { this.msgWait = true; MR.pushScene(new MR.SceneSave(true, () => { this.msgWait = false; })); this.waitFn = () => this.msgWait; };
  H[353] = function () { MR.gotoScene(new MR.SceneGameOver()); this.terminate(); };
  H[354] = function () { MR.gotoScene(new MR.SceneTitle()); this.terminate(); };

  // --- scripts / plugins
  H[355] = function (p) {
    const code = [p[0]].concat(this.nextText(655)).join('\n');
    MR.api.$gameMessage._buf = [];
    MR.api.run(code, { _eventId: this.eventId, character: (i) => this.character(i), eventId: () => this.eventId });
    const buf = MR.api.$gameMessage._buf;
    if (buf.length) { this.msgWait = true; this.scene.msg.show(buf, { pos: 2 }, () => { this.msgWait = false; }); this.waitFn = () => this.msgWait; }
  };
  H[356] = function (p) {
    const parts = String(p[0]).trim().split(/\s+/), name = parts.shift();
    const fn = MR.ext.pluginCommands[name] || MR.ext.pluginCommands[String(name).toLowerCase()];
    if (fn) fn.call(this, parts, name); else MR.warn('plug:' + name, 'comando de plugin sem port: ' + name);
  };
  H[357] = function (p) {
    const key = p[0] + '.' + p[1];
    const fn = MR.ext.pluginCommands[key] || MR.ext.pluginCommands[p[1]];
    if (fn) fn.call(this, p[3] || {}, key); else MR.warn('plug:' + key, 'comando de plugin MZ sem port: ' + key);
  };

  MR.Interpreter.supported = Object.keys(H).map(Number).sort((a, b) => a - b);
})();
