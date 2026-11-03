# Contrato do runtime MAKER-Rebuild (para a IA)

O jogo entregue roda num runtime Canvas 2D próprio. Os dados seguem a nomenclatura do RPG Maker MV
(`actors`, `classes`, `skills`, `items`, `weapons`, `armors`, `enemies`, `troops`, `states`, `commonEvents`, `tilesets`,
`system`, `mapInfos`; mapas separados). Ids começam em 1 (índice 0 é `null`).

## Formato de patch (MR-PATCH v1) — resposta das tarefas `expand`/`improve`

Responda **somente** com um objeto JSON:

```json
{
  "summary": "frase curta do que foi feito",
  "system":  {"set": {"startMapId": 1}, "switches": [{"name": "Falou com o rei", "ref": "met_king"}], "variables": [{"name": "Moedas", "ref": "coins"}]},
  "db": {
    "items":   {"add": [{"ref": "elixir", "name": "Elixir", "description": "...", "iconIndex": 176, "price": 300,
                         "consumable": true, "scope": 7, "occasion": 0, "itypeId": 1,
                         "damage": {"type": 0, "elementId": 0, "formula": "0", "variance": 0, "critical": false},
                         "effects": [{"code": 11, "dataId": 0, "value1": 0, "value2": 400}]}],
                "update": [{"id": 1, "set": {"price": 60}}]},
    "weapons|armors|skills|enemies|troops|states|actors|classes|commonEvents": "mesma forma {add, update}"
  },
  "maps": {
    "add":    [{"ref": "cave", "name": "Caverna", "displayName": "Caverna Sombria", "width": 20, "height": 15, "tilesetId": 1,
                "fill": {"z0": 2816},
                "rects": [{"x": 0, "y": 0, "w": 20, "h": 1, "z": 1, "id": 1}],
                "tiles": [{"x": 3, "y": 4, "z": 1, "id": 1}],
                "bgm": {"name": "Dungeon1", "volume": 90, "pitch": 100},
                "events": [ EVENT ]}],
    "update": [{"id": 1, "rects": [], "tiles": [], "events": {"add": [EVENT], "update": [{"id": 3, "set": {"x": 4}}], "remove": [5]}}]
  },
  "files":  [{"path": "code/js/ext/meu-sistema.js", "content": "/* módulo JS */"},
             {"path": "code/css/theme.css", "content": "/* tema */"}],
  "assets": [{"category": "characters", "name": "NovoNPC", "note": "sprite que o autor precisa fornecer"}],
  "notes":  ["observações para o autor"]
}
```

Regras:
- `ref` dá um nome simbólico a algo criado no patch. Em qualquer parâmetro de evento use `"@ref"` para referenciar o id
  alocado (ex.: `{"give_item": "@elixir"}`, `{"transfer": {"map": "@cave", "x": 3, "y": 3}}`, `{"set_switch": "@met_king"}`).
- Referencie ids **existentes** pelo número. Nunca invente assets: use só nomes que existem em `assetIndex` (listados no
  contexto). Para algo novo, adicione em `assets` (o autor fornece; o CLI cria um placeholder).
- Não repita nem renumere dados existentes. Preserve nomes/ids/lógica originais salvo pedido contrário.
- `tilesetId`, ids de tiles e `characterName` devem existir no jogo (veja o contexto). Tiles: z0/z1 chão, z2/z3 acima; id 0 = vazio.
  Em tilesets MV: A2 grama típica = 2816 (+48 por tipo de autotile); B = 1..255 (árvore, objetos).
- Arquivos novos de JS devem ficar em `code/js/ext/` e se registrar assim:
  `MR.ext.modules['nome'] = {...}`, `MR.ext.hooks.mapEnter = (MR.ext.hooks.mapEnter||[]).concat([(scene)=>{}])`,
  `MR.ext.commands[CODIGO] = function(params, cmd){ /* this = intérprete */ }`,
  `MR.ext.pluginCommands['NomeDoComando'] = function(args){ ... }`. Sem frameworks; Canvas 2D; ES2017.
- Temas/UX: edite `code/css/theme.css` (variáveis `--mr-*`) ou use `MR.config`.

### EVENT

```json
{"name": "Guarda", "x": 5, "y": 7,
 "pages": [{
   "image": {"characterName": "People1", "characterIndex": 2, "direction": 2, "pattern": 1},
   "trigger": "action",           // action | touch | event-touch | auto | parallel  (ou 0..4)
   "priority": "same",            // below | same | above (ou 0..2)
   "move": "fixed",               // fixed | random | approach | custom
   "conditions": {"switch": 3, "switch2": 4, "variable": [2, ">=", 5], "self": "A", "item": 1, "actor": 1},
   "script": [ PASSOS ]           // ou "list": [comandos MV brutos terminando em {"code":0,"indent":0,"parameters":[]}]
 }]}
```

