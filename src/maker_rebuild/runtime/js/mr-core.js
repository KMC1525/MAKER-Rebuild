/*!
 * MAKER-Rebuild runtime — núcleo
 * Canvas 2D puro, sem frameworks. Funciona via file:// (dados carregados por <script>).
 */
(function (global) {
  'use strict';

  const MR = global.MR = global.MR || {};
  MR.version = '0.3.0';
  MR.data = MR.data || {};
  MR.data.maps = MR.data.maps || {};
  MR.config = MR.config || {};
  // Pontos de extensão: módulos gerados por IA / plugins portados se registram aqui.
  MR.ext = { commands: {}, pluginCommands: {}, hooks: {}, modules: {} };

  const warned = {};
  MR.warn = function (key, ...args) {
    if (warned[key]) return;
    warned[key] = true;
    console.warn('[MAKER-Rebuild]', ...args);
    (MR.warnings = MR.warnings || []).push(String(args[0]));
  };

  /* ------------------------------------------------------------------ utilidades */
  MR.u = {
    clamp: (v, a, b) => Math.max(a, Math.min(b, v)),
    rand: (n) => Math.floor(Math.random() * n),
    randRange: (a, b) => a + Math.floor(Math.random() * (b - a + 1)),
    pad: (n, w) => String(n).padStart(w, '0'),
    clone: (o) => JSON.parse(JSON.stringify(o)),
    isCJK: (ch) => /[　-鿿＀-￯]/.test(ch),
  };

  /* ------------------------------------------------------------------ textos da interface do runtime */
  MR.t = function (key) {
    let s = ((MR.config.ui || {})[key]);
    if (s == null) s = key;
    for (let i = 1; i < arguments.length; i++) s = s.split('{' + (i - 1) + '}').join(arguments[i]);
    return s;
  };
  const CMD_IDX = { mv: { escape: 1, attack: 2, guard: 3, item: 4, skill: 5, equip: 6, status: 7, save: 9, quit: 10 },
    vxace: { escape: 1, attack: 2, guard: 3, item: 4, skill: 5, equip: 6, status: 7, save: 8, quit: 9 } };
  CMD_IDX.mz = CMD_IDX.mv; CMD_IDX.vx = CMD_IDX.vxace;
  // termo de comando do próprio jogo (ex.: "Attack") com fallback para o texto do runtime
  MR.cmd = function (name) {
    const idx = (CMD_IDX[MR.config.engine] || {})[name];
    const terms = ((MR.data.db.system || {}).terms || {}).commands || [];
    const v = idx != null ? terms[idx] : '';
    return v || MR.t(name);
  };

  /* ------------------------------------------------------------------ assets */
  MR.assets = {
    imgs: {},
    // procura "categoria/nome" no índice gerado pelo build (case-insensitive)
    url(cat, name) {
      const idx = (MR.config.assetIndex || {})[cat];
      if (!idx || !name) return null;
      const hit = idx[String(name).toLowerCase()];
      if (!hit) return null;
      const dir = MR.config.paths[cat];
      return dir + '/' + hit.n.split('/').map(encodeURIComponent).join('/') + hit.e;
    },
    image(cat, name, quiet) {
      const key = cat + '/' + name;
      let im = this.imgs[key];
      if (im) return im;
      im = new Image();
      im.mrReady = false;
      im.mrFail = false;
      const url = this.url(cat, name);
      if (!url) {
        im.mrFail = true;
        if (name && !quiet) MR.warn('img:' + key, 'asset de imagem ausente: ' + key);
      } else {
        im.onload = () => { im.mrReady = true; };
        im.onerror = () => { im.mrFail = true; MR.warn('imgerr:' + key, 'falha ao carregar ' + url); };
        im.src = url;
      }
      this.imgs[key] = im;
      return im;
    },
    // Promise que resolve quando todas as imagens carregaram (ou falharam)
    whenLoaded(list, timeout) {
      const t0 = performance.now();
      return new Promise((resolve) => {
        const tick = () => {
          const pending = list.some((im) => !im.mrReady && !im.mrFail);
          if (!pending || performance.now() - t0 > (timeout || 20000)) resolve();
          else setTimeout(tick, 16);
        };
        tick();
      });
    },
  };

  /* ------------------------------------------------------------------ áudio */
  MR.audio = {
    bgm: null, bgmData: null, bgs: null, bgsData: null, me: null, saved: null,
    master: { bgm: 90, bgs: 90, me: 90, se: 90 },
    pending: [],
    _vol(o, cat) { return MR.u.clamp(((o && o.volume != null ? o.volume : 90) / 100) * (this.master[cat] / 100), 0, 1); },
    _el(cat, o, loop) {
      const url = MR.assets.url(cat, o.name);
      if (!url) { MR.warn('aud:' + cat + o.name, 'áudio ausente: ' + cat + '/' + o.name); return null; }
      const a = new Audio(url);
      a.loop = loop;
      a.volume = this._vol(o, cat);
      a.playbackRate = MR.u.clamp((o.pitch || 100) / 100, 0.5, 2);
      return a;
    },
    _start(a) {
      const p = a.play();
      if (p && p.catch) p.catch(() => { this.pending.push(a); });
    },
    unlock() {
      const q = this.pending.splice(0);
      q.forEach((a) => { const p = a.play(); if (p && p.catch) p.catch(() => {}); });
    },
    playBgm(o) {
      if (!o || !o.name) return this.stopBgm();
      if (this.bgmData && this.bgmData.name === o.name && this.bgm && !this.bgm.paused) {
        this.bgm.volume = this._vol(o, 'bgm');
        this.bgmData = Object.assign({}, o);
        return;
      }
      this.stopBgm();
      const a = this._el('bgm', o, true);
      this.bgmData = Object.assign({}, o);
      if (!a) return;
      this.bgm = a;
      this._start(a);
    },
    stopBgm() { if (this.bgm) { this.bgm.pause(); this.bgm = null; } this.bgmData = null; },
    fadeOut(which, sec) {
      const a = which === 'bgm' ? this.bgm : this.bgs;
      if (!a) return;
      const step = a.volume / Math.max(1, sec * 20);
      const iv = setInterval(() => {
        a.volume = Math.max(0, a.volume - step);
        if (a.volume <= 0.001) { clearInterval(iv); a.pause(); }
      }, 50);
      if (which === 'bgm') { this.bgm = null; this.bgmData = null; } else { this.bgs = null; this.bgsData = null; }
    },
    playBgs(o) {
      if (!o || !o.name) { if (this.bgs) this.bgs.pause(); this.bgs = null; this.bgsData = null; return; }
      if (this.bgsData && this.bgsData.name === o.name && this.bgs) return;
      if (this.bgs) this.bgs.pause();
      const a = this._el('bgs', o, true);
      this.bgsData = Object.assign({}, o);
      if (!a) return;
      this.bgs = a;
      this._start(a);
    },
    playMe(o) {
      if (!o || !o.name) return;
      const a = this._el('me', o, false);
      if (!a) return;
      const bgm = this.bgm;
      if (bgm) bgm.volume = 0;
      a.onended = () => { if (bgm) bgm.volume = this._vol(this.bgmData, 'bgm'); };
      this._start(a);
    },
    playSe(o) {
      if (!o || !o.name) return;
      const a = this._el('se', o, false);
      if (a) this._start(a);
    },
    saveBgm() { this.saved = { bgm: this.bgmData && Object.assign({}, this.bgmData), bgs: this.bgsData && Object.assign({}, this.bgsData) }; },
    replayBgm() { if (this.saved) { this.playBgm(this.saved.bgm); if (this.saved.bgs) this.playBgs(this.saved.bgs); } },
    // SE do sistema (cursor/ok/cancel/buzzer...) — nomes vêm de System.sounds
    sys(idx) {
      const s = ((MR.data.db.system || {}).sounds || [])[idx];
      if (s) this.playSe(s);
    },
  };

  /* ------------------------------------------------------------------ input */
  MR.input = {
    keys: {}, trig: {}, rep: {}, hold: {}, pointer: { x: 0, y: 0, down: false, trig: false, cancel: false },
    map: {
      ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right', ArrowUp: 'up', KeyW: 'up',
      ArrowDown: 'down', KeyS: 'down', Enter: 'ok', Space: 'ok', KeyZ: 'ok', Escape: 'cancel', KeyX: 'cancel',
      Numpad0: 'cancel', ShiftLeft: 'shift', ShiftRight: 'shift', PageUp: 'pageup', KeyQ: 'pageup',
      PageDown: 'pagedown', KeyE: 'pagedown', F9: 'debug',
    },
    init(canvas) {
      this.canvas = canvas;
      const down = (a) => { if (!this.keys[a]) this.trig[a] = true; this.keys[a] = true; };
      window.addEventListener('keydown', (e) => {
        const a = this.map[e.code];
        if (a) { e.preventDefault(); down(a); MR.audio.unlock(); }
      });
      window.addEventListener('keyup', (e) => { const a = this.map[e.code]; if (a) this.keys[a] = false; });
      window.addEventListener('blur', () => { this.keys = {}; });
      const pos = (e) => {
        const r = canvas.getBoundingClientRect();
        this.pointer.x = (e.clientX - r.left) * (canvas.width / r.width);
        this.pointer.y = (e.clientY - r.top) * (canvas.height / r.height);
      };
      canvas.addEventListener('pointerdown', (e) => {
        pos(e); MR.audio.unlock();
        if (e.button === 2) { this.pointer.cancel = true; return; }
        this.pointer.down = true; this.pointer.trig = true;
      });
      canvas.addEventListener('pointermove', pos);
      window.addEventListener('pointerup', () => { this.pointer.down = false; });
      canvas.addEventListener('contextmenu', (e) => e.preventDefault());
      // direcional virtual (HTML) para toque
      document.querySelectorAll('[data-mr-key]').forEach((el) => {
        const a = el.getAttribute('data-mr-key');
        const on = (e) => { e.preventDefault(); MR.audio.unlock(); down(a); };
        const off = (e) => { e.preventDefault(); this.keys[a] = false; };
        el.addEventListener('pointerdown', on);
        el.addEventListener('pointerup', off);
        el.addEventListener('pointerleave', off);
        el.addEventListener('pointercancel', off);
      });
    },
    update() {
      // repetição para menus: dispara no 1º frame, depois a cada 6 frames após 24
      for (const a of Object.keys(this.keys)) {
        if (this.keys[a]) {
          this.hold[a] = (this.hold[a] || 0) + 1;
          const h = this.hold[a];
          this.rep[a] = h === 1 || (h > 24 && (h - 24) % 6 === 0);
        } else { this.hold[a] = 0; this.rep[a] = false; }
      }
    },
    endFrame() { this.trig = {}; this.pointer.trig = false; this.pointer.cancel = false; },
    pressed(a) { return !!this.keys[a]; },
    triggered(a) { return !!this.trig[a]; },
    repeated(a) { return !!this.rep[a]; },
    dir4() {
      if (this.keys.down) return 2;
      if (this.keys.left) return 4;
      if (this.keys.right) return 6;
      if (this.keys.up) return 8;
      return 0;
    },
    // “OK” genérico: tecla ou toque/clique em qualquer lugar
    okTriggered() { return this.triggered('ok') || this.pointer.trig; },
    cancelTriggered() { return this.triggered('cancel') || this.pointer.cancel; },
    // versões que “consomem” o evento: evitam que o mesmo OK que fechou uma janela também dispare uma ação no mapa
    takeOk() { const r = this.okTriggered(); if (r) { this.trig.ok = false; this.pointer.trig = false; } return !!r; },
    takeCancel() { const r = this.cancelTriggered(); if (r) { this.trig.cancel = false; this.pointer.cancel = false; } return !!r; },
  };

  /* ------------------------------------------------------------------ estado do jogo */
  const G = MR.G = {
    switches: {}, variables: {}, selfSwitches: {}, gold: 0, items: {}, weapons: {}, armors: {},
    party: [], actors: {}, steps: 0, playtime: 0, mapId: 0, px: 0, py: 0, pdir: 2,
    dirty: true, menuDisabled: false, saveDisabled: false, encounterDisabled: false,
    timer: { on: false, frames: 0 }, flags: {},

    reset() {
      this.switches = {}; this.variables = {}; this.selfSwitches = {};
      this.gold = 0; this.items = {}; this.weapons = {}; this.armors = {};
      this.party = []; this.actors = {}; this.steps = 0; this.playtime = 0;
      this.menuDisabled = false; this.saveDisabled = false; this.encounterDisabled = false;
      this.timer = { on: false, frames: 0 }; this.flags = {};
      this.dirty = true;
    },
    sw(id) { return !!this.switches[id]; },
    setSw(id, v) { if (!!this.switches[id] !== !!v) this.dirty = true; this.switches[id] = !!v; },
    v(id) { return this.variables[id] || 0; },
    setV(id, v) {
      v = typeof v === 'number' ? Math.trunc(v) : (parseInt(v, 10) || 0);
      v = MR.u.clamp(v, -99999999, 99999999);
      if (this.variables[id] !== v) this.dirty = true;
      this.variables[id] = v;
    },
    ss(mapId, evId, ch) { return !!this.selfSwitches[mapId + ',' + evId + ',' + ch]; },
    setSs(mapId, evId, ch, v) { this.selfSwitches[mapId + ',' + evId + ',' + ch] = !!v; this.dirty = true; },
    // inventário
    container(kind) { return kind === 'item' ? this.items : kind === 'weapon' ? this.weapons : this.armors; },
    numItems(kind, id) { return this.container(kind)[id] || 0; },
    gain(kind, id, n) {
      const c = this.container(kind);
      c[id] = MR.u.clamp((c[id] || 0) + n, 0, 99);
      if (!c[id]) delete c[id];
      this.dirty = true;
    },
    db(kind) {
      const d = MR.data.db;
      return kind === 'item' ? d.items : kind === 'weapon' ? d.weapons : d.armors;
    },
    gainGold(n) { this.gold = MR.u.clamp(this.gold + n, 0, 99999999); },
    // ---- protagonistas
    actor(id) {
      if (!this.actors[id]) {
        const d = (MR.data.db.actors || [])[id];
        if (!d) return null;
        const cls = (MR.data.db.classes || [])[d.classId] || {};
        const lv = d.initialLevel || 1;
        const a = {
          id, name: d.name, nickname: d.nickname || '', classId: d.classId, level: lv, exp: 0,
          equips: (d.equips || []).slice(), skills: [], states: [], hp: 1, mp: 0, tp: 0,
          characterName: d.characterName, characterIndex: d.characterIndex,
          faceName: d.faceName, faceIndex: d.faceIndex, profile: d.profile || '',
        };
        a.exp = MR.rules.expForLevel(a, lv);
        (cls.learnings || []).forEach((l) => { if (l.level <= lv && a.skills.indexOf(l.skillId) < 0) a.skills.push(l.skillId); });
        this.actors[id] = a;
        a.hp = MR.rules.param(a, 0);
        a.mp = MR.rules.param(a, 1);
      }
      return this.actors[id];
    },
    members() { return this.party.map((id) => this.actor(id)).filter(Boolean); },
    addMember(id) { if (this.party.indexOf(id) < 0 && this.actor(id)) this.party.push(id); },
    newGame() {
      this.reset();
      const s = MR.data.db.system;
      (s.partyMembers || []).forEach((id) => this.addMember(id));
      this.gold = s.startingGold || 0;
      this.mapId = s.startMapId; this.px = s.startX; this.py = s.startY; this.pdir = 2;
    },
    snapshot() {
      const o = MR.u.clone({
        switches: this.switches, variables: this.variables, selfSwitches: this.selfSwitches, gold: this.gold,
        items: this.items, weapons: this.weapons, armors: this.armors, party: this.party, actors: this.actors,
        steps: this.steps, playtime: this.playtime, flags: this.flags,
        menuDisabled: this.menuDisabled, saveDisabled: this.saveDisabled, encounterDisabled: this.encounterDisabled,
      });
      o.mapId = this.mapId; o.px = this.px; o.py = this.py; o.pdir = this.pdir;
      return o;
    },
    restore(s) { Object.assign(this, MR.u.clone(s)); this.dirty = true; },
  };

  /* ------------------------------------------------------------------ regras (fórmulas de RPG Maker) */
  MR.rules = {
    expForLevel(a, level) {
      const cls = (MR.data.db.classes || [])[a.classId] || {};
      const p = cls.expParams || [30, 20, 30, 30];
      const basis = p[0], extra = p[1], accA = p[2], accB = p[3];
      return Math.round(basis * Math.pow(level - 1, 0.9 + accA / 250) * level * (level + 1) /
        (6 + Math.pow(level, 2) / 50 / accB) + (level - 1) * extra);
    },
    // 0 mhp 1 mmp 2 atk 3 def 4 mat 5 mdf 6 agi 7 luk
    param(a, id) {
      const cls = (MR.data.db.classes || [])[a.classId] || {};
      const row = (cls.params || [])[id];
      let v = row ? (row[MR.u.clamp(a.level, 1, row.length - 1)] || row[row.length - 1] || 0) : (id < 2 ? 100 : 10);
      (a.equips || []).forEach((eid, slot) => {
        const it = this.equipData(a, slot, eid);
        if (it && it.params) v += it.params[id] || 0;
      });
      return Math.max(0, Math.floor(v));
    },
    equipData(a, slot, eid) {
      if (!eid) return null;
      const typeId = (((MR.data.db.actors || [])[a.id] || {}).equips || []);
      return slot === 0 ? (MR.data.db.weapons || [])[eid] : (MR.data.db.armors || [])[eid];
    },
    levelUp(a) {
      const cls = (MR.data.db.classes || [])[a.classId] || {};
      const msgs = [];
      while (a.level < 99 && a.exp >= this.expForLevel(a, a.level + 1)) {
        a.level++;
        (cls.learnings || []).forEach((l) => {
          if (l.level === a.level && a.skills.indexOf(l.skillId) < 0) {
            a.skills.push(l.skillId);
            msgs.push(MR.t('learned', a.name, (((MR.data.db.skills || [])[l.skillId]) || {}).name));
          }
        });
        msgs.push(MR.t('levelUp', a.name, a.level));
      }
      return msgs;
    },
    term(kind, i, fallback) {
      const t = (MR.data.db.system || {}).terms || {};
      const arr = t[kind];
      return (arr && arr[i]) || fallback;
    },
    currency() { return (((MR.data.db.system || {}).currencyUnit) || ((((MR.data.db.system || {}).terms || {}).basic || [])[4])) || 'G'; },
  };

  /* ------------------------------------------------------------------ save / load */
  MR.save = {
    key(slot) { return 'maker-rebuild:' + (MR.config.saveKey || MR.config.title) + ':' + slot; },
    max: 8,
    read(slot) {
      try { const s = localStorage.getItem(this.key(slot)); return s ? JSON.parse(s) : null; } catch (e) { return null; }
    },
    write(slot) {
      try {
        const snap = { when: Date.now(), title: MR.G.mapName ? MR.G.mapName() : '', G: MR.G.snapshot() };
        localStorage.setItem(this.key(slot), JSON.stringify(snap));
        return true;
      } catch (e) { MR.warn('save', 'não foi possível salvar: ' + e); return false; }
    },
    load(slot) { const s = this.read(slot); if (!s) return false; MR.G.restore(s.G); return true; },
    any() { for (let i = 1; i <= this.max; i++) if (this.read(i)) return true; return false; },
  };

})(window);
