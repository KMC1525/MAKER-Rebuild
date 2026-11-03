/*!
 * MAKER-Rebuild runtime — UI: janelas, texto com códigos de controle, listas, mensagens.
 */
(function () {
  'use strict';
  const MR = window.MR;
  const IN = MR.input;

  /* ------------------------------------------------------------------ texto */
  const PALETTE = [
    '#ffffff', '#20a0d6', '#ff784c', '#66cc40', '#99ccff', '#ccc0ff', '#ffffa0', '#808080',
    '#c0c0c0', '#2080cc', '#ff3820', '#00a040', '#60a0e0', '#a060e0', '#e0d030', '#606060',
    '#202040', '#e08040', '#f0c040', '#4060c0', '#60c0e0', '#6040a0', '#c04080', '#a0a0a0',
    '#ffe0a0', '#a0e0a0', '#a0c0ff', '#ffa0a0', '#e0a0ff', '#c8c8c8', '#404060', '#101018',
  ];

  MR.text = {
    palette: PALETTE,
    actorName(n) { const a = MR.G.actor(n); return a ? a.name : ''; },
    // expande \V \N \P \G; os demais códigos viram ESC+letra
    convert(s) {
      s = String(s == null ? '' : s).replace(/\\\\/g, '\u0001');
      for (let i = 0; i < 4; i++) s = s.replace(/\\V\[(\d+)\]/gi, (_, n) => String(MR.G.v(+n)));
      s = s.replace(/\\N\[(\d+)\]/gi, (_, n) => this.actorName(+n));
      s = s.replace(/\\P\[(\d+)\]/gi, (_, n) => { const m = MR.G.members()[+n - 1]; return m ? m.name : ''; });
      s = s.replace(/\\G/gi, MR.rules.currency());
      s = s.replace(/\\/g, '\x1b').replace(/\u0001/g, '\\');
      return s;
    },
    // Quebra em itens posicionados. Retorna {items, lines, width}
    layout(ctx, raw, maxW, size) {
      const s = this.convert(raw);
      const items = [];
      let color = 0, fs = size, x = 0, line = 0, lastBreak = -1, lineStart = 0;
      const font = () => (ctx.font = fs + 'px ' + MR.ui.font);
      const place = (it) => {
        if (maxW > 0 && x + it.w > maxW && items.length > lineStart) {
          if (lastBreak >= lineStart) {                 // quebra no último espaço
            line++;
            let nx = 0;
            for (let k = lastBreak + 1; k < items.length; k++) { items[k].line = line; items[k].x = nx; nx += items[k].w || 0; }
            x = nx; lineStart = lastBreak + 1;
          } else { line++; x = 0; lineStart = items.length; }
          lastBreak = -1;
        }
        it.x = x; it.line = line; x += it.w || 0; items.push(it);
      };
      for (let i = 0; i < s.length; i++) {
        const ch = s[i];
        if (ch === '\n') { line++; x = 0; lastBreak = -1; lineStart = items.length; continue; }
        if (ch === '\x1b') {
          const c = s[++i];
          if (!c) break;
          if (/[CcIi]/.test(c)) {
            const m = /^\[(\d+)\]/.exec(s.slice(i + 1));
            const n = m ? +m[1] : 0;
            if (m) i += m[0].length;
            if (c === 'C' || c === 'c') color = n;
            else place({ k: 'i', n, w: MR.ui.iconSize() + 4 * MR.ui.sc });
          } else if (c === '{') fs = Math.min(fs + 12 * MR.ui.sc, size * 2.4);
          else if (c === '}') fs = Math.max(fs - 12 * MR.ui.sc, size * 0.5);
          else if (c === '.') items.push({ k: 'ctl', op: 'wait', v: 15 });
          else if (c === '|') items.push({ k: 'ctl', op: 'wait', v: 60 });
          else if (c === '!') items.push({ k: 'ctl', op: 'input' });
          else if (c === '>') items.push({ k: 'ctl', op: 'fast', v: true });
          else if (c === '<') items.push({ k: 'ctl', op: 'fast', v: false });
          else if (c === '^') items.push({ k: 'ctl', op: 'noclose' });
          continue;
        }
        font();
        const w = ctx.measureText(ch).width;
        if (ch === ' ' || MR.u.isCJK(ch)) lastBreak = ch === ' ' ? items.length : items.length;
        place({ k: 'c', ch, w, color, size: fs });
      }
      return { items, lines: line + 1, width: Math.max(0, x) };
    },
    draw(ctx, lay, ox, oy, lineH, upto, align, boxW) {
      let n = 0;
      ctx.textBaseline = 'alphabetic';
      for (const it of lay.items) {
        if (it.k === 'ctl') continue;
        if (upto != null && n++ >= upto) break;
        let dx = ox + it.x;
        const dy = oy + it.line * lineH;
        if (align && boxW) {
          // alinhamento por linha (apenas modo de uma linha usa isso)
          dx += align === 'center' ? (boxW - lay.width) / 2 : align === 'right' ? boxW - lay.width : 0;
        }
        if (it.k === 'i') { MR.ui.icon(ctx, it.n, dx, dy + 2 * MR.ui.sc); continue; }
        ctx.font = it.size + 'px ' + MR.ui.font;
        const base = dy + lineH * 0.72;
        ctx.lineWidth = 4 * MR.ui.sc; ctx.strokeStyle = 'rgba(0,0,0,0.65)'; ctx.lineJoin = 'round';
        ctx.strokeText(it.ch, dx, base);
        ctx.fillStyle = PALETTE[it.color] || '#fff';
        ctx.fillText(it.ch, dx, base);
      }
    },
  };

  /* ------------------------------------------------------------------ UI base */
  MR.ui = {
    sc: 1,
    font: '"GameFont","Noto Sans","Segoe UI",system-ui,sans-serif',
    init() { this.sc = MR.config.screen.h / 624; if (this.sc < 0.5) this.sc = 0.5; },
    fs() { return Math.round(28 * this.sc); },
    lh() { return Math.round(36 * this.sc); },
    pad() { return Math.round(18 * this.sc); },
    iconSize() { return Math.round(32 * this.sc); },
    icon(ctx, n, x, y) {
      if (!n) return;
      const im = MR.assets.image('system', 'IconSet');
      if (!im.mrReady) return;
      const cell = im.width / 16, size = this.iconSize();
      ctx.drawImage(im, (n % 16) * cell, Math.floor(n / 16) * cell, cell, cell, x, y, size, size);
    },
    // largura/altura de um texto de uma linha
    measure(ctx, str, size) { return MR.text.layout(ctx, str, 0, size || this.fs()).width; },
    // texto de uma linha com códigos; align: left|center|right dentro de boxW
    text(ctx, str, x, y, boxW, align, size) {
      const lay = MR.text.layout(ctx, str, 0, size || this.fs());
      MR.text.draw(ctx, lay, x, y, this.lh(), null, align || 'left', boxW);
    },
    window(ctx, x, y, w, h, opts) {
      opts = opts || {};
      const skin = MR.assets.image('system', MR.config.windowskin || 'Window');
      ctx.save();
      const op = opts.opacity != null ? opts.opacity : 1;
      if (skin.mrReady && skin.width >= 128 && skin.width === skin.height && MR.config.engine !== 'xp') {
        const half = skin.width / 2, b = half / 4, k = this.sc * (MR.config.tileSize >= 48 ? 1 : 0.75);
        const bd = Math.max(8, b * k);
        ctx.globalAlpha = 0.9 * op;
        ctx.drawImage(skin, 0, 0, half, half, x + 2, y + 2, w - 4, h - 4);
        ctx.globalAlpha = op;
        const s = half, ox = half;
        const mid = s - 2 * b;
        const C = (sx, sy, sw, sh, dx, dy, dw, dh) => ctx.drawImage(skin, ox + sx, sy, sw, sh, dx, dy, dw, dh);
        C(b, 0, mid, b, x + bd, y, w - 2 * bd, bd);                     // topo
        C(b, s - b, mid, b, x + bd, y + h - bd, w - 2 * bd, bd);        // base
        C(0, b, b, mid, x, y + bd, bd, h - 2 * bd);                     // esquerda
        C(s - b, b, b, mid, x + w - bd, y + bd, bd, h - 2 * bd);        // direita
        C(0, 0, b, b, x, y, bd, bd); C(s - b, 0, b, b, x + w - bd, y, bd, bd);
        C(0, s - b, b, b, x, y + h - bd, bd, bd); C(s - b, s - b, b, b, x + w - bd, y + h - bd, bd, bd);
      } else {
        // fallback “UI-UX” (sem windowskin): vidro escuro com borda
        const r = 10 * this.sc;
        ctx.globalAlpha = op;
        const g = ctx.createLinearGradient(0, y, 0, y + h);
        g.addColorStop(0, 'rgba(24,32,64,0.88)'); g.addColorStop(1, 'rgba(10,14,32,0.88)');
        ctx.fillStyle = g;
        rr(ctx, x, y, w, h, r); ctx.fill();
        ctx.lineWidth = 2 * this.sc; ctx.strokeStyle = 'rgba(210,225,255,0.85)';
        rr(ctx, x + 1, y + 1, w - 2, h - 2, r); ctx.stroke();
      }
      ctx.restore();
    },
    gauge(ctx, x, y, w, rate, c1, c2) {
      const h = Math.round(6 * this.sc);
      ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(x, y, w, h);
      const g = ctx.createLinearGradient(x, 0, x + w, 0);
      g.addColorStop(0, c1); g.addColorStop(1, c2);
      ctx.fillStyle = g; ctx.fillRect(x, y, Math.max(0, Math.floor(w * MR.u.clamp(rate, 0, 1))), h);
    },
    face(ctx, name, index, x, y, h) {
      const im = MR.assets.image('faces', name);
      if (!im.mrReady) return 0;
      const fw = im.width / 4, fh = im.height / 2, sc = h / fh;
      ctx.drawImage(im, (index % 4) * fw, Math.floor(index / 4) * fh, fw, fh, x, y, fw * sc, h);
      return fw * sc;
    },
  };

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  MR.ui.roundRect = rr;

  /* ------------------------------------------------------------------ lista selecionável */
  MR.ListWin = class {
    // opts: x,y,w, rows, cols, items:[{text, enabled, data}], onOk, onCancel, cancel(bool), drawItem(ctx,item,rect,i)
    constructor(o) {
      this.o = Object.assign({ cols: 1, rows: 4, enabled: true, cancel: true, items: [] }, o);
      this.items = this.o.items;
      this.index = 0; this.top = 0; this.active = true; this.visible = true;
      this.x = o.x; this.y = o.y; this.w = o.w;
      this.rowH = MR.ui.lh();
      this.layoutSize();
    }
    layoutSize() {
      this.visibleRows = Math.min(this.o.rows, Math.max(1, Math.ceil(this.items.length / this.o.cols)));
      this.h = this.visibleRows * this.rowH + MR.ui.pad() * 2;
    }
    setItems(items) { this.items = items; this.index = Math.min(this.index, Math.max(0, items.length - 1)); this.layoutSize(); }
    rect(i) {
      const pad = MR.ui.pad(), cw = (this.w - pad * 2) / this.o.cols;
      const col = i % this.o.cols, row = Math.floor(i / this.o.cols) - this.top;
      return { x: this.x + pad + col * cw, y: this.y + pad + row * this.rowH, w: cw, h: this.rowH };
    }
    update() {
      if (!this.active || !this.items.length) { if (this.active && this.o.cancel && IN.takeCancel()) { MR.audio.sys(2); this.o.onCancel && this.o.onCancel(); } return; }
      const n = this.items.length, cols = this.o.cols, old = this.index;
      if (IN.repeated('down')) this.index = (this.index + cols < n) ? this.index + cols : (this.index % cols);
      if (IN.repeated('up')) this.index = (this.index - cols >= 0) ? this.index - cols : Math.min(n - 1, this.index + (Math.ceil(n / cols) - 1) * cols);
      if (cols > 1) {
        if (IN.repeated('right') && this.index < n - 1) this.index++;
        if (IN.repeated('left') && this.index > 0) this.index--;
      }
      this.index = MR.u.clamp(this.index, 0, n - 1);
      const row = Math.floor(this.index / cols);
      if (row < this.top) this.top = row;
      if (row >= this.top + this.visibleRows) this.top = row - this.visibleRows + 1;
      // mouse / toque
      const p = IN.pointer;
      for (let i = this.top * cols; i < Math.min(n, (this.top + this.visibleRows) * cols); i++) {
        const r = this.rect(i);
        if (p.x >= r.x && p.x < r.x + r.w && p.y >= r.y && p.y < r.y + r.h) {
          if (p.trig) { if (this.index === i) { p.trig = false; this.index = i; this._ok(); return; } this.index = i; }
          break;
        }
      }
      if (old !== this.index) { MR.audio.sys(0); this.o.onMove && this.o.onMove(this.index, this.items[this.index]); }
      if (IN.takeOk()) this._ok();
      else if (this.o.cancel && IN.takeCancel()) { MR.audio.sys(2); this.o.onCancel && this.o.onCancel(); }
    }
    _ok() {
      const it = this.items[this.index];
      if (!it) return;
      if (it.enabled === false) { MR.audio.sys(3); return; }
      MR.audio.sys(1);
      this.o.onOk && this.o.onOk(this.index, it);
    }
    draw(ctx) {
      if (!this.visible) return;
      MR.ui.window(ctx, this.x, this.y, this.w, this.h);
      const cols = this.o.cols, n = this.items.length;
      for (let i = this.top * cols; i < Math.min(n, (this.top + this.visibleRows) * cols); i++) {
        const r = this.rect(i), it = this.items[i];
        if (i === this.index && this.active) {
          ctx.fillStyle = 'rgba(255,255,255,0.20)'; rr(ctx, r.x, r.y + 2, r.w - 4, r.h - 4, 6 * MR.ui.sc); ctx.fill();
        }
        ctx.globalAlpha = it.enabled === false ? 0.45 : 1;
        if (this.o.drawItem) this.o.drawItem(ctx, it, r, i);
        else MR.ui.text(ctx, it.text, r.x + 4, r.y, r.w - 8, it.align || 'left');
        ctx.globalAlpha = 1;
      }
      if (n > this.visibleRows * cols) {   // setas de rolagem
        ctx.fillStyle = 'rgba(255,255,255,0.7)';
        if (this.top > 0) ctx.fillText('▲', this.x + this.w / 2, this.y + 12 * MR.ui.sc);
        if ((this.top + this.visibleRows) * cols < n) ctx.fillText('▼', this.x + this.w / 2, this.y + this.h - 4);
      }
    }
  };

  /* ------------------------------------------------------------------ caixa de mensagem (evento 101/102/103/104/105) */
  MR.MessageBox = class {
    constructor() { this.reset(); }
    reset() {
      this.state = 'idle';   // idle | typing | waitInput | choices | number | item | scroll
      this.lay = null; this.shown = 0; this.wait = 0; this.fast = false; this.waitInput = false;
      this.face = null; this.pos = 2; this.bg = 0; this.done = null;
      this.choice = null; this.num = null;
    }
    busy() { return this.state !== 'idle'; }
    // lines: array de strings; opts: {face, faceIndex, bg, pos, speaker}
    show(lines, opts, done) {
      const sc = MR.ui.sc, ctx = MR.ctx;
      this.opts = opts || {};
      this.pos = this.opts.pos == null ? 2 : this.opts.pos;
      this.bg = this.opts.bg || 0;
      this.face = this.opts.face ? { name: this.opts.face, index: this.opts.faceIndex || 0 } : null;
      const W = MR.config.screen.w, pad = MR.ui.pad(), lh = MR.ui.lh();
      this.boxH = lh * 4 + pad * 2;
      this.boxY = this.pos === 0 ? 0 : this.pos === 1 ? Math.round((MR.config.screen.h - this.boxH) / 2) : MR.config.screen.h - this.boxH;
      this.textX = pad + (this.face ? lh * 4 + pad : 0);
      this.textW = W - this.textX - pad;
      this.lay = MR.text.layout(ctx, lines.join('\n'), this.textW, MR.ui.fs());
      // mais de 4 linhas → pagina
      this.pages = [];
      for (let l = 0; l < this.lay.lines; l += 4) this.pages.push(l);
      this.page = 0;
      this.shown = 0; this.wait = 0; this.fast = false; this.waitInput = false;
      this.state = 'typing'; this.done = done;
      this._open = 0;
    }
    pageItems() {
      const a = this.pages[this.page], b = a + 4;
      let count = 0;
      for (const it of this.lay.items) if (it.k !== 'ctl' && it.line >= a && it.line < b) count++;
      return count;
    }
    update() {
      if (this.state === 'idle') return;
      this._open = Math.min(1, (this._open || 0) + 0.25);
      if (this.state === 'typing') {
        const total = this.pageItems();
        if (this.wait > 0) { this.wait--; if (IN.takeOk()) { this.wait = 0; this.fast = true; } return; }
        if (IN.takeOk() || IN.pressed('shift')) this.fast = true;
        const speed = this.fast ? 6 : 1.5;
        this._acc = (this._acc || 0) + speed;
        while (this._acc >= 1 && this.shown < total) {
          this._acc -= 1; this.shown++;
          const ctl = this._ctlAt(this.shown);
          if (ctl) { this.wait = ctl; break; }
        }
        if (this.shown >= total) {
          if (this.opts.hold && this.page + 1 >= this.pages.length) {   // próxima instrução é escolha/número: não espera OK
            const cb = this.done; this.done = null; this.state = 'held'; if (cb) cb();
          } else { this.state = 'waitInput'; this.blink = 0; }
        }
      } else if (this.state === 'waitInput') {
        this.blink = (this.blink || 0) + 1;
        if (IN.takeOk() || IN.takeCancel()) {
          MR.audio.sys(1);
          if (this.page + 1 < this.pages.length) { this.page++; this.shown = 0; this.fast = false; this.state = 'typing'; }
          else this._finish();
        }
      } else if (this.state === 'choices' || this.state === 'item') {
        this.choice.update();
      } else if (this.state === 'number') {
        this._updateNumber();
      } else if (this.state === 'scroll') {
        this.scrollY -= this.fast ? 4 * MR.ui.sc : (this.opts.speed || 2) * 0.5 * MR.ui.sc;
        if (IN.takeOk() && this.opts.noFast !== true) this.fast = true;
        if (this.scrollY + this.lay.lines * MR.ui.lh() < 0) this._finish();
      }
    }
    // controles \. \| \! no meio do texto: devolve frames de espera após o item `n` (1-based) da página
    _ctlAt(n) {
      let seen = 0;
      const a = this.pages[this.page], b = a + 4;
      for (let i = 0; i < this.lay.items.length; i++) {
        const it = this.lay.items[i];
        if (it.k !== 'ctl' && it.line >= a && it.line < b) seen++;
        if (seen === n) {
          const nx = this.lay.items[i + 1];
          if (nx && nx.k === 'ctl' && nx.op === 'wait' && !this.fast) return nx.v;
          return 0;
        }
      }
      return 0;
    }
    _finish() {
      const cb = this.done;
      this.state = 'idle'; this.lay = null; this.done = null;
      if (cb) cb();
    }
    // ---- escolhas
    choices(list, opts, done) {
      const lh = MR.ui.lh(), pad = MR.ui.pad();
      const ctx = MR.ctx;
      let w = 0;
      list.forEach((t) => { w = Math.max(w, MR.ui.measure(ctx, t)); });
      w = Math.min(MR.config.screen.w - 40, w + pad * 2 + 24);
      const rows = Math.min(list.length, 8);
      const h = rows * lh + pad * 2;
      const pos = opts.pos == null ? 2 : opts.pos;
      const sw = MR.config.screen.w, sh = MR.config.screen.h;
      const x = pos === 0 ? 8 : pos === 1 ? Math.round((sw - w) / 2) : sw - w - 8;
      const msgOnScreen = this.lay != null;
      let y = msgOnScreen ? (this.boxY > sh / 2 ? this.boxY - h - 6 : this.boxY + this.boxH + 6) : Math.round((sh - h) / 2);
      y = MR.u.clamp(y, 4, sh - h - 4);
      this.state = 'choices'; this.done = done; this._open = 1;
      this.choice = new MR.ListWin({
        x, y, w, rows, items: list.map((t, i) => ({ text: t, i })), cancel: opts.cancelType !== undefined && opts.cancelType !== -1 && opts.cancelType !== null,
        onOk: (i) => this._pick(i), onCancel: () => this._pick(opts.cancelType),
      });
      this.defaultType = opts.defaultType || 0;
      this.choice.index = Math.max(0, this.defaultType);
      this._keepMsg = msgOnScreen;
    }
    _pick(i) {
      const cb = this.done;
      this.state = 'idle'; this.choice = null; this.lay = null; this.done = null;
      if (cb) cb(i);
    }
    // ---- entrada numérica
    inputNumber(digits, initial, done) {
      this.state = 'number'; this.done = done; this._open = 1;
      this.num = { digits, value: String(Math.max(0, initial || 0)).padStart(digits, '0').slice(-digits), cursor: 0 };
    }
    _updateNumber() {
      const n = this.num;
      if (IN.repeated('left')) n.cursor = (n.cursor + n.digits - 1) % n.digits;
      if (IN.repeated('right')) n.cursor = (n.cursor + 1) % n.digits;
      const d = n.value.split('').map(Number);
      if (IN.repeated('up')) d[n.cursor] = (d[n.cursor] + 1) % 10;
      if (IN.repeated('down')) d[n.cursor] = (d[n.cursor] + 9) % 10;
      n.value = d.join('');
      if (IN.takeOk()) { const cb = this.done; this.state = 'idle'; this.done = null; cb && cb(parseInt(n.value, 10) || 0); }
    }
    // ---- escolher item
    selectItem(itypeId, done) {
      const items = [];
      const db = MR.data.db.items || [];
      Object.keys(MR.G.items).forEach((id) => {
        const it = db[id];
        if (it && (it.itypeId || 1) === itypeId) items.push({ text: it.name, id: +id, icon: it.iconIndex, n: MR.G.items[id] });
      });
      const sw = MR.config.screen.w, lh = MR.ui.lh();
      this.state = 'item'; this.done = done; this._open = 1;
      this.choice = new MR.ListWin({
        x: 0, y: 0, w: sw, rows: 6, cols: 2, items: items.length ? items : [{ text: MR.t('empty'), id: 0, enabled: false }],
        onOk: (i, it) => { const cb = this.done; this.state = 'idle'; this.choice = null; cb && cb(it.id); },
        onCancel: () => { const cb = this.done; this.state = 'idle'; this.choice = null; cb && cb(0); },
        drawItem: (ctx, it, r) => { MR.ui.icon(ctx, it.icon, r.x, r.y + 2); MR.ui.text(ctx, it.text, r.x + MR.ui.iconSize() + 6, r.y, r.w, 'left'); if (it.n) MR.ui.text(ctx, '×' + it.n, r.x, r.y, r.w - 6, 'right'); },
      });
      this.choice.y = this.boxY != null && this.boxY < MR.config.screen.h / 2 ? MR.config.screen.h - this.choice.h : 0;
    }
    // ---- texto rolante (105)
    scrollText(lines, opts, done) {
      this.opts = opts || {};
      this.lay = MR.text.layout(MR.ctx, lines.join('\n'), MR.config.screen.w - MR.ui.pad() * 4, MR.ui.fs());
      this.scrollY = MR.config.screen.h; this.fast = false; this.state = 'scroll'; this.done = done; this._open = 1;
    }
    draw(ctx) {
      if (this.state === 'idle') return;
      const W = MR.config.screen.w, pad = MR.ui.pad(), lh = MR.ui.lh();
      if (this.state === 'scroll') {
        ctx.fillStyle = 'rgba(0,0,0,0.85)'; ctx.fillRect(0, 0, W, MR.config.screen.h);
        MR.text.draw(ctx, this.lay, pad * 2, this.scrollY, lh, null);
        return;
      }
      if ((this.lay && this.state !== 'item') || this.state === 'typing' || this.state === 'waitInput') {
        if (this.lay) {
          if (this.bg !== 2) {
            if (this.bg === 1) { ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(0, this.boxY, W, this.boxH); }
            else MR.ui.window(ctx, 0, this.boxY, W, this.boxH);
          }
          if (this.face) MR.ui.face(ctx, this.face.name, this.face.index, pad, this.boxY + pad, lh * 4);
          if (this.opts && this.opts.speaker) {
            const sw = MR.ui.measure(ctx, this.opts.speaker) + pad * 2;
            MR.ui.window(ctx, this.textX - pad, this.boxY - lh * 0.75, sw, lh * 1.1);
            MR.ui.text(ctx, this.opts.speaker, this.textX, this.boxY - lh * 0.75 + 2, sw, 'left');
          }
          const a = this.pages[this.page];
          const sub = { items: this.lay.items.filter((it) => it.k === 'ctl' || (it.line >= a && it.line < a + 4)).map((it) => Object.assign({}, it, { line: it.line - a })), width: this.lay.width };
          MR.text.draw(ctx, sub, this.textX, this.boxY + pad, lh, this.shown);
          if (this.state === 'waitInput' && Math.floor(this.blink / 20) % 2 === 0) {
            ctx.fillStyle = '#fff'; ctx.font = (MR.ui.fs() * 0.8) + 'px ' + MR.ui.font; ctx.fillText('▼', W / 2 - 6, this.boxY + this.boxH - 8 * MR.ui.sc);
          }
        }
      }
      if (this.choice) this.choice.draw(ctx);
      if (this.state === 'number') {
        const n = this.num, cw = 22 * MR.ui.sc + 6, w = n.digits * cw + pad * 2, h = lh + pad * 2;
        const x = Math.round((W - w) / 2), y = this.boxY != null && this.boxY > MR.config.screen.h / 2 ? this.boxY - h - 6 : this.boxY + this.boxH + 6;
        MR.ui.window(ctx, x, y, w, h);
        for (let i = 0; i < n.digits; i++) {
          if (i === n.cursor) { ctx.fillStyle = 'rgba(255,255,255,0.25)'; ctx.fillRect(x + pad + i * cw, y + pad, cw - 2, lh); }
          MR.ui.text(ctx, n.value[i], x + pad + i * cw, y + pad, cw - 2, 'center');
        }
      }
    }
  };

})();
