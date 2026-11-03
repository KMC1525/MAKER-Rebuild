"""DSL de eventos, patches, tradução, porte e jsonio — tudo sem rede (provedor mock/fakes)."""
import json
import re
from pathlib import Path

import pytest

from maker_rebuild.ai import port as portmod
from maker_rebuild.ai.client import AIClient, AIOutputError
from maker_rebuild.ai.eventdsl import Compiler, DSLError, check_list
from maker_rebuild.ai.jsonio import extract_json
from maker_rebuild.ai.patch import PatchError, apply_patch
from maker_rebuild.ai.translate import collect_units, protect, restore, tokens_ok, translate_game
from maker_rebuild.build.validate import validate_game
from maker_rebuild.config import Config


# ------------------------------------------------------------------ jsonio
@pytest.mark.parametrize("txt,expect", [
    ('{"a": 1}', {"a": 1}),
    ('Claro!\n```json\n{"a": [1,2,],}\n```\nPronto.', {"a": [1, 2]}),
    ('texto { não é json } depois {"ok": "} dentro de string"}', {"ok": "} dentro de string"}),
    ('[{"id":1}]', [{"id": 1}]),
])
def test_extract_json(txt, expect):
    assert extract_json(txt) == expect


def test_extract_json_failures():
    for bad in ("", "sem json", '{"a": '):
        with pytest.raises(ValueError):
            extract_json(bad)


# ------------------------------------------------------------------ DSL
def test_dsl_say_splits_boxes_and_choices_indent():
    c = Compiler()
    cmds = c.compile([{"say": ["1", "2", "3", "4", "5"]},
                      {"choices": ["A", "B"], "branches": [[{"set_switch": 3}], [{"if": {"switch": 3}, "then": [{"wait": 5}], "else": [{"wait": 9}]}]]}])
    codes = [(x["code"], x["indent"]) for x in cmds]
    assert codes[:2] == [(101, 0), (401, 0)] and codes.count((101, 0)) == 2            # 5 linhas → 2 caixas
    assert (102, 0) in codes and (402, 0) in codes and (404, 0) in codes
    assert (121, 1) in codes and (111, 1) in codes and (411, 1) in codes and (412, 1) in codes and (230, 2) in codes
    assert check_list(cmds + [{"code": 0, "indent": 0, "parameters": []}]) == []


def test_dsl_refs_battle_shop_and_errors():
    c = Compiler(lambda v: {"x": 7}[v[1:]] if isinstance(v, str) and v.startswith("@") else v)
    cmds = c.compile([{"battle": "@x", "win": [{"say": ["ok"]}], "lose": [], "can_lose": True, "can_escape": False},
                      {"shop": [["item", 1], ["weapon", 2, 500]]}, {"give_item": "@x", "n": -2}])
    b = cmds[0]
    assert b["code"] == 301 and b["parameters"][:2] == [0, 7]
    assert [x["code"] for x in cmds if x["code"] in (601, 602, 603, 604)] == [601, 603, 604]
    shop = [x for x in cmds if x["code"] in (302, 605)]
    assert shop[0]["parameters"][:4] == [0, 1, 0, 0] and shop[1]["parameters"] == [1, 2, 1, 500]
    assert cmds[-1]["parameters"] == [7, 1, 0, 2]                                         # n<0 → remover
    with pytest.raises(DSLError):
        c.compile([{"nao_existe": 1}])


def test_check_list_detects_bad_indent():
    bad = [{"code": 101, "indent": 0, "parameters": []}, {"code": 401, "indent": 3, "parameters": []}, {"code": 0, "indent": 0, "parameters": []}]
    assert check_list(bad)


# ------------------------------------------------------------------ patch
def _patch():
    return {"summary": "x",
            "system": {"switches": [{"name": "Falou", "ref": "talked"}]},
            "db": {"items": {"add": [{"ref": "elixir", "name": "Elixir", "price": 300, "effects": [{"code": 11, "dataId": 0, "value1": 0, "value2": 400}]}],
                             "update": [{"id": 1, "set": {"price": 60}}]},
                   "commonEvents": {"add": [{"name": "CE", "script": [{"say": ["oi"]}]}]}},
            "maps": {"add": [{"ref": "cave", "name": "Caverna", "width": 10, "height": 8, "tilesetId": 1, "fill": {"z0": 2816},
                              "rects": [{"x": 0, "y": 0, "w": 10, "h": 1, "z": 1, "id": 1}],
                              "events": [{"name": "Saída", "x": 5, "y": 6, "pages": [{"trigger": "touch", "priority": "below",
                                                                                      "script": [{"transfer": {"map": 1, "x": 3, "y": 3}}]}]}]}],
                     "update": [{"id": 1, "events": {"add": [{"name": "Guia", "x": 2, "y": 2, "pages": [{
                         "image": {"characterName": "People1", "characterIndex": 1}, "trigger": "action",
                         "script": [{"say": ["Tome isto"]}, {"give_item": "@elixir"}, {"set_switch": "@talked"},
                                    {"transfer": {"map": "@cave", "x": 5, "y": 5}}]}]}]}}]},
            "assets": [{"category": "characters", "name": "Guia2", "note": "sprite do guia"}],
            "files": [{"path": "code/js/ext/hello.js", "content": "MR.ext.modules.hello = {};"}]}


