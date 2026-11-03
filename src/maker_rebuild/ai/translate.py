"""Tradução do jogo: extrai unidades de texto, protege códigos de controle, traduz em lotes e reaplica."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import ui
from ..build import commands as cmdmod
from .client import AIClient, AIOutputError
from . import prompts

# códigos de controle do RPG Maker que NÃO podem ser alterados pela tradução
CTRL = re.compile(r"\\[A-Za-z]+\[\d+\]|\\[A-Za-z]+(?![A-Za-z\[])|\\[{}.|!><^$\\]|\x1b[A-Za-z]\[\d+\]")


def protect(text: str) -> Tuple[str, List[str]]:
    toks: List[str] = []

    def rep(m: "re.Match[str]") -> str:
        toks.append(m.group(0))
        return f"<<{len(toks) - 1}>>"

    return CTRL.sub(rep, text), toks


def restore(text: str, toks: List[str]) -> str:
    return re.sub(r"<<(\d+)>>", lambda m: toks[int(m.group(1))] if int(m.group(1)) < len(toks) else m.group(0), text)


def tokens_ok(src: str, dst: str, n: int) -> bool:
    found = re.findall(r"<<(\d+)>>", dst)
    return sorted(found, key=int) == [str(i) for i in range(n)] and len(found) == n


@dataclass
class Unit:
    uid: str
    text: str                      # texto original (com códigos de controle)
    ctx: str
    setter: Callable[[str], None]
    kind: str = "text"


def collect_units(game: Any, include_db: bool = True) -> List[Unit]:
    units: List[Unit] = []
    db, maps = game.db, game.maps

    def add(uid: str, text: Any, ctx: str, setter: Callable[[str], None], kind: str = "text") -> None:
        if isinstance(text, str) and text.strip():
            units.append(Unit(uid, text, ctx, setter, kind))

    # --- diálogos / escolhas / texto rolante
    for origin, cont, key in cmdmod.iter_lists(db, maps):
        lst = cont.get(key) or []
        mid = origin.split("/")[0]
        i = 0
        groups: List[Tuple[int, int, str]] = []   # (índice do cabeçalho, nº de linhas, tipo)
        while i < len(lst):
            c = lst[i]
            if c.get("code") in (101, 105):
                cont_code = 401 if c["code"] == 101 else 405
                j = i + 1
                while j < len(lst) and lst[j].get("code") == cont_code:
                    j += 1
                if j > i + 1:
                    groups.append((i, j - i - 1, cont_code))
                i = j
                continue
            i += 1
        # aplica de trás pra frente para não invalidar índices ao mudar o nº de linhas
        for hi, n, cont_code in groups:
            lines = [str(lst[hi + 1 + k]["parameters"][0]) for k in range(n)]
            speaker = ""
            if lst[hi]["code"] == 101 and lst[hi]["parameters"] and lst[hi]["parameters"][0]:
                speaker = f" / {lst[hi]['parameters'][0]}#{lst[hi]['parameters'][1]}"
            indent = lst[hi].get("indent", 0)

            def setter(new: str, lst=lst, hi=hi, n=n, indent=indent, cont_code=cont_code) -> None:
                new_lines = new.split("\n") if new else [""]
                lst[hi + 1:hi + 1 + n] = [{"code": cont_code, "indent": indent, "parameters": [t]} for t in new_lines]
                # índices seguintes mudam: marcamos para reconstruir em apply_all
            add(f"{origin}#{hi}", "\n".join(lines), f"{mid}{speaker}", _Deferred(lst, hi, n, indent, cont_code, setter), "dialog")
        for ci, c in enumerate(lst):
            if c.get("code") == 102 and c.get("parameters"):
                for k, opt in enumerate(c["parameters"][0]):
                    add(f"{origin}#c{ci}.{k}", opt, f"{mid} / escolha",
                        (lambda new, c=c, k=k: c["parameters"][0].__setitem__(k, new)), "choice")
    # sincroniza o nome dos ramos 402 com as escolhas traduzidas (apenas editor)
    # --- banco de dados
    if include_db:
        fields = {"actors": ("name", "nickname", "profile"), "classes": ("name",), "skills": ("name", "description", "message1", "message2"),
                  "items": ("name", "description"), "weapons": ("name", "description"), "armors": ("name", "description"),
                  "enemies": ("name",), "states": ("name", "message1", "message2", "message3", "message4")}
        for kind, flds in fields.items():
            for e in db.get(kind) or []:
                if not e:
                    continue
                for f in flds:
                    add(f"db.{kind}.{e['id']}.{f}", e.get(f), f"{kind}/{e.get('name', '')}", (lambda new, e=e, f=f: e.__setitem__(f, new)), "db")
        s = db.get("system") or {}
        add("sys.currency", s.get("currencyUnit"), "moeda", lambda new: s.__setitem__("currencyUnit", new), "db")
        add("sys.title", s.get("gameTitle"), "título do jogo", lambda new: (s.__setitem__("gameTitle", new), setattr(game, "title", new)), "db")
        terms = s.get("terms") or {}
        for tk in ("basic", "commands", "params", "etypes"):
            arr = terms.get(tk)
            if isinstance(arr, list):
                for i, t in enumerate(arr):
                    add(f"term.{tk}.{i}", t, f"termo {tk}", (lambda new, arr=arr, i=i: arr.__setitem__(i, new)), "term")
        msgs = terms.get("messages")
        if isinstance(msgs, dict):
            for k, t in msgs.items():
                add(f"term.msg.{k}", t, "mensagem do sistema", (lambda new, msgs=msgs, k=k: msgs.__setitem__(k, new)), "term")
        for mid, m in maps.items():
            add(f"map.{mid}.display", m.get("displayName"), "nome do mapa", (lambda new, m=m: m.__setitem__("displayName", new)), "db")
    return units


class _Deferred:
    """Setter de diálogo: registra a troca para ser aplicada de uma vez, de trás para frente."""

    def __init__(self, lst: list, hi: int, n: int, indent: int, code: int, fn: Callable[[str], None]):
        self.lst, self.hi, self.n, self.indent, self.code, self.fn = lst, hi, n, indent, code, fn

    def __call__(self, new: str) -> None:
        self.fn(new)


def apply_all(units: List[Unit], results: Dict[str, str]) -> int:
    """Aplica traduções; diálogos de cada lista são tratados do fim para o começo (muda o nº de linhas)."""
    done = 0
    dialogs = [u for u in units if isinstance(u.setter, _Deferred) and u.uid in results]
    others = [u for u in units if not isinstance(u.setter, _Deferred) and u.uid in results]
    for u in others:
        u.setter(results[u.uid])
        done += 1
    dialogs.sort(key=lambda u: (id(u.setter.lst), -u.setter.hi))
    for u in dialogs:
        u.setter(results[u.uid])
        done += 1
    return done


# ---------------------------------------------------------------------------------------------

@dataclass
class TranslateReport:
    units: int = 0
    unique: int = 0
    translated: int = 0
    failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def load_glossary(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    import csv
    out: Dict[str, str] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and row[0].strip() and not row[0].startswith("#"):
                out[row[0].strip()] = row[1].strip()
    return out


def _batches(items: List[Tuple[str, str, str]], max_chars: int, max_items: int = 40) -> List[List[Tuple[str, str, str]]]:
    out, cur, size = [], [], 0
    for it in items:
        if cur and (size + len(it[1]) > max_chars or len(cur) >= max_items):
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += len(it[1]) + 40
    if cur:
        out.append(cur)
    return out


def translate_game(ai: AIClient, game: Any, target: str, source: str = "", tone: str = "", glossary: Optional[Dict[str, str]] = None,
                   include_db: bool = True, progress: Optional[Callable[[int, int, str], None]] = None) -> TranslateReport:
    rep = TranslateReport()
    units = collect_units(game, include_db)
    rep.units = len(units)
    # deduplica por (texto, tipo de contexto): mesma frase → uma tradução
    uniq: Dict[str, Tuple[str, str, List[Unit]]] = {}
    for u in units:
        k = u.text
        if k not in uniq:
            prot, toks = protect(u.text)
            uniq[k] = (f"t{len(uniq)}", prot, [])
        uniq[k][2].append(u)
    rep.unique = len(uniq)
    items = [(tid, prot, units_[0].ctx) for (tid, prot, units_) in uniq.values()]
    toks_of = {tid: protect(text)[1] for text, (tid, _p, _u) in uniq.items()}
    original_of = {tid: text for text, (tid, _p, _u) in uniq.items()}
    ids_units = {tid: us for (tid, _p, us) in uniq.values()}
    gl = "\n".join(f"{a} = {b}" for a, b in (glossary or {}).items())
    header = f"TARGET_LANG={target}\nSOURCE_LANG={source or 'auto'}\nTONE={tone or 'fiel ao original'}\n" + (f"GLOSSARY:\n{gl}\n" if gl else "")
    translated: Dict[str, str] = {}

    def run(batch: List[Tuple[str, str, str]], depth: int = 0) -> None:
        payload = json.dumps([{"id": i, "ctx": c, "text": t} for i, t, c in batch], ensure_ascii=False)
        try:
            data = ai.ask_json("translate", header + "JSON:\n" + payload, extra_system=prompts.TRANSLATE_TASK, cache=True,
                               desc=f"traduzindo {len(batch)} textos", with_api=False, temperature=0.3)
        except AIOutputError as e:
            if len(batch) > 1:
                mid = len(batch) // 2
                run(batch[:mid], depth + 1)
                run(batch[mid:], depth + 1)
                return
            rep.failed.append(batch[0][0])
            rep.warnings.append(f"texto não traduzido ({e})")
            return
        got = {t.get("id"): t.get("text") for t in (data.get("translations") if isinstance(data, dict) else data) or []
               if isinstance(t, dict)}
        retry: List[Tuple[str, str, str]] = []
        for tid, prot, ctx in batch:
            new = got.get(tid)
            ntok = len(toks_of[tid])
            if isinstance(new, str) and new.strip() and tokens_ok(prot, new, ntok):
                translated[tid] = restore(new, toks_of[tid])
            else:
                retry.append((tid, prot, ctx))
        if retry:
            if len(retry) == len(batch) and len(batch) == 1:
                rep.failed.append(batch[0][0])
                rep.warnings.append(f"códigos de controle alterados na tradução; mantido original: {original_of[batch[0][0]][:50]!r}")
            elif depth < 3:
                for r in retry:
                    run([r], depth + 3)
            else:
                rep.failed.extend(r[0] for r in retry)

    batches = _batches(items, 5000)
    for bi, b in enumerate(batches, 1):
        run(b)
        if progress:
            progress(bi, len(batches), "traduzindo")
    results: Dict[str, str] = {}
    for tid, new in translated.items():
        for u in ids_units[tid]:
            results[u.uid] = new
    rep.translated = apply_all(units, results)
    # atualiza idioma da UI
    lang = target
    if hasattr(game, "config"):
        from ..build.i18n import ui_strings
        game.config["lang"] = lang
        game.config["ui"] = ui_strings(lang)
    return rep
