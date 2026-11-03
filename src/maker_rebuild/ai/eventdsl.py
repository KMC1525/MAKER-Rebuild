"""DSL de eventos → comandos MV com indentação/marcadores corretos.

A IA descreve *o que* acontece (``{"say": [...]}``, ``{"if": ...}``); este módulo gera a lista de comandos
do RPG Maker (101/401, 111/411/412, 102/402/404 ...), eliminando a classe de erros de indentação e de
códigos de continuação que LLMs cometem ao escrever o JSON bruto.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class DSLError(ValueError):
    pass


def cmd(code: int, indent: int, *params: Any) -> Dict[str, Any]:
    return {"code": code, "indent": indent, "parameters": list(params)}


OPS = {"==": 0, ">=": 1, "<=": 2, ">": 3, "<": 4, "!=": 5}
VAR_OPS = {"set": 0, "add": 1, "sub": 2, "mul": 3, "div": 4, "mod": 5}
POS = {"top": 0, "middle": 1, "bottom": 2}
BG = {"window": 0, "dim": 1, "none": 2, "transparent": 2}
FADE = {"black": 0, "white": 1, "none": 2}
KIND = {"item": 0, "weapon": 1, "armor": 2}


class Compiler:
    def __init__(self, resolve: Optional[Callable[[Any], Any]] = None):
        self.resolve = resolve or (lambda v: v)

    def r(self, v: Any) -> Any:
        return self.resolve(v)

    # ----------------------------------------------------------------- API
    def compile(self, steps: List[Any], indent: int = 0) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for st in steps or []:
            if not isinstance(st, dict) or not st:
                raise DSLError(f"passo inválido: {st!r}")
            out += self.step(st, indent)
        return out

    def block(self, steps: Optional[List[Any]], indent: int) -> List[Dict[str, Any]]:
        """Corpo de um ramo: comandos em ``indent+1`` terminados por um 0 do mesmo nível."""
        return self.compile(steps or [], indent + 1) + [cmd(0, indent + 1)]

    # ----------------------------------------------------------------- passos
    def step(self, s: Dict[str, Any], n: int) -> List[Dict[str, Any]]:
        k = next(iter(s))
        h = getattr(self, "s_" + k, None)
        if h is None:
            for alt in s:
                h = getattr(self, "s_" + alt, None)
                if h:
                    k = alt
                    break
        if h is None:
            raise DSLError(f"passo desconhecido: {list(s)}")
        return h(s, n)

    def s_say(self, s, n):
        lines = s["say"] if isinstance(s["say"], list) else str(s["say"]).split("\n")
        face = s.get("face") or ["", 0]
        out: List[Dict[str, Any]] = []
        for i in range(0, max(1, len(lines)), 4):
            out.append(cmd(101, n, face[0], face[1] if len(face) > 1 else 0, BG.get(s.get("bg", "window"), 0),
                           POS.get(s.get("pos", "bottom"), 2)))
            out += [cmd(401, n, str(t)) for t in lines[i:i + 4]]
        return out

    def s_choices(self, s, n):
        ch = [str(c) for c in s["choices"]]
        br = s.get("branches") or []
        cancel = s.get("cancel", "disallow")
        ct = -1 if cancel == "disallow" else len(ch) if cancel == "branch" else int(cancel)
        out = [cmd(102, n, ch, ct, 0, POS.get(s.get("pos", "bottom"), 2), BG.get(s.get("bg", "window"), 0))]
        for i, name in enumerate(ch):
            out.append(cmd(402, n, i, name))
            out += self.block(br[i] if i < len(br) else [], n)
        if cancel == "branch":
            out.append(cmd(403, n, len(ch), None))
            out += self.block(s.get("cancel_branch"), n)
        out.append(cmd(404, n))
        return out

    def cond(self, c: Dict[str, Any]) -> List[Any]:
        if "switch" in c:
            return [0, self.r(c["switch"]), 0 if c.get("is", True) else 1]
        if "variable" in c:
            vid, op, val = c["variable"]
            return [1, self.r(vid), 0, self.r(val), OPS[op]]
        if "self" in c:
            return [2, c["self"], 0 if c.get("is", True) else 1]
        if "gold" in c:
            return [7, self.r(c["gold"]), 0]
        if "item" in c:
            return [8, self.r(c["item"])]
        if "actor" in c:
            return [4, self.r(c["actor"]), 0]
        if "script" in c:
            return [12, str(c["script"])]
        raise DSLError(f"condição desconhecida: {c}")

    def s_if(self, s, n):
        out = [cmd(111, n, *self.cond(s["if"]))]
        out += self.block(s.get("then"), n)
        if s.get("else") is not None:
            out.append(cmd(411, n))
            out += self.block(s["else"], n)
        out.append(cmd(412, n))
        return out

    def s_loop(self, s, n):
        return [cmd(112, n)] + self.block(s["loop"], n) + [cmd(413, n)]

    def s_break(self, s, n):
        return [cmd(113, n)]

    def s_exit(self, s, n):
        return [cmd(115, n)]

    def s_label(self, s, n):
        return [cmd(118, n, str(s["label"]))]

    def s_goto(self, s, n):
        return [cmd(119, n, str(s["goto"]))]

    def s_set_switch(self, s, n):
        i = self.r(s["set_switch"])
        return [cmd(121, n, i, i, 0 if s.get("to", True) else 1)]

    def s_self_switch(self, s, n):
        return [cmd(123, n, s["self_switch"], 0 if s.get("to", True) else 1)]

    def s_set_var(self, s, n):
        i, op = self.r(s["set_var"]), VAR_OPS[s.get("op", "set")]
        if "random" in s:
            return [cmd(122, n, i, i, op, 2, s["random"][0], s["random"][1])]
        if "from_var" in s:
            return [cmd(122, n, i, i, op, 1, self.r(s["from_var"]))]
        return [cmd(122, n, i, i, op, 0, self.r(s["value"]))]

    def _give(self, code, key, s, n):
        amt = int(s.get("n", 1))
        extra = [False] if code in (127, 128) else []
        return [cmd(code, n, self.r(s[key]), 0 if amt >= 0 else 1, 0, abs(amt), *extra)]

    def s_give_item(self, s, n):
        return self._give(126, "give_item", s, n)

    def s_give_weapon(self, s, n):
        return self._give(127, "give_weapon", s, n)

    def s_give_armor(self, s, n):
        return self._give(128, "give_armor", s, n)

    def s_give_gold(self, s, n):
        v = int(s["give_gold"])
        return [cmd(125, n, 0 if v >= 0 else 1, 0, abs(v))]

    def s_party_add(self, s, n):
        return [cmd(129, n, self.r(s["party_add"]), 0, True)]

    def s_party_remove(self, s, n):
        return [cmd(129, n, self.r(s["party_remove"]), 1, False)]

    def s_transfer(self, s, n):
        t = s["transfer"]
        return [cmd(201, n, 0, self.r(t["map"]), t.get("x", 0), t.get("y", 0), t.get("dir", 0), FADE.get(t.get("fade", "black"), 0))]

    def s_battle(self, s, n):
        ce, cl = bool(s.get("can_escape", True)), bool(s.get("can_lose", False))
        out = [cmd(301, n, 0, self.r(s["battle"]), ce, cl)]
        if any(k in s for k in ("win", "escape", "lose")):
            out += [cmd(601, n)] + self.block(s.get("win"), n)
            if ce:
                out += [cmd(602, n)] + self.block(s.get("escape"), n)
            if cl:
                out += [cmd(603, n)] + self.block(s.get("lose"), n)
            out.append(cmd(604, n))
        return out

    def s_shop(self, s, n):
        goods = s["shop"]
        rows = []
        for g in goods:
            kind = KIND[g[0]]
            price = g[2] if len(g) > 2 else 0
            rows.append([kind, self.r(g[1]), 1 if len(g) > 2 else 0, price])
        out = [cmd(302, n, *rows[0], bool(s.get("buy_only", False)))]
        out += [cmd(605, n, *r) for r in rows[1:]]
        return out

    def _audio(self, code, key, s, n, default_vol=90):
        a = s[key]
        if isinstance(a, str):
            a = {"name": a}
        return [cmd(code, n, {"name": a.get("name", ""), "pan": 0, "pitch": a.get("pitch", 100), "volume": a.get("volume", default_vol)})]

    def s_bgm(self, s, n):
        return self._audio(241, "bgm", s, n)

    def s_bgs(self, s, n):
        return self._audio(245, "bgs", s, n)

    def s_me(self, s, n):
        return self._audio(249, "me", s, n)

    def s_se(self, s, n):
        return self._audio(250, "se", s, n)

    def s_fade_bgm(self, s, n):
        return [cmd(242, n, int(s["fade_bgm"]))]

    def s_wait(self, s, n):
        return [cmd(230, n, int(s["wait"]))]

    def s_fade_out(self, s, n):
        return [cmd(221, n)]

    def s_fade_in(self, s, n):
        return [cmd(222, n)]

    def s_tint(self, s, n):
        return [cmd(223, n, list(s["tint"]), int(s.get("frames", 60)), True)]

    def s_flash(self, s, n):
        return [cmd(224, n, list(s["flash"]), int(s.get("frames", 30)), True)]

    def s_shake(self, s, n):
        p = s["shake"]
        return [cmd(225, n, p[0], p[1], p[2], True)]

    def s_picture(self, s, n):
        return [cmd(231, n, int(s["picture"]), s["name"], int(s.get("origin", 0)), 0, s.get("x", 0), s.get("y", 0),
                    s.get("zoom_x", 100), s.get("zoom_y", 100), s.get("opacity", 255), 0)]

    def s_erase_picture(self, s, n):
        return [cmd(235, n, int(s["erase_picture"]))]

    def s_common_event(self, s, n):
        return [cmd(117, n, self.r(s["common_event"]))]

    def s_erase_event(self, s, n):
        return [cmd(214, n)]

    def s_move_route(self, s, n):
        m = s["move_route"]
        route = [c if isinstance(c, dict) else {"code": int(c), "parameters": []} for c in m.get("route", [])]
        route.append({"code": 0, "parameters": []})
        return [cmd(205, n, m.get("target", 0), {"list": route, "repeat": False, "skippable": False, "wait": bool(m.get("wait", True))})]

    def s_change_hp(self, s, n):
        v = int(s["change_hp"])
        return [cmd(311, n, 0, self.r(s.get("actor", 0)), 0 if v >= 0 else 1, 0, abs(v), False)]

    def s_recover_all(self, s, n):
        return [cmd(314, n, 0, self.r(s.get("actor", 0)))]

    def s_exp(self, s, n):
        v = int(s["exp"])
        return [cmd(315, n, 0, self.r(s.get("actor", 0)), 0 if v >= 0 else 1, 0, abs(v), True)]

    def s_learn_skill(self, s, n):
        return [cmd(318, n, 0, self.r(s.get("actor", 0)), 0, self.r(s["learn_skill"]))]

    def s_menu_access(self, s, n):
        return [cmd(135, n, 0 if s["menu_access"] else 1)]

    def s_save_access(self, s, n):
        return [cmd(134, n, 0 if s["save_access"] else 1)]

    def s_encounters(self, s, n):
        return [cmd(136, n, 0 if s["encounters"] else 1)]

    def s_open_menu(self, s, n):
        return [cmd(351, n)]

    def s_game_over(self, s, n):
        return [cmd(353, n)]

    def s_title(self, s, n):
        return [cmd(354, n)]

    def s_script(self, s, n):
        lines = str(s["script"]).split("\n")
        return [cmd(355, n, lines[0])] + [cmd(655, n, t) for t in lines[1:]]

    def s_comment(self, s, n):
        return [cmd(108, n, str(s["comment"]))]

    def s_raw(self, s, n):
        r = s["raw"]
        return [cmd(int(r["code"]), n, *r.get("parameters", []))]


def check_list(cmds: List[Dict[str, Any]]) -> List[str]:
    """Verifica a consistência estrutural de uma lista de comandos (devolve mensagens de erro)."""
    errs: List[str] = []
    if not cmds:
        return ["lista de comandos vazia (precisa terminar com código 0)"]
    prev_indent = 0
    for i, c in enumerate(cmds):
        if not isinstance(c, dict) or not isinstance(c.get("code"), int) or not isinstance(c.get("parameters", []), list):
            errs.append(f"comando {i} malformado")
            continue
        ind = c.get("indent", 0)
        if not isinstance(ind, int) or ind < 0 or ind > prev_indent + 1:
            errs.append(f"comando {i} (código {c['code']}): indentação {ind} inválida (anterior {prev_indent})")
        prev_indent = ind
    if cmds[-1].get("code") != 0:
        errs.append("a lista deve terminar com o comando 0")
    return errs