def test_apply_patch_end_to_end(built):
    res = apply_patch(built, _patch())
    assert res.added["items"] == 1 and res.added["maps"] == 1 and res.added["events"] == 2 and res.updated["items"] == 1
    assert built.db["items"][2]["name"] == "Elixir" and built.db["items"][1]["price"] == 60
    cave_id = res.refs["cave"]
    assert cave_id == 3 and built.db["mapInfos"][3]["name"] == "Caverna" and len(built.maps[3]["data"]) == 10 * 8 * 6
    guia = built.maps[1]["events"][-1]
    tr = [c for c in guia["pages"][0]["list"] if c["code"] == 201][0]
    assert tr["parameters"][1] == 3                                         # @cave resolvido
    assert (built.root / "code/js/ext/hello.js").exists() and res.files == ["code/js/ext/hello.js"]
    assert (built.root / "assets/sprites/characters/Guia2.png").read_bytes().startswith(b"\x89PNG") and res.placeholders
    built.save()
    assert "code/js/ext/hello.js" in (built.root / "Game.html").read_text()
    assert validate_game(built)["ok"]


@pytest.mark.parametrize("mutate,msg", [
    (lambda p: p["maps"]["update"][0]["events"]["add"][0]["pages"][0]["script"].append({"give_item": 99}), "id 99"),
    (lambda p: p["files"].append({"path": "../x.js", "content": ""}), "inseguro"),
    (lambda p: p["files"].append({"path": "code/js/mr-core.js", "content": "x"}), "não permitido"),
    (lambda p: p["files"].__setitem__(0, {"path": "code/js/ext/bad.js", "content": "function ( {"}), "JS inválido"),
    (lambda p: p["db"]["items"]["update"].append({"id": 77, "set": {}}), "id inexistente"),
    (lambda p: p["maps"]["add"][0].__setitem__("tilesetId", 9), "tilesetId"),
    (lambda p: p["maps"]["update"][0]["events"]["add"][0]["pages"][0]["script"].append({"set_switch": "@fantasma"}), "referência desconhecida"),
])
def test_patch_rejections_leave_game_untouched(built, mutate, msg):
    import copy
    before = (copy.deepcopy(built.db), copy.deepcopy(built.maps))
    p = _patch()
    mutate(p)
    with pytest.raises(PatchError, match=msg):
        apply_patch(built, p)
    assert (built.db, built.maps) == before
    assert not (built.root / "code/js/ext/hello.js").exists()


# ------------------------------------------------------------------ tradução
def test_protect_restore_tokens():
    s = "Olá \\C[2]\\N[1]\\C[0]! Você tem \\V[3] \\G.\\| \\{grande\\}"
    p, toks = protect(s)
    assert "\\" not in p and restore(p, toks) == s and tokens_ok(p, p, len(toks))
    assert not tokens_ok(p, p.replace("<<1>>", ""), len(toks))


def test_translate_game_with_mock_changes_line_count(built):
    # um diálogo de 2 linhas vira 3 (a tradução pode ter outro nº de linhas)
    class Fake(AIClient):
        def complete(self, task, user, **kw):
            items = json.loads(user.split("JSON:\n", 1)[1])
            return json.dumps({"translations": [{"id": i["id"], "text": "EN " + i["text"] + ("\nextra" if "poção" in i["text"] else "")} for i in items]})

    ai = Fake(Config(provider="mock"), quiet=True)
    rep = translate_game(ai, built, "en")
    assert rep.translated == rep.units and not rep.failed
    lst = built.maps[1]["events"][1]["pages"][0]["list"]
    texts = [c["parameters"][0] for c in lst if c["code"] == 401]
    assert texts[0].startswith("EN Olá, \\C[2]\\N[1]\\C[0]!") and "extra" in " ".join(texts)
    # listas continuam consistentes (101 antes de 401s, termina em 0)
    assert check_list(lst) == []
    assert built.config["lang"] == "en" and built.config["ui"]["newGame"] == "New Game"


def test_translate_retries_when_control_codes_are_lost(built):
    calls = {"n": 0}

    class Lossy(AIClient):
        def complete(self, task, user, **kw):
            calls["n"] += 1
            items = json.loads(user.split("JSON:\n", 1)[1])
            # perde os marcadores quando o lote tem mais de 1 item → força o retry individual
            return json.dumps({"translations": [{"id": i["id"], "text": "T " + (re.sub(r"<<\d+>>", "", i["text"]) if len(items) > 1 else i["text"])} for i in items]})

    rep = translate_game(Lossy(Config(provider="mock"), quiet=True), built, "en")
    assert calls["n"] > 1 and rep.translated > 0
    assert "\\N[1]" in " ".join(c["parameters"][0] for c in built.maps[1]["events"][1]["pages"][0]["list"] if c["code"] == 401)