### PASSOS (DSL de eventos; compilada para comandos MV com indentação correta)

| passo | exemplo |
|---|---|
| texto | `{"say": ["linha 1", "linha 2"], "face": ["Actor1", 0], "pos": "bottom", "bg": "window"}` (pos: top/middle/bottom; bg: window/dim/none; até 4 linhas por caixa; separe em vários `say`) |
| escolhas | `{"choices": ["Sim","Não"], "branches": [[PASSOS],[PASSOS]], "cancel": "branch"\|"disallow"\|índice}` |
| condição | `{"if": {"switch": 3, "is": true}, "then": [..], "else": [..]}` — também `{"variable": [2,">=",5]}`, `{"self": "A", "is": true}`, `{"gold": 100}` (>=), `{"item": 1}`, `{"actor": 2}` (no grupo), `{"script": "js"}` |
| laço | `{"loop": [PASSOS]}`, `{"break": true}`, `{"exit": true}`, `{"label": "x"}`, `{"goto": "x"}` |
| interruptor | `{"set_switch": 3, "to": true}`; `{"self_switch": "A", "to": true}` |
| variável | `{"set_var": 2, "op": "set\|add\|sub\|mul\|div\|mod", "value": 5}` (ou `"random": [1,6]`) |
| itens/ouro | `{"give_item": 1, "n": 2}` (n<0 remove), `{"give_weapon": 1}`, `{"give_armor": 1}`, `{"give_gold": 100}` |
| grupo | `{"party_add": 2}`, `{"party_remove": 2}` |
| mapa | `{"transfer": {"map": 2, "x": 3, "y": 4, "dir": 2, "fade": "black"\|"none"}}` |
| batalha | `{"battle": 1, "win": [..], "escape": [..], "lose": [..], "can_escape": true, "can_lose": false}` |
| loja | `{"shop": [["item", 1], ["weapon", 2, 500]], "buy_only": false}` |
| som | `{"bgm": {"name": "Town1", "volume": 90, "pitch": 100}}`, `{"se": {...}}`, `{"me": {...}}`, `{"bgs": {...}}`, `{"fade_bgm": 2}` |
| tela | `{"wait": 30}`, `{"fade_out": true}`, `{"fade_in": true}`, `{"tint": [r,g,b,gray], "frames": 60}`, `{"flash": [255,255,255,170], "frames": 20}`, `{"shake": [5,5,30]}` |
| imagens | `{"picture": 1, "name": "Img", "x": 0, "y": 0}`, `{"erase_picture": 1}` |
| evento | `{"common_event": 3}`, `{"erase_event": true}`, `{"move_route": {"target": 0, "route": [..comandos de rota MV..], "wait": true}}` |
| atores | `{"change_hp": 2, "actor": 0, "value": 50}` (actor 0 = todos), `{"recover_all": true, "actor": 0}`, `{"exp": 100, "actor": 0}`, `{"learn_skill": 5, "actor": 1}` |
| sistema | `{"menu_access": false}`, `{"save_access": false}`, `{"encounters": false}`, `{"open_menu": true}`, `{"game_over": true}`, `{"title": true}` |
| código | `{"script": "$gameVariables.setValue(3, 10);"}` (API de compatibilidade abaixo), `{"comment": "nota"}` |
| bruto | `{"raw": {"code": 121, "parameters": [1, 1, 0]}}` |

Texto: códigos de controle suportados: `\V[n] \N[n] \P[n] \G \C[n] \I[n] \{ \} \. \| \! \> \< \^`. Nada de HTML.

### API de compatibilidade para `script`/ext (subconjunto do MV)

`$gameVariables.value(i)/setValue(i,v)`, `$gameSwitches.value(i)/setValue(i,b)`, `$gameSelfSwitches.value([map,ev,"A"])/setValue(...)`,
`$gameParty.gold()/gainGold(n)/gainItem($dataItems[i], n)/hasItem(item)/members()/addActor(id)/removeActor(id)`,
`$gamePlayer.reserveTransfer(map,x,y,dir,fade)/x/y`, `$gameMap.mapId()/event(id)`, `$gameMessage.add(texto)`,
`$dataItems/$dataWeapons/$dataArmors/$dataActors/$dataSkills/$dataSystem`, `AudioManager.playSe({name,volume,pitch})`.
Estado global: `MR.G` (`sw(i)`, `v(i)`, `gold`, `items`, `party`, `actor(id)`), cena atual: `MR.sceneMap`, `MR.scene()`.
