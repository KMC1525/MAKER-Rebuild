# Arquitetura

## Visão geral

```
src/maker_rebuild/
├── cli.py · shell.py · ui.py · config.py        interface (argparse, REPL, cores/spinner, config persistente)
├── pipeline.py                                  orquestra recompile / expand / improve / translate / port
├── project.py · assets.py · demo.py             leitura dos projetos → IR (Project) · mapeamento de assets · projeto de demo
├── engines/                                     rubymarshal · rgssad · crypt (MV/MZ) · lcf (2000/2003) · vfs (pasta + arquivo RGSS)
├── analyze.py                                   mapeamento estrutural + riscos
├── build/                                       builder · builtgame · validate · commands · datajs · zipper · i18n · audio · png
├── ai/                                          client · prompts · context · eventdsl · patch · translate · port · jobs · jsonio
├── providers/                                   anthropic · openai_compat · gemini · ollama · mock (+ http)
├── prompts/                                     system_base.md (o system prompt do autor) · runtime_api.md (contrato do runtime/patch)
└── runtime/                                     js/mr-*.js · css · html — o que vai dentro do jogo entregue
```

## 1. Leitura → IR

`open_project()` detecta a engine (`detect_root`) e preenche um `Project`:

- `db`: `actors, classes, skills, items, weapons, armors, enemies, troops, states, animations, tilesets, commonEvents, system, mapInfos`
- `maps`: `{id: mapa}` — mapas no formato do MV (`data` plana com 6 camadas z: 0–3 tiles, 4 sombra, 5 região; `events` com `null` no índice 0)
- `assets`: `AssetEntry(category, name, ext, reader())` — *lazy*: só lê/descriptografa quando o builder grava
- `plugins`, `plugin_sources`, `scripts` (Ruby), `fonts`, `notes` (documentos do autor), `warnings`

Por que o formato do MV? VX Ace → MV é quase 1:1 (os ids de tiles, campos e códigos de evento são parentes diretos). O conversor Marshal
(`rubymarshal.convert`) transforma `@snake_case` em `camelCase`; `project.py` corrige as diferenças (Table → listas, página de evento
`condition`/`graphic` → `conditions`/`image`, camadas de mapa, `params` de classe). Os comandos de evento são normalizados em
`build/commands.py` (`102`, `104`, XP `101/201`; scripts Ruby ganham `lang: "ruby"`).

### Descriptografia
- MV/MZ: 16 bytes de cabeçalho falso + XOR nos 16 primeiros bytes reais com `encryptionKey` (de `System.json`, ou recuperada do cabeçalho PNG conhecido).
- RGSS v1 (`.rgssad/.rgss2a`) e v3 (`.rgss3a`): chaves LCG (`k*7+3`; v3 inicia com `seed*9+3`). Há escritores equivalentes para teste.

## 2. Builder → jogo entregue

`build_game()` cria `game-x/`, copia o runtime, escreve assets (com índice `assetIndex` *case-insensitive* e preferência `ogg > m4a > …`),
dados (`code/js/data/*.js`, carregados por `<script>` → funcionam em `file://`), `Game.html` (ordem: runtime → config → db → `ext/` → `plugins/` → boot),
`about.html`, manifesto. Os dados são `.js` (`MR.data.db = {…};`) e o `datajs` lê/escreve de volta — assim **qualquer jogo gerado pode ser
reaberto** (`BuiltGame`) para expandir/traduzir/portar sem o projeto original.

## 3. Runtime (`runtime/js`)

| arquivo | responsabilidade |
|---|---|
| `mr-core.js` | `MR.assets`, `MR.audio`, `MR.input`, estado `MR.G` (switches/variáveis/inventário/grupo), regras (EXP, parâmetros), save/load, `MR.t()` (i18n) |
| `mr-ui.js` | janelas (`Window.png` ou fallback), parser de códigos de texto, `MR.ListWin`, `MR.MessageBox` (texto, escolhas, número, item, texto rolante) |
| `mr-map.js` | `MR.Tilemap` (autotiles), `MR.Char` (movimento/rotas), `MR.SceneMap` (eventos, gatilhos, encontros, efeitos de tela) |
| `mr-interpreter.js` | `MR.Interpreter` — comandos `H[codigo]`; API de compatibilidade `$gameVariables`…; ponto de extensão `MR.ext.commands` |
| `mr-battle.js` | batalha por turnos (fórmulas `a.atk * 4 - b.def * 2`) |
| `mr-scenes.js` | título, menu, loja, save/load, game over |
| `mr-main.js` | pilha de cenas, laço 60 Hz fixo, tratamento de erros (`F9` = avisos) |