# ------------------------------------------------------------------ porte Ruby → JS
@pytest.mark.parametrize("rb,js", [
    ("$game_switches[3] = true", "$gameSwitches.setValue(3, true);"),
    ("$game_variables[2] += 1", "$gameVariables.setValue(2, $gameVariables.value(2) + (1));"),
    ("$game_variables[5] = $game_variables[1] * 2", "$gameVariables.setValue(5, $gameVariables.value(1) * 2);"),
    ("$game_party.gain_gold(100)", "$gameParty.gainGold(100);"),
    ("$game_party.lose_item($data_items[4], 2)", "$gameParty.gainItem($dataItems[4], -2);"),
    ('$game_self_switches[[@map_id, @event_id, "A"]] = true', '$gameSelfSwitches.setValue([$gameMap.mapId(), this._eventId, "A"], true);'),
])
def test_ruby_simple_port(rb, js):
    assert portmod.port_line(rb) == js


def test_ruby_port_refuses_unknown_code():
    assert portmod.port_ruby_simple("SceneManager.call(Scene_Custom)") is None
    assert portmod.port_ruby_simple("$game_variables[1] = foo(3)") is None


def test_port_event_scripts_mixed_deterministic_and_ai(tmp_path, vxa_src):
    from maker_rebuild.build.builder import build_game
    from maker_rebuild.build.builtgame import BuiltGame
    from maker_rebuild.project import open_project
    p = open_project(str(vxa_src))
    g = BuiltGame(build_game(p, tmp_path / "o"))
    g.scripts, g.plugin_sources = p.scripts, {}

    class FakeAI(AIClient):
        def complete(self, task, user, **kw):
            items = json.loads(user.split("ENTRADA:\n", 1)[1])
            return json.dumps({"ports": [{"id": i["id"], "js": "MR.G.setSw(9, true);\n// " + i["ruby"][:10]} for i in items]})

    rep = portmod.PortReport()
    portmod.port_event_scripts(FakeAI(Config(provider="mock"), quiet=True), g, rep)
    assert rep.ruby_groups == 2 and rep.deterministic == 1 and rep.ai == 1 and not rep.failed
    lst = g.maps[1]["events"][1]["pages"][0]["list"]
    scripts = [c for c in lst if c["code"] in (355, 655)]
    assert not any(c.get("lang") == "ruby" for c in scripts)
    assert "$gameVariables.setValue(2" in scripts[0]["parameters"][0] and "MR.G.setSw(9" in scripts[-1]["parameters"][0]
    assert validate_game(g, check_syntax=False)["commands"]["ruby_scripts"] == 0


def test_port_rejects_invalid_js_from_ai(tmp_path, vxa_src):
    from maker_rebuild.build.builder import build_game
    from maker_rebuild.build.builtgame import BuiltGame
    from maker_rebuild.project import open_project
    g = BuiltGame(build_game(open_project(str(vxa_src)), tmp_path / "o"))

    class BadAI(AIClient):
        def complete(self, task, user, **kw):
            items = json.loads(user.split("ENTRADA:\n", 1)[1])
            return json.dumps({"ports": [{"id": i["id"], "js": "function ( {"} for i in items]})

    rep = portmod.PortReport()
    portmod.port_event_scripts(BadAI(Config(provider="mock"), quiet=True), g, rep)
    assert rep.failed and rep.ai == 0
    assert validate_game(g, check_syntax=False)["commands"]["ruby_scripts"] >= 1       # continua sinalizado


# ------------------------------------------------------------------ cliente
def test_ai_client_repairs_json_once():
    seq = iter(["isto não é json", '{"ok": true}'])

    class Flaky(AIClient):
        def complete(self, task, user, **kw):
            return next(seq)

    assert Flaky(Config(provider="mock"), quiet=True).ask_json("plan", "x") == {"ok": True}


def test_ai_client_gives_up_with_clear_error():
    class Broken(AIClient):
        def complete(self, task, user, **kw):
            return "nada"

    with pytest.raises(AIOutputError):
        Broken(Config(provider="mock"), quiet=True).ask_json("plan", "x")


# ------------------------------------------------------------------ "perguntar antes de assumir"
def test_clarify_asks_critical_questions_interactively(built):
    from maker_rebuild.ai import jobs

    class Asker(AIClient):
        def complete(self, task, user, **kw):
            return json.dumps({"ready": False, "questions": ["Qual idioma de destino?", "Manter nomes próprios?"], "assumptions": ["tom fiel"]})

    asked = []
    out = jobs.clarify(Asker(Config(provider="mock"), quiet=True), built, "traduza", True, ask=lambda q, d="": asked.append(q) or "inglês")
    assert asked == ["Qual idioma de destino?", "Manter nomes próprios?"]
    assert "R: inglês" in out and "tom fiel" in out and out.startswith("traduza")


def test_clarify_non_interactive_uses_assumptions_without_blocking(built, capsys):
    from maker_rebuild.ai import jobs

    class Asker(AIClient):
        def complete(self, task, user, **kw):
            return json.dumps({"ready": False, "questions": ["Qual idioma?"], "assumptions": ["inglês"]})

    out = jobs.clarify(Asker(Config(provider="mock"), quiet=True), built, "traduza", False)
    assert "SUPOSIÇÕES" in out and "inglês" in out
