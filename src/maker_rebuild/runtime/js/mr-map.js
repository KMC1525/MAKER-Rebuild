/*!
 * MAKER-Rebuild runtime — mapa: tilemap, autotiles, personagens, eventos, cena de mapa.
 */
(function () {
  'use strict';
  const MR = window.MR;
  const IN = MR.input;
  const DX = { 2: 0, 4: -1, 6: 1, 8: 0 }, DY = { 2: 1, 4: 0, 6: 0, 8: -1 };
  const REV = { 2: 8, 4: 6, 6: 4, 8: 2 };
  MR.dirs = { DX, DY, REV };

  /* ------------------------------------------------------------------ autotiles */
  // Cada função devolve 4 quartos [x,y] (em meios-tiles dentro do bloco do autotile): TL, TR, BL, BR.
  // `s(dx,dy)` diz se o vizinho é do mesmo tipo.
  function pick(H, V, Dg, interior, side, edge, corner, inner) {
    if (!H && !V) return corner;
    if (!H) return side;
    if (!V) return edge;
    if (inner && !Dg) return inner;
    return interior;
  }
  function floorQ(s) {
    const L = s(-1, 0), R = s(1, 0), U = s(0, -1), D = s(0, 1);
    return [
      pick(L, U, s(-1, -1), [2, 4], [0, 4], [2, 2], [0, 2], [2, 0]),
      pick(R, U, s(1, -1), [1, 4], [3, 4], [1, 2], [3, 2], [3, 0]),
      pick(L, D, s(-1, 1), [2, 3], [0, 3], [2, 5], [0, 5], [2, 1]),
      pick(R, D, s(1, 1), [1, 3], [3, 3], [1, 5], [3, 5], [3, 1]),
    ];
  }
  function wallQ(s) {
    const L = s(-1, 0), R = s(1, 0), U = s(0, -1), D = s(0, 1);
    return [
      pick(L, U, true, [2, 2], [0, 2], [2, 0], [0, 0]),
      pick(R, U, true, [1, 2], [3, 2], [1, 0], [3, 0]),
      pick(L, D, true, [2, 1], [0, 1], [2, 3], [0, 3]),
      pick(R, D, true, [1, 1], [3, 1], [1, 3], [3, 3]),
    ];
  }
  function waterfallQ(s) {
    const L = s(-1, 0), R = s(1, 0);
    if (L && R) return [[2, 0], [1, 0], [2, 1], [1, 1]];
    if (!L && R) return [[0, 0], [1, 0], [0, 1], [1, 1]];
    if (L && !R) return [[2, 0], [3, 0], [2, 1], [3, 1]];
    return [[0, 0], [3, 0], [0, 1], [3, 1]];
  }

  /* ------------------------------------------------------------------ tilemap */
  MR.Tilemap = class {
    constructor(map, tileset) {
      this.map = map; this.ts = tileset || { tilesetNames: [], flags: [] };
      this.mode = this.ts.mode === 'xp' ? 'xp' : this.ts.mode === 'lcf' ? 'lcf' : 'mv';
      this.tw = MR.config.tileSize; this.th = MR.config.tileSize;
      const names = this.ts.tilesetNames || [];
      this.imgs = names.map((n, i) => (n ? MR.assets.image(this.mode === 'xp' && i > 0 ? 'autotiles' : 'tilesets', n) : null));
      this.hasWater = false;
    }
    pending() { return this.imgs.filter(Boolean); }
    id(x, y, z) {
      const m = this.map;
      if (x < 0 || y < 0 || x >= m.width || y >= m.height) return -1;
      return m.data[(z * m.height + y) * m.width + x] || 0;
    }
    flag(id) { return (this.ts.flags || [])[id] || 0; }
    isHigher(id) { return (this.flag(id) & 0x10) !== 0; }

    /** desenha todas as camadas visíveis: upper=false → chão; upper=true → tiles “☆” */
    draw(ctx, offX, offY, W, H, upper) {
      const tw = this.tw, th = this.th, m = this.map;
      const x0 = Math.floor(offX / tw), y0 = Math.floor(offY / th);
      const x1 = Math.min(m.width - 1, Math.ceil((offX + W) / tw)), y1 = Math.min(m.height - 1, Math.ceil((offY + H) / th));
      const frame = Math.floor((MR.tick || 0) / 30);
      for (let z = 0; z < 4; z++) {
        for (let y = Math.max(0, y0); y <= y1; y++) {
          for (let x = Math.max(0, x0); x <= x1; x++) {
            const id = this.id(x, y, z);
            if (id <= 0 || this.isHigher(id) !== upper) continue;
            this.drawTile(ctx, id, Math.round(x * tw - offX), Math.round(y * th - offY), x, y, z, frame);
          }
        }
        if (z === 2 && !upper) this.drawShadows(ctx, offX, offY, x0, y0, x1, y1);
      }
    }
    drawShadows(ctx, offX, offY, x0, y0, x1, y1) {
      const m = this.map, tw = this.tw, th = this.th;
      ctx.fillStyle = 'rgba(0,0,0,0.5)';
      for (let y = Math.max(0, y0); y <= y1; y++) {
        for (let x = Math.max(0, x0); x <= x1; x++) {
          const bits = this.id(x, y, 4);
          if (bits <= 0) continue;
          for (let i = 0; i < 4; i++) if (bits & (1 << i)) {
            ctx.fillRect(Math.round(x * tw - offX + (i % 2) * tw / 2), Math.round(y * th - offY + Math.floor(i / 2) * th / 2), tw / 2, th / 2);
          }
        }
      }
    }
    drawTile(ctx, id, dx, dy, mx, my, z, frame) {
      const tw = this.tw, th = this.th;
      if (this.mode === 'xp') return this.drawXp(ctx, id, dx, dy);
      if (this.mode === 'lcf') { ctx.fillStyle = 'hsl(' + (id * 37 % 360) + ',40%,' + (30 + id % 30) + '%)'; ctx.fillRect(dx, dy, tw, th); return; }
      if (id < 2048) {                           // B C D E e A5
        const set = id >= 1536 ? 4 : 5 + (id >> 8);
        const img = this.imgs[set];
        if (!img || !img.mrReady) return;
        const cols = set === 4 ? 8 : 16, sw = img.width / cols, sh = sw;
        const sx = ((id >> 7) % 2 * 8 + (id & 7)) * sw, sy = (((id & 255) >> 3) % 16) * sh;
        ctx.drawImage(img, sx, sy, sw, sh, dx, dy, tw, th);
        return;
      }
      const kind = Math.floor((id - 2048) / 48), tx = kind % 8, ty = Math.floor(kind / 8);
      let set, bx, by, q, fall = false;
      const same = (ox, oy) => {
        const n = this.id(mx + ox, my + oy, z);
        if (n < 0) return true;
        return n >= 2048 && Math.floor((n - 2048) / 48) === kind;
      };
      if (id < 2816) {                            // A1: água / cachoeira
        set = 0; this.hasWater = true;
        const w = [0, 1, 2, 1][frame % 4];
        if (kind === 0) { bx = w * 2; by = 0; } else if (kind === 1) { bx = w * 2; by = 3; }
        else if (kind === 2) { bx = 6; by = 0; } else if (kind === 3) { bx = 6; by = 3; }
        else {
          bx = Math.floor(tx / 4) * 8; by = ty * 6 + Math.floor(tx / 2) % 2 * 3;
          if (kind % 2 === 0) bx += w * 2; else { bx += 6; fall = true; by += frame % 3; }
        }
        q = fall ? waterfallQ(same) : floorQ(same);
      } else if (id < 4352) { set = 1; bx = tx * 2; by = (ty - 2) * 3; q = floorQ(same); }      // A2
      else if (id < 5888) { set = 2; bx = tx * 2; by = (ty - 6) * 2; q = wallQ(same); }         // A3
      else {                                                                                     // A4
        set = 3; bx = tx * 2; by = Math.floor((ty - 10) * 2.5 + (ty % 2 === 1 ? 0.5 : 0));
        q = ty % 2 === 1 ? wallQ(same) : floorQ(same);
      }
      const img = this.imgs[set];
      if (!img || !img.mrReady) return;
      const sw1 = img.width / 32, sh1 = sw1, dw = tw / 2, dh = th / 2;   // meio-tile de origem
      for (let i = 0; i < 4; i++) {
        ctx.drawImage(img, (bx * 2 + q[i][0]) * sw1, (by * 2 + q[i][1]) * sh1, sw1, sh1,
          dx + (i % 2) * dw, dy + Math.floor(i / 2) * dh, dw, dh);
      }
    }
    drawXp(ctx, id, dx, dy) {
      const tw = this.tw, th = this.th;
      if (id < 48) return;
      if (id < 384) {
        const img = this.imgs[Math.floor(id / 48)];
        if (!img || !img.mrReady) return;
        const u = img.width / 3;                // tile central do autotile XP
        ctx.drawImage(img, u, u * 2, u, u, dx, dy, tw, th);
        return;
      }
      const img = this.imgs[0];
      if (!img || !img.mrReady) return;
      const n = id - 384, u = img.width / 8;
      ctx.drawImage(img, (n % 8) * u, Math.floor(n / 8) * u, u, u, dx, dy, tw, th);
    }
  };

  /* ------------------------------------------------------------------ personagens */
  MR.Char = class {
    constructor(kind) {
      this.kind = kind;            // 'player' | 'event'
      this.x = 0; this.y = 0; this.rx = 0; this.ry = 0; this.dir = 2;
      this.pattern = 1; this.origPattern = 1; this.animCount = 0; this.stopCount = 0;
      this.moveSpeed = 4; this.moveFreq = 3; this.through = false; this.transparent = false;
      this.walkAnime = true; this.stepAnime = false; this.dirFix = false; this.priority = 1;
      this.image = { tileId: 0, characterName: '', characterIndex: 0 };
      this.route = null; this.routeIdx = 0; this.routeWait = 0; this.routeBackup = null;
      this.moveSuccess = true; this.locked = false; this.dashing = false; this.opacity = 255;
      this.jump = null; this.balloon = null; this.erased = false;
    }
    setPos(x, y) { this.x = this.rx = x; this.y = this.ry = y; }
    isMoving() { return this.rx !== this.x || this.ry !== this.y; }
    isNormalPriority() { return this.priority === 1; }
    pos(x, y) { return this.x === x && this.y === y; }
    dpf() { return Math.pow(2, this.moveSpeed + (this.dashing ? 1 : 0)) / 256; }
    setDir(d) { if (!this.dirFix && d) this.dir = d; }
    canPass(map, x, y, d) {
      const x2 = x + DX[d], y2 = y + DY[d];
      if (!map.isValid(x2, y2)) return false;
      if (this.through) return true;
      if (!map.isPassable(x, y, d)) return false;
      if (!map.isPassable(x2, y2, REV[d])) return false;
      return !map.collidedWithChars(x2, y2, this);
    }
    moveStraight(map, d) {
      this.moveSuccess = this.canPass(map, this.x, this.y, d);
      this.setDir(d);
      if (this.moveSuccess) {
        this.x += DX[d]; this.y += DY[d]; this.stopCount = 0;
        if (this.kind === 'player') MR.G.steps++;
      }
      return this.moveSuccess;
    }
    moveDiagonal(map, h, v) {
      this.moveSuccess = (this.canPass(map, this.x, this.y, v) && this.canPass(map, this.x, this.y + DY[v], h)) ||
        (this.canPass(map, this.x, this.y, h) && this.canPass(map, this.x + DX[h], this.y, v));
      if (this.moveSuccess) { this.x += DX[h]; this.y += DY[v]; this.stopCount = 0; }
      if (!this.dirFix) this.dir = this.dir === REV[h] ? h : this.dir === REV[v] ? v : this.dir;
    }
    jumpTo(dx, dy) {
      this.setDir(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 6 : 4) : (dy > 0 ? 2 : 8));
      this.x += dx; this.y += dy;
      const dist = Math.max(1, Math.round(Math.sqrt(dx * dx + dy * dy)));
      this.jump = { n: 0, peak: 10 + dist * 2, total: 2 * (10 + dist * 2) };
      this.rx = this.x - dx; this.ry = this.y - dy; this.jumpFrom = { x: this.rx, y: this.ry };
    }
    turnToward(ch) {
      const sx = this.x - ch.x, sy = this.y - ch.y;
      if (Math.abs(sx) > Math.abs(sy)) this.setDir(sx > 0 ? 4 : 6); else if (sy !== 0) this.setDir(sy > 0 ? 8 : 2);
    }
    turnAway(ch) {
      const sx = this.x - ch.x, sy = this.y - ch.y;
      if (Math.abs(sx) > Math.abs(sy)) this.setDir(sx > 0 ? 6 : 4); else if (sy !== 0) this.setDir(sy > 0 ? 2 : 8);
    }
    moveToward(map, ch) {
      const sx = this.x - ch.x, sy = this.y - ch.y;
      if (Math.abs(sx) > Math.abs(sy)) { this.moveStraight(map, sx > 0 ? 4 : 6); if (!this.moveSuccess && sy !== 0) this.moveStraight(map, sy > 0 ? 8 : 2); }
      else if (sy !== 0) { this.moveStraight(map, sy > 0 ? 8 : 2); if (!this.moveSuccess && sx !== 0) this.moveStraight(map, sx > 0 ? 4 : 6); }
    }
    moveAway(map, ch) {
      const sx = this.x - ch.x, sy = this.y - ch.y;
      if (Math.abs(sx) > Math.abs(sy)) { this.moveStraight(map, sx > 0 ? 6 : 4); if (!this.moveSuccess && sy !== 0) this.moveStraight(map, sy > 0 ? 2 : 8); }
      else if (sy !== 0) { this.moveStraight(map, sy > 0 ? 2 : 8); if (!this.moveSuccess && sx !== 0) this.moveStraight(map, sx > 0 ? 6 : 4); }
    }
    /* ---- rotas de movimento */
    forceRoute(route) {
      if (!this.route) this.routeBackup = null;
      this.route = route; this.routeIdx = 0; this.routeWait = 0; this.routeDone = false;
    }
    stopRoute() { this.route = null; this.routeDone = true; }
    updateRoute(map, scene) {
      if (!this.route) return;
      if (this.routeWait > 0) { this.routeWait--; return; }
      const list = this.route.list || [];
      if (this.routeIdx >= list.length) {
        if (this.route.repeat !== false && list.length > 1) this.routeIdx = 0;
        else { this.route = null; this.routeDone = true; return; }
      }
      const c = list[this.routeIdx], p = c.parameters || [];
      let advance = true;
      const rnd = () => [2, 4, 6, 8][MR.u.rand(4)];
      const player = scene.player;
      switch (c.code) {
        case 0: if (this.route.repeat !== false && list.length > 1) this.routeIdx = -1; else { this.route = null; this.routeDone = true; return; } break;
        case 1: case 2: case 3: case 4: this.moveStraight(map, c.code * 2); advance = this.moveSuccess || this.route.skippable; break;
        case 5: this.moveDiagonal(map, 4, 2); advance = this.moveSuccess || this.route.skippable; break;
        case 6: this.moveDiagonal(map, 6, 2); advance = this.moveSuccess || this.route.skippable; break;
        case 7: this.moveDiagonal(map, 4, 8); advance = this.moveSuccess || this.route.skippable; break;
        case 8: this.moveDiagonal(map, 6, 8); advance = this.moveSuccess || this.route.skippable; break;
        case 9: this.moveStraight(map, rnd()); break;
        case 10: this.moveToward(map, player); break;
        case 11: this.moveAway(map, player); break;
        case 12: this.moveStraight(map, this.dir); advance = this.moveSuccess || this.route.skippable; break;
        case 13: this.moveStraight(map, REV[this.dir]); advance = this.moveSuccess || this.route.skippable; break;
        case 14: this.jumpTo(p[0], p[1]); break;
        case 15: this.routeWait = p[0] || 0; break;
        case 16: this.setDir(2); break; case 17: this.setDir(4); break; case 18: this.setDir(6); break; case 19: this.setDir(8); break;
        case 20: this.setDir({ 2: 4, 4: 8, 8: 6, 6: 2 }[this.dir]); break;
        case 21: this.setDir({ 2: 6, 6: 8, 8: 4, 4: 2 }[this.dir]); break;
        case 22: this.setDir(REV[this.dir]); break;
        case 23: this.setDir(MR.u.rand(2) ? { 2: 4, 4: 8, 8: 6, 6: 2 }[this.dir] : { 2: 6, 6: 8, 8: 4, 4: 2 }[this.dir]); break;
        case 24: this.setDir(rnd()); break;
        case 25: this.turnToward(player); break;
        case 26: this.turnAway(player); break;
        case 27: MR.G.setSw(p[0], true); break;
        case 28: MR.G.setSw(p[0], false); break;
        case 29: this.moveSpeed = p[0]; break;
        case 30: this.moveFreq = p[0]; break;
        case 31: this.walkAnime = true; break; case 32: this.walkAnime = false; break;
        case 33: this.stepAnime = true; break; case 34: this.stepAnime = false; break;
        case 35: this.dirFix = true; break; case 36: this.dirFix = false; break;
        case 37: this.through = true; break; case 38: this.through = false; break;
        case 39: this.transparent = true; break; case 40: this.transparent = false; break;
        case 41: this.image = { tileId: 0, characterName: p[0], characterIndex: p[1] }; this.pattern = this.origPattern; break;
        case 42: this.opacity = p[0]; break;
        case 44: MR.audio.playSe(p[0]); break;
        case 45: try { new Function('$gameVariables', '$gameSwitches', 'self', String(p[0]))(MR.api.$gameVariables, MR.api.$gameSwitches, this); } catch (e) { MR.warn('route-script', 'script em rota falhou: ' + e); } break;
        default: break;
      }
      if (advance) this.routeIdx++;
    }
    update(map, scene) {
      const wasMoving = this.isMoving();
      if (this.jump) {
        const j = this.jump; j.n++;
        const t = j.n / j.total;
        this.rx = this.jumpFrom.x + (this.x - this.jumpFrom.x) * t;
        this.ry = this.jumpFrom.y + (this.y - this.jumpFrom.y) * t;
        if (j.n >= j.total) { this.jump = null; this.rx = this.x; this.ry = this.y; this.onStepEnd && this.onStepEnd(); }
      } else if (this.isMoving()) {
        const d = this.dpf();
        if (this.x < this.rx) this.rx = Math.max(this.x, this.rx - d); else if (this.x > this.rx) this.rx = Math.min(this.x, this.rx + d);
        if (this.y < this.ry) this.ry = Math.max(this.y, this.ry - d); else if (this.y > this.ry) this.ry = Math.min(this.y, this.ry + d);
        if (!this.isMoving() && this.onStepEnd) this.onStepEnd();
      }
      // animação
      if (this.isMoving() && this.walkAnime || this.stepAnime) {
        this.animCount++;
        if (this.animCount >= (9 - this.moveSpeed - (this.dashing ? 1 : 0)) * 3) {
          this.pattern = (this.pattern + 1) % 4; this.animCount = 0;
        }
      } else if (!this.stepAnime && !this.isMoving() && !this.jump) {
        this.pattern = this.origPattern; this.animCount = 0;
      }
      if (!this.isMoving() && !this.jump) { this.stopCount++; if (this.route) this.updateRoute(map, scene); }
      if (this.balloon) { this.balloon.t++; if (this.balloon.t > 100) this.balloon = null; }
      void wasMoving;
    }
    patternIndex() { return this.pattern === 3 ? 1 : this.pattern; }
    // ---- desenho
    draw(ctx, offX, offY) {
      if (this.transparent || this.erased) return;
      const tw = MR.config.tileSize;
      let px = Math.round(this.rx * tw - offX), py = Math.round(this.ry * tw - offY);
      if (this.jump) {
        const j = this.jump, k = j.n - j.total / 2, h = (j.peak * j.peak - k * k) / 2 * 0.2 * tw / 48;
        py -= Math.max(0, h);
      }
      const im = this.image;
      ctx.save();
      ctx.globalAlpha = this.opacity / 255;
      if (im.tileId > 0) {
        const tm = MR.sceneMap && MR.sceneMap.tilemap;
        if (tm) tm.drawTile(ctx, im.tileId, px, py, -9, -9, 0, 0);
      } else if (im.characterName) {
        const img = MR.assets.image('characters', im.characterName);
        if (img.mrReady) {
          const xp = MR.config.engine === 'xp';
          const big = xp || im.characterName.charAt(0) === '$';
          const cols = xp ? 4 : 3, rows = 4;
          const bw = big ? img.width : img.width / 4, bh = big ? img.height : img.height / 2;
          const fw = bw / cols, fh = bh / rows;
          const ci = big ? 0 : im.characterIndex || 0;
          const sx = (big ? 0 : (ci % 4) * bw) + (xp ? this.pattern : this.patternIndex()) * fw;
          const sy = (big ? 0 : Math.floor(ci / 4) * bh) + ((this.dir - 2) / 2) * fh;
          const shift = (im.characterName.charAt(0) === '!' || im.characterName.indexOf('!$') === 0) ? 0 : 6 * tw / 48;
          ctx.drawImage(img, sx, sy, fw, fh, px + tw / 2 - fw / 2, py + tw - fh - shift, fw, fh);
        }
      }
      if (this.balloon) this.drawBalloon(ctx, px, py);
      ctx.restore();
    }
    drawBalloon(ctx, px, py) {
      const img = MR.assets.image('system', 'Balloon');
      if (!img.mrReady) return;
      const u = img.width / 8, fr = Math.min(7, Math.floor(this.balloon.t / 8) % 8), row = this.balloon.id - 1;
      ctx.drawImage(img, fr * u, row * u, u, u, px + MR.config.tileSize / 2 - u / 2, py - u * 1.1, u, u);
    }
  };

  /* ------------------------------------------------------------------ mapa em execução */
  MR.loadMap = function (id) {
    return new Promise((resolve, reject) => {
      if (MR.data.maps[id]) return resolve(MR.data.maps[id]);
      const s = document.createElement('script');
      s.src = MR.config.mapScriptDir + '/map-' + id + '.js';
      s.onload = () => (MR.data.maps[id] ? resolve(MR.data.maps[id]) : reject(new Error('mapa ' + id + ' vazio')));
      s.onerror = () => reject(new Error('mapa ' + id + ' não encontrado'));
      document.head.appendChild(s);
    });
  };

  const G_SYNC = (sc) => { MR.G.px = sc.player.x; MR.G.py = sc.player.y; MR.G.pdir = sc.player.dir; };
  const PAGE_FIELDS = ['moveSpeed', 'moveFrequency', 'walkAnime', 'stepAnime', 'directionFix', 'through', 'priorityType'];

  MR.SceneMap = class {
    constructor() {
      MR.sceneMap = this;
      this.map = null; this.tilemap = null; this.loading = true; this.events = []; this.player = new MR.Char('player');
      this.msg = new MR.MessageBox(); this.interp = null; this.parallel = {}; this.commonAuto = {};
      this.fade = { a: 1, target: 1, speed: 1 / 24 };
      this.tint = { cur: [0, 0, 0, 0], tgt: [0, 0, 0, 0], t: 0, d: 0 };
      this.flash = null; this.shakeT = 0; this.shake = { p: 0, s: 0, d: 0 }; this.pictures = {};
      this.dispX = 0; this.dispY = 0; this.scrollTo = null; this.transfer = null; this.encCount = 0;
      this.nameShow = 0; this.waitFrames = 0; this.menu = null; this.battleReq = null;
      this.player.priority = 1;
      this.player.onStepEnd = () => this.onPlayerStepEnd();
      this.enterMap(MR.G.mapId, MR.G.px, MR.G.py, MR.G.pdir, 'none');
    }
    mapInfo() { return (MR.data.db.mapInfos || [])[MR.G.mapId] || {}; }

    enterMap(id, x, y, d, fadeType) {
      this.loading = true;
      const prevBgm = MR.audio.bgmData;
      MR.loadMap(id).then((m) => {
        this.mapData = m; MR.G.mapId = id;
        this.setupMap(m);
        this.player.setPos(x, y); if (d) this.player.dir = d;
        this.events = []; this.parallel = {};
        (m.events || []).forEach((ed) => { if (ed) { const ev = this.makeEvent(ed); this.events.push(ev); } });
        const ts = (MR.data.db.tilesets || [])[m.tilesetId] || {};
        this.tilemap = new MR.Tilemap(m, ts);
        MR.assets.whenLoaded(this.tilemap.pending()).then(() => {
          this.loading = false;
          this.syncLeader();
          this.refreshEvents(true);
          this.centerCamera(true);
          if (m.autoplayBgm) MR.audio.playBgm(m.bgm);
          if (m.autoplayBgs) MR.audio.playBgs(m.bgs);
          this.nameShow = (m.displayName && !m.disableDisplayName) ? 150 : 0;
          if (fadeType !== 'none' && fadeType !== 2) this.fade.target = 0;
          else if (fadeType === 'none') this.fade.target = 0;
          this.encCount = this.makeEncCount();
          MR.G.mapName = () => this.mapData.displayName || this.mapData.name || '';
          if (MR.ext.hooks.mapEnter) MR.ext.hooks.mapEnter.forEach((f) => f(this));
          void prevBgm;
        });
      }).catch((e) => { MR.fatal('Falha ao carregar mapa ' + id + ': ' + e.message); });
    }
    setupMap(m) {
      this.w = m.width; this.h = m.height;
      this.mapRef = m;
    }
    /* --- consultas de mapa (usadas pelos Char) */
    isValid(x, y) { return x >= 0 && y >= 0 && x < this.w && y < this.h; }
    tid(x, y, z) { return this.tilemap ? this.tilemap.id(x, y, z) : 0; }
    checkPassage(x, y, bit) {
      const tm = this.tilemap;
      for (let z = 3; z >= 0; z--) {
        const id = tm.id(x, y, z);
        if (id <= 0) continue;
        const f = tm.flag(id);
        if (f & 0x10) continue;
        if ((f & bit) === 0) return true;
        if ((f & bit) === bit) return false;
      }
      return false;
    }
    isPassable(x, y, d) { return this.checkPassage(x, y, (1 << (d / 2 - 1)) & 0x0f); }
    regionId(x, y) { return this.isValid(x, y) ? this.tid(x, y, 5) : 0; }
    isCounter(x, y) {
      for (let z = 3; z >= 0; z--) { const id = this.tid(x, y, z); if (id > 0 && (this.tilemap.flag(id) & 0x80)) return true; }
      return false;
    }
    eventsXy(x, y) { return this.events.filter((e) => !e.erased && e.x === x && e.y === y); }
    collidedWithChars(x, y, self) {
      if (self !== this.player && !this.player.through && this.player.isNormalPriority() && this.player.pos(x, y) && self.isNormalPriority()) return true;
      return this.events.some((e) => e !== self && !e.erased && !e.through && e.isNormalPriority() && e.pos(x, y));
    }
    busy() { return this.interp && this.interp.running() || this.msg.busy() || this.transfer || this.fade.a > 0.01 && this.fade.target > this.fade.a; }

    /* --- eventos */
    makeEvent(ed) {
      const ev = new MR.Char('event');
      ev.id = ed.id; ev.data = ed; ev.pageIndex = -1; ev.list = []; ev.trigger = 0; ev.starting = false;
      ev.setPos(ed.x, ed.y);
      ev.onStepEnd = () => this.onEventStepEnd(ev);
      return ev;
    }
    pageOk(ev, pg) {
      const c = pg.conditions || {}, G = MR.G;
      if (c.switch1Valid && !G.sw(c.switch1Id)) return false;
      if (c.switch2Valid && !G.sw(c.switch2Id)) return false;
      if (c.variableValid && G.v(c.variableId) < c.variableValue) return false;
      if (c.selfSwitchValid && !G.ss(G.mapId, ev.id, c.selfSwitchCh)) return false;
      if (c.itemValid && !G.numItems('item', c.itemId)) return false;
      if (c.actorValid && G.party.indexOf(c.actorId) < 0) return false;
      return true;
    }
    refreshEvents(force) {
      if (!force && !MR.G.dirty) return;
      MR.G.dirty = false;
      this.events.forEach((ev) => {
        if (ev.permErased) { ev.erased = true; return; }
        const pages = ev.data.pages || [];
        let idx = -1;
        for (let i = pages.length - 1; i >= 0; i--) if (this.pageOk(ev, pages[i])) { idx = i; break; }
        if (idx === ev.pageIndex && !force) return;
        ev.pageIndex = idx;
        ev.erased = ev.erasedFlag && idx === ev.erasedPage;
        if (idx < 0) { ev.image = { tileId: 0, characterName: '', characterIndex: 0 }; ev.list = []; ev.trigger = -1; ev.erased = false; ev.transparent = true; ev.ghost = true; return; }
        ev.ghost = false; ev.transparent = false;
        const pg = pages[idx];
        ev.image = Object.assign({ tileId: 0, characterName: '', characterIndex: 0 }, pg.image || {});
        if (ev.image.tileId > 0) ev.image.characterName = '';
        ev.dir = (pg.image && pg.image.direction) || ev.dir;
        ev.origPattern = ev.pattern = (pg.image && pg.image.pattern != null) ? pg.image.pattern : 1;
        if (MR.config.engine === 'xp' && pg.image && pg.image.pattern != null) ev.origPattern = ev.pattern = pg.image.pattern;
        ev.moveSpeed = pg.moveSpeed != null ? pg.moveSpeed : 3; ev.moveFreq = pg.moveFrequency != null ? pg.moveFrequency : 3;
        ev.walkAnime = pg.walkAnime !== false; ev.stepAnime = !!pg.stepAnime; ev.dirFix = !!pg.directionFix;
        ev.through = !!pg.through; ev.priority = pg.priorityType != null ? pg.priorityType : 1;
        if (ev.image.tileId > 0 && pg.priorityType == null) ev.priority = 0;
        ev.moveType = pg.moveType || 0; ev.trigger = pg.trigger || 0; ev.list = pg.list || [];
        ev.route = null;
        if (ev.moveType === 3 && pg.moveRoute) { ev.route = pg.moveRoute; ev.routeIdx = 0; ev.selfRoute = true; }
        ev.starting = false;
        // paralelo
        delete this.parallel[ev.id];
        if (ev.trigger === 4 && ev.list.length > 1) this.parallel[ev.id] = { interp: new MR.Interpreter(this, 1), list: ev.list, id: ev.id };
      });
    }
    startEvent(ev) {
      if (!ev || !ev.list || ev.list.length <= 1 || this.interp && this.interp.running()) return false;
      if (ev.trigger >= 0 && ev.trigger <= 2) { ev.locked = true; ev.preDir = ev.dir; ev.turnToward(this.player); ev.dashing = false; }
      this.interp = this.interp || new MR.Interpreter(this, 0);
      this.interp.setup(ev.list, ev.id);
      return true;
    }
    startCommon(list, evId) {
      this.interp = this.interp || new MR.Interpreter(this, 0);
      this.interp.setup(list, evId || 0);
    }
    onEventStepEnd(ev) {
      if (ev.trigger === 2 && this.player.pos(ev.x, ev.y) && !this.busy() && ev.isNormalPriority()) this.startEvent(ev);
    }
    onPlayerStepEnd() {
      // chegou na casa: eventos de toque “aqui” (prioridade não-normal)
      if (this.busy()) return;
      const here = this.eventsXy(this.player.x, this.player.y).filter((e) => (e.trigger === 1 || e.trigger === 2) && !e.isNormalPriority());
      for (const e of here) if (this.startEvent(e)) return;
      // encontros aleatórios
      if (!MR.G.encounterDisabled && this.mapData.encounterList && this.mapData.encounterList.length) {
        const reg = this.regionId(this.player.x, this.player.y);
        this.encCount -= (reg === 0 ? 1 : 1);
        if (this.encCount <= 0) { this.encCount = this.makeEncCount(); this.randomEncounter(); }
      }
    }
    makeEncCount() { const n = this.mapData.encounterStep || 30; return MR.u.rand(n) + MR.u.rand(n) + 1; }
    randomEncounter() {
      const reg = this.regionId(this.player.x, this.player.y);
      const list = (this.mapData.encounterList || []).filter((e) => !e.regionSet || e.regionSet.length === 0 || e.regionSet.indexOf(reg) >= 0);
      if (!list.length) return;
      let total = list.reduce((s, e) => s + e.weight, 0), r = MR.u.rand(total), pick = list[0];
      for (const e of list) { r -= e.weight; if (r < 0) { pick = e; break; } }
      this.battleReq = { troopId: pick.troopId, canEscape: true, canLose: false, cb: null };
    }
    eventById(id) {
      if (id === -1) return this.player;
      return this.events.find((e) => e.id === id) || null;
    }

    /* --- câmera */
    centerCamera(snap) {
      const tw = MR.config.tileSize, W = MR.config.screen.w, H = MR.config.screen.h;
      const wpx = this.w * tw, hpx = this.h * tw;
      let ox = this.player.rx * tw + tw / 2 - W / 2, oy = this.player.ry * tw + tw / 2 - H / 2;
      ox = wpx <= W ? -(W - wpx) / 2 : MR.u.clamp(ox, 0, wpx - W);
      oy = hpx <= H ? -(H - hpx) / 2 : MR.u.clamp(oy, 0, hpx - H);
      if (this.scrollTo) {
        const s = this.scrollTo; s.t--;
        this.camOffX = (this.camOffX || 0) + s.dx; this.camOffY = (this.camOffY || 0) + s.dy;
        if (s.t <= 0) this.scrollTo = null;
      }
      this.offX = ox + (this.camOffX || 0); this.offY = oy + (this.camOffY || 0);
      if (snap) { this.camOffX = 0; this.camOffY = 0; }
    }

    /* --- atualização */
    update() {
      MR.tick = (MR.tick || 0) + 1;
      if (this.loading) return;
      const P = this.player;
      // transição de mapa
      if (this.transfer) {
        if (this.fade.a >= 0.999 || this.transfer.fade === 2) {
          const t = this.transfer; this.transfer = null;
          this.enterMap(t.mapId, t.x, t.y, t.d, t.fade);
          return;
        }
      }
      this.fade.a += Math.sign(this.fade.target - this.fade.a) * Math.min(Math.abs(this.fade.target - this.fade.a), this.fade.speed);
      this.updateScreenFx();
      this.msg.update();
      this.refreshEvents(false);
      // intérpretes
      if (this.interp && this.interp.running()) this.interp.update();
      if (this.interp && !this.interp.running()) this.releaseEvents();
      const idle = !(this.interp && this.interp.running()) && !this.msg.busy() && !this.transfer;
      Object.keys(this.parallel).forEach((k) => {
        const par = this.parallel[k];
        if (!par.interp.running()) par.interp.setup(par.list, par.id);
        par.interp.update();
      });
      // autorun
      if (idle && !this.battleReq) {
        for (const ev of this.events) if (ev.trigger === 3 && ev.list.length > 1 && !ev.erased && !ev.ghost) { this.startEvent(ev); break; }
        if (!(this.interp && this.interp.running())) this.autoCommon();
      }
      // jogador
      if (idle && !this.battleReq && this.fade.a < 0.5) this.updatePlayerInput();
      P.update(this, this);
      this.events.forEach((ev) => this.updateEvent(ev, idle));
      if (MR.G.timer.on && MR.G.timer.frames > 0) { MR.G.timer.frames--; if (MR.G.timer.frames === 0) { MR.G.timer.on = false; MR.G.timerExpired = true; } }
      MR.G.playtime++;
      G_SYNC(this);
      this.syncLeader();
      this.centerCamera();
      if (this.nameShow > 0) this.nameShow--;
      // batalha / menu
      if (this.battleReq && !(this.interp && this.interp.running()) && !this.msg.busy()) {
        const b = this.battleReq; this.battleReq = null;
        MR.startBattle(b.troopId, b.canEscape, b.canLose, b.cb);
        return;
      }
      if (idle && IN.cancelTriggered() && !MR.G.menuDisabled && !P.isMoving() && !this.battleReq) { MR.audio.sys(1); MR.pushScene(new MR.SceneMenu()); }
    }
    // o sprite do jogador é o do primeiro membro do grupo
    syncLeader() {
      const a = MR.G.members()[0], im = this.player.image;
      if (a && (im.characterName !== a.characterName || im.characterIndex !== a.characterIndex)) {
        this.player.image = { tileId: 0, characterName: a.characterName, characterIndex: a.characterIndex };
      }
    }
    releaseEvents() { this.events.forEach((e) => { if (e.locked) { e.locked = false; if (!e.dirFix && e.preDir) e.dir = e.preDir; } }); }
    autoCommon() {
      const cs = MR.data.db.commonEvents || [];
      for (const ce of cs) if (ce && ce.trigger === 1 && MR.G.sw(ce.switchId)) { this.startCommon(ce.list, 0); return; }
      if (!this.commonPar) this.commonPar = {};
      for (const ce of cs) if (ce && ce.trigger === 2 && MR.G.sw(ce.switchId)) {
        (this.commonPar[ce.id] = this.commonPar[ce.id] || (() => { const it = new MR.Interpreter(this, 0); it.setup(ce.list, 0); return it; })()).update();
      }
    }
    updatePlayerInput() {
      const P = this.player;
      if (!P.isMoving() && !P.jump) {
        P.dashing = IN.pressed('shift') && !MR.G.flags.disableDash && !this.mapData.disableDashing;
        const d = IN.dir4();
        if (d) {
          const moved = P.moveStraight(this, d);
          if (!moved) this.touchFront(d);
        } else if (IN.okTriggered()) {
          this.triggerAction();
        }
      }
    }
    touchFront(d) {
      const x2 = this.player.x + DX[d], y2 = this.player.y + DY[d];
      for (const e of this.eventsXy(x2, y2)) if ((e.trigger === 1 || e.trigger === 2) && e.isNormalPriority() && this.startEvent(e)) return true;
      return false;
    }
    triggerAction() {
      const P = this.player;
      const here = this.eventsXy(P.x, P.y).filter((e) => e.trigger === 0 && !e.isNormalPriority());
      for (const e of here) if (this.startEvent(e)) return true;
      let x2 = P.x + DX[P.dir], y2 = P.y + DY[P.dir];
      let front = this.eventsXy(x2, y2).filter((e) => e.trigger <= 2 && e.trigger >= 0 && e.isNormalPriority());
      if (!front.length && this.isValid(x2, y2) && this.isCounter(x2, y2)) {
        x2 += DX[P.dir]; y2 += DY[P.dir];
        front = this.eventsXy(x2, y2).filter((e) => e.trigger === 0 && e.isNormalPriority());
      }
      for (const e of front) if (this.startEvent(e)) return true;
      return false;
    }
    updateEvent(ev, idle) {
      if (ev.ghost) return;
      if (!ev.locked && !(this.interp && this.interp.running() && this.interp.eventId === ev.id && false)) {
        if (!ev.isMoving() && !ev.route && ev.stopCount > 30 * (5 - ev.moveFreq) && idle && ev.moveType) {
          const rnd = [2, 4, 6, 8][MR.u.rand(4)];
          if (ev.moveType === 1) ev.moveStraight(this, MR.u.rand(2) ? ev.dir : rnd);
          else if (ev.moveType === 2) { if (MR.u.rand(5) < 4) ev.moveToward(this, this.player); else ev.moveStraight(this, rnd); }
        }
      }
      const frozen = ev.locked || (this.interp && this.interp.running() && !ev.selfRoute && !ev.route);
      if (ev.locked || (!idle && ev.moveType !== 3 && !ev.route)) { ev.update(this, this); ev.stopCount = ev.locked ? 0 : ev.stopCount; return; }
      void frozen;
      ev.update(this, this);
    }

    /* --- efeitos de tela */
    updateScreenFx() {
      const t = this.tint;
      if (t.d > 0) { t.d--; for (let i = 0; i < 4; i++) t.cur[i] += (t.tgt[i] - t.cur[i]) / (t.d + 1); }
      if (this.flash) { this.flash.t--; if (this.flash.t <= 0) this.flash = null; }
      if (this.shake.d > 0) { this.shake.d--; this.shakeT++; }
      Object.keys(this.pictures).forEach((k) => {
        const p = this.pictures[k];
        if (p.move) {
          const m = p.move; m.t--;
          const f = 1 / Math.max(1, m.t + 1);
          p.x += (m.x - p.x) * f; p.y += (m.y - p.y) * f; p.sx += (m.sx - p.sx) * f; p.sy += (m.sy - p.sy) * f; p.op += (m.op - p.op) * f;
          if (m.t <= 0) p.move = null;
        }
      });
    }
    showMapName(ctx) {
      if (this.nameShow <= 0 || !this.mapData.displayName) return;
      ctx.save(); ctx.globalAlpha = Math.min(1, this.nameShow / 30);
      const w = Math.min(MR.config.screen.w * 0.6, MR.ui.measure(ctx, this.mapData.displayName) + 80 * MR.ui.sc);
      ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fillRect(8, 8, w, MR.ui.lh() + 8);
      MR.ui.text(ctx, this.mapData.displayName, 8 + 8, 12, w - 16, 'left'); ctx.restore();
    }

    drawParallax(ctx, W, H) {
      const nm = this.mapData.parallaxName;
      if (!nm) return;
      const im = MR.assets.image('parallaxes', nm);
      if (!im.mrReady) return;
      const f = nm.charAt(0) === '!' ? 1 : 0.5;
      let ox = -this.offX * f, oy = -this.offY * f;
      if (this.mapData.parallaxLoopX) ox = ((ox % im.width) - im.width) % im.width;
      if (this.mapData.parallaxLoopY) oy = ((oy % im.height) - im.height) % im.height;
      for (let y = oy; y < H; y += im.height) {
        for (let x = ox; x < W; x += im.width) { ctx.drawImage(im, Math.round(x), Math.round(y)); if (!this.mapData.parallaxLoopX) break; }
        if (!this.mapData.parallaxLoopY) break;
      }
    }

    /* --- desenho */
    draw(ctx) {
      const W = MR.config.screen.w, H = MR.config.screen.h;
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      if (this.loading) { MR.ui.text(ctx, MR.t('loading'), 0, H / 2 - 18, W, 'center'); return; }
      let sx = 0, sy = 0;
      if (this.shake.d > 0) sx = Math.sin(this.shakeT * this.shake.s * 0.35) * this.shake.p * 2;
      ctx.save(); ctx.translate(Math.round(sx), Math.round(sy));
      this.drawParallax(ctx, W, H);
      this.tilemap.draw(ctx, this.offX, this.offY, W, H, false);
      const chars = this.events.filter((e) => !e.erased && !e.ghost).concat([this.player]);
      const tw = MR.config.tileSize;
      chars.sort((a, b) => ((a.priority === 0 ? 0 : a.priority === 2 ? 2e6 : 1e6) + a.ry * 100 + a.rx * 0.01) - ((b.priority === 0 ? 0 : b.priority === 2 ? 2e6 : 1e6) + b.ry * 100 + b.rx * 0.01));
      chars.forEach((c) => c.draw(ctx, this.offX, this.offY));
      this.tilemap.draw(ctx, this.offX, this.offY, W, H, true);
      ctx.restore();
      // tom
      const t = this.tint.cur;
      if (t[0] || t[1] || t[2]) {
        ctx.save();
        const neg = t.slice(0, 3).map((v) => 255 + Math.min(0, v)), pos = t.slice(0, 3).map((v) => Math.max(0, v));
        if (neg.some((v) => v < 255)) { ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = 'rgb(' + neg.map(Math.round).join(',') + ')'; ctx.fillRect(0, 0, W, H); }
        if (pos.some((v) => v > 0)) { ctx.globalCompositeOperation = 'lighter'; ctx.fillStyle = 'rgb(' + pos.map(Math.round).join(',') + ')'; ctx.fillRect(0, 0, W, H); }
        ctx.restore();
      }
      if (this.flash) { ctx.fillStyle = 'rgba(' + this.flash.c.slice(0, 3).join(',') + ',' + (this.flash.t / this.flash.d * (this.flash.c[3] / 255)) + ')'; ctx.fillRect(0, 0, W, H); }
      // imagens
      Object.keys(this.pictures).sort((a, b) => a - b).forEach((k) => {
        const p = this.pictures[k], im = MR.assets.image('pictures', p.name);
        if (!im.mrReady) return;
        ctx.save(); ctx.globalAlpha = MR.u.clamp(p.op / 255, 0, 1);
        const w = im.width * p.sx / 100, h = im.height * p.sy / 100;
        ctx.drawImage(im, p.origin ? p.x - w / 2 : p.x, p.origin ? p.y - h / 2 : p.y, w, h); ctx.restore();
      });
      this.showMapName(ctx);
      if (MR.G.timer.on) { const s = Math.ceil(MR.G.timer.frames / 60); MR.ui.window(ctx, W - 130 * MR.ui.sc, 6, 124 * MR.ui.sc, MR.ui.lh() + 10); MR.ui.text(ctx, Math.floor(s / 60) + ':' + MR.u.pad(s % 60, 2), W - 130 * MR.ui.sc, 11, 124 * MR.ui.sc, 'center'); }
      this.msg.draw(ctx);
      if (this.fade.a > 0.001) { ctx.fillStyle = 'rgba(0,0,0,' + MR.u.clamp(this.fade.a, 0, 1) + ')'; ctx.fillRect(0, 0, W, H); }
    }
  };
  void PAGE_FIELDS;

})();