Pontos de extensão (módulos em `code/js/ext/` carregados antes do boot):
`MR.ext.commands[codigo]`, `MR.ext.pluginCommands[nome]`, `MR.ext.hooks.{boot,mapEnter,menuCommand,titleCommand}`, `MR.ext.modules`, `MR.config.extraMenu`.

## 4. IA

```
pedido ──► clarify ──► plan ──► (por feature) implement ──► apply_patch ──► save ──► validate ──► zip
            │ perguntas   │ features   │ JSON (patch)          │ valida + aplica atômico
            ▼ (se faltar info crítica) ▼                       ▼ rollback em qualquer erro
```

- `AIClient` monta o *system prompt* = **`system_base.md`** (o prompt do autor) + contrato operacional + (opcional) `runtime_api.md`;
  faz streaming, cache por hash (provedor+modelo+prompt), e **reparo de JSON** (uma re-pergunta com o erro de parse).
- **MR-PATCH v1** (`ai/patch.py`): `system / db / maps / files / assets / notes`. Tudo validado: ids existentes, dimensões, camadas,
  caminhos de arquivo (lista de permitidos), `node --check` em JS, referências simbólicas (`"ref"` / `"@ref"`) e checagem cruzada
  pós-aplicação (itens, mapas, eventos comuns, tropas). Falha → `PatchError` com mensagens que alimentam a próxima tentativa (até 3).
- **DSL de eventos** (`ai/eventdsl.py`): compila passos de alto nível para comandos MV com indentação e marcadores corretos
  (`101/401`, `102/402/403/404`, `111/411/412`, `301/601–604`, `302/605`, …). `check_list` valida qualquer lista bruta.
- **Tradução** (`ai/translate.py`): extrai *unidades* (blocos de diálogo = `101` + `401…`, escolhas, texto rolante, nomes/descrições do
  banco, termos, nome de mapa); protege códigos de controle como `<<n>>`; deduplica; lotes de ~5k caracteres; verifica que os marcadores
  voltaram intactos (senão reenvia individualmente; por fim mantém o original e avisa); reaplica de trás para frente (o nº de linhas pode mudar).
- **Porte** (`ai/port.py`): Ruby→JS por regras (one-liners), restante pela IA em lote; JS só entra se passar `node --check`;
  plugins/scripts customizados viram `code/js/ext/port-*.js`.

## 5. Provedores

`Provider.complete(LLMRequest, on_chunk) -> Completion` — HTTP com `urllib` (streaming linha a linha). `providers/http.py` faz *retry*
em `408/429/5xx/529` (respeita `Retry-After`), não insiste em "conexão recusada" (servidor local desligado) e devolve mensagens com a
correção provável ("o Ollama está rodando?"). `AnthropicProvider`/`OpenAICompatProvider` removem parâmetros rejeitados (`temperature`,
`max_tokens` ↔ `max_completion_tokens`, `response_format`) e refazem a chamada.

## 6. Testes

- `test_engines/project/build`: Marshal (contra Ruby real, quando existe), RGSS v1/v3, criptografia MV, VX Ace/MV/MZ/2000 sintéticos, estrutura entregue, validações.
- `test_ai_offline`: DSL, patches (aceitação e **rejeição sem efeito colateral**), tradução (incluindo perda de códigos de controle), porte, jsonio.
- `test_providers`: servidor HTTP falso que imita Anthropic/OpenAI/Gemini/Ollama (streaming, *retry*, parâmetros rejeitados, chave ausente).
- `test_runtime`: `node --check` do runtime + **jogabilidade real** em Chromium headless (diálogo, escolhas, inventário, colisão, teletransporte, batalha, save).
