<div align="center">

# MAKER-Rebuild

**Recompila, melhora e expande jogos de RPG Maker (2000 → MZ) para HTML + CSS + JS, com ajuda de IAs generativas — frontier ou locais.**

[![CI](https://github.com/kmc1525/MAKER-Rebuild/actions/workflows/ci.yml/badge.svg)](https://github.com/kmc1525/MAKER-Rebuild/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![deps](https://img.shields.io/badge/depend%C3%AAncias-zero-brightgreen)
![license](https://img.shields.io/badge/licen%C3%A7a-MIT-green)
![status](https://img.shields.io/badge/status-alpha-orange)

[English](README.en.md) · **Português**

</div>

---

## O que é

O **MAKER-Rebuild** é uma ferramenta de **terminal (CLI) em Python** que pega um jogo feito em RPG Maker e entrega um
**jogo web autônomo** (`Game.html` + CSS + JS + assets) dentro de um `.zip` — sem NW.js, sem Electron, sem plugin proprietário,
sem framework pesado: só **HTML5 Canvas**.

Ela faz três coisas:

1. **Recompila** — lê o projeto original (pastas `Data/`, `img/`, `audio/`, arquivos `.rpgmvp`, `.rgss3a`…), descriptografa os assets,
   mapeia mapas, eventos, banco de dados e plugins, e gera o jogo em HTML/CSS/JS fiel ao original.
2. **Melhora** — corrige, moderniza e rebalanceia (dados, UI/tema, módulos JS) com a ajuda de uma IA.
3. **Expande** — adiciona conteúdo novo (mapas, NPCs, itens, inimigos, quests, sistemas) de forma coerente com o jogo,
   a partir de um pedido em linguagem natural, de um roteiro/GDD ou de planilhas.

E também **traduz** o jogo inteiro (diálogos, banco de dados, termos do sistema) preservando códigos de controle (`\C[2]`, `\V[1]`, `\N[1]`…).

O comportamento do agente é definido pelo [system prompt do projeto](src/maker_rebuild/prompts/system_base.md) — fidelidade ao
original acima de tudo, código limpo, preservar nomes de variáveis/switches/eventos, e **perguntar antes de assumir** quando faltar
informação crítica.

> **Status: alpha.** A conversão de **MV, MZ e VX Ace** funciona de ponta a ponta e é testada em navegador real. XP, VX e 2000/2003
> são **experimentais** (veja a [matriz de suporte](#suporte-por-engine)). Leia [Limitações](#limitações-conhecidas) antes de prometer
> um jogo comercial complexo ao seu público.

---

## Instalação

Requisitos: **Python 3.9+**. Nenhuma dependência de Python (só biblioteca padrão).
Opcionais: `node` (valida a sintaxe dos JS gerados), `ffmpeg` (converte áudio WMA/MIDI).

```bash
git clone https://github.com/kmc1525/MAKER-Rebuild.git
cd MAKER-Rebuild
pip install -e .
```

Ou direto do GitHub, isolado:

```bash
pipx install git+https://github.com/kmc1525/MAKER-Rebuild.git
```

Confira o ambiente:

```bash
maker-rebuild doctor
```

## Começando em 1 minuto (sem ter um jogo)

O projeto traz um **mini-jogo de demonstração** (sem arte de terceiros) para você testar tudo:

```bash
maker-rebuild demo                         # cria ./demo-mv (um projeto RPG Maker MV sintético)
maker-rebuild analyze demo-mv              # mapeia estrutura, riscos e cobertura do runtime
maker-rebuild recompile demo-mv -o dist    # gera dist/demo-quest/ e dist/demo-quest.zip
maker-rebuild serve dist/demo-quest.zip --open   # joga no navegador
```

Para testar os fluxos de IA **sem rede e sem chave**, use o provedor offline `mock`:

```bash
maker-rebuild expand dist/demo-quest.zip "adicione uma poção e um NPC" --provider mock -o dist2
```

## Uso com um jogo de verdade

```bash
# 1) entenda o projeto (sem IA, não altera nada)
maker-rebuild analyze ./MeuJogo            # pasta ou .zip; aceita raiz do projeto, www/ ou pasta acima

# 2) conversão fiel (sem IA) → dist/meu-jogo.zip
maker-rebuild recompile ./MeuJogo -o dist

# 3) jogar / revisar
maker-rebuild serve dist/meu-jogo.zip --open
maker-rebuild validate dist/meu-jogo.zip

# 4) com IA: traduzir, portar scripts, melhorar, expandir
export ANTHROPIC_API_KEY=...               # ou OPENAI_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY
maker-rebuild translate dist/meu-jogo.zip --to en --glossary examples/glossary.csv --tone "jovial, gírias leves"
maker-rebuild port ./JogoVXAce --provider anthropic        # scripts Ruby / plugins → JS
maker-rebuild improve dist/meu-jogo.zip "rebalanceie a dificuldade do início e deixe o menu mais legível"
maker-rebuild expand dist/meu-jogo.zip "adicione uma dungeon de gelo com chefe, 3 itens e uma quest" --docs roteiro.md fichas.csv

# tudo num passo só (pedido livre → esclarecer → planejar → converter → aplicar → revisar → .zip)
maker-rebuild recompile ./MeuJogo -i "traduza para inglês e adicione um chefe secreto" --provider ollama --model qwen2.5:14b
```

Ou abra o **terminal interativo** (rode sem argumentos):

```text
$ maker-rebuild
maker-rebuild › /open ./MeuJogo
maker-rebuild › /analyze
maker-rebuild › /recompile
maker-rebuild › adicione uma loja de poções na vila     ← linguagem natural, roteada pela IA
```

### Todos os comandos

| comando | o que faz | usa IA |
|---|---|:-:|
| `analyze <jogo>` | engine, mapas, eventos, banco de dados, assets, plugins, riscos, cobertura do runtime (`--json`) | – |
| `recompile <jogo>` | converte para HTML/CSS/JS e gera o `.zip`; com `-i "pedido"` encadeia tradução/porte/expansão | opcional |
| `expand <jogo> "pedido"` | adiciona mapas, eventos, itens, inimigos, sistemas… | ✔ |
| `improve <jogo> ["pedido"]` | melhorias seguras: balanceamento, tema/UI, correções | ✔ |
| `translate <jogo> --to LANG` | traduz diálogos, banco de dados e UI preservando códigos de controle | ✔ |
| `port <jogo>` | porta scripts Ruby (VX/VXA/XP) e plugins MV/MZ para módulos JS | ✔ |
| `validate <jogo>` | estrutura, assets ausentes, referências quebradas, comandos sem suporte, `node --check` | – |
| `serve <jogo>` | servidor local em `127.0.0.1` para jogar | – |
| `providers [--local]` | lista provedores e detecta Ollama/LM Studio/llama.cpp/vLLM | – |
| `doctor` · `config` · `prompt` · `demo` · `shell` | utilitários | – |

`expand`, `improve`, `translate` e `port` aceitam **um jogo já recompilado** (pasta/.zip) **ou um projeto original** (recompilam antes).
Nada é sobrescrito: a saída vai para `-o` (padrão `dist/`), e o original nunca é tocado.

---

## O que você recebe (estrutura entregue)

```
meu-jogo.zip
└── meu-jogo/
    ├── Game.html                 ← abra e jogue (funciona via file://)
    ├── code/
    │   ├── html/about.html
    │   ├── css/                  game.css · theme.css (seu: nunca sobrescrito) · fonts.css
    │   └── js/
    │       ├── mr-*.js           runtime (Canvas 2D, sem frameworks)
    │       ├── data/             config.js · db.js · maps/map-N.js   (dados do jogo)
    │       ├── ext/              módulos gerados por IA / seus
    │       ├── plugins/_original/   plugins MV/MZ originais (referência para o porte)
    │       └── scripts-ruby/     scripts Ruby originais (referência para o porte)
    └── assets/
        ├── sprites/              characters · faces · enemies · sv_actors · animations
        ├── background/           tilesets · parallaxes · battlebacks · titles
        ├── ui-ux/                system (Window, IconSet…) · pictures · fonts
        ├── music/                bgm · bgs · me
        └── sfx/
```

Além disso: `code/validation-report.json` (revisão automática), `code/rebuild-manifest.json` (histórico de tudo o que foi feito
no jogo) e, quando a IA pede arte nova, `code/assets-todo.md` + **placeholders** gerados para você substituir.

---

## Como funciona

```
 original (pasta/.zip)                                                          meu-jogo.zip
 ┌──────────────┐   ┌───────────┐   ┌───────────────┐   ┌──────────────┐   ┌───────────────┐
 │ Data/ img/   │ → │  leitores │ → │  IR (modelo   │ → │   builder    │ → │ Game.html +   │
 │ audio/ .rgss │   │ MV/MZ JSON│   │  estilo MV)   │   │ runtime Canvas│   │ code/ assets/ │
 │ .rpgmvp ...  │   │ Marshal   │   │ mapas, eventos│   │ + dados .js  │   └──────┬────────┘
 └──────────────┘   │ LCF (2k)  │   │ banco, assets │   └──────────────┘          │
                    └───────────┘   └───────┬───────┘                      validate + zip
                                            │
                       IA (opcional) ◄──────┘  esclarecer → planejar → patch/tradução/porte → validar
```

- **Leitores determinísticos**: MV/MZ (JSON), VX Ace/VX/XP (um leitor próprio de *Ruby Marshal* — nada é executado), arquivos
  `.rgssad/.rgss2a/.rgss3a`, descriptografia de `.rpgmvp/.rpgmvm/.rpgmvo` e `.png_/.m4a_/.ogg_` (a chave vem de `System.json` ou é
  recuperada do cabeçalho PNG), e um leitor LCF mínimo para 2000/2003.
- **IR comum** na nomenclatura do MV: como VX Ace e MV compartilham o modelo de dados, a conversão é quase 1:1 e o que não é 1:1
  é normalizado (tabelas, camadas, `cancelType` de escolhas, páginas de evento…).
- **Runtime próprio** (`runtime/js/mr-*.js`): tilemap com autotiles, personagens, colisão, interpretador de eventos, janelas com
  `Window.png` do jogo, batalha por turnos com as fórmulas do banco de dados, loja, menu, save/load, áudio, tela (tom/flash/tremor/imagens).
- **IA sempre por contrato**: a IA nunca grava no jogo diretamente. Ela devolve **JSON** (patch `MR-PATCH v1`, lote de traduções,
  lote de portes); o CLI **valida tudo** (formas, ids, limites, caminhos, `node --check` em todo JS) e só então aplica — de forma
  **atômica** (se algo falha, nada é aplicado) e com **re-tentativa guiada** pelos erros.
- **DSL de eventos**: em vez de pedir à IA que escreva comandos brutos do RPG Maker (indentação, 401/402/404…), ela descreve
  `{"say": [...]}`, `{"if": ...}`, `{"choices": ...}`, `{"battle": ...}` e o CLI compila para comandos corretos. Veja o
  [contrato completo](src/maker_rebuild/prompts/runtime_api.md).

Mais detalhes em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## IAs suportadas (frontier e locais)

Sem SDKs: o CLI fala HTTP direto (streaming SSE/NDJSON, *retries* com *backoff*, parâmetros rejeitados são removidos e a chamada refeita).

| provedor | tipo | variável de ambiente | exemplo |
|---|---|---|---|
| `anthropic` (`claude`) | frontier | `ANTHROPIC_API_KEY` | `--provider anthropic --model claude-sonnet-5-5` |
| `openai` (`gpt`) | frontier | `OPENAI_API_KEY` | `--provider openai --model gpt-4.1` |
| `gemini` (`google`) | frontier | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `--provider gemini --model gemini-2.5-pro` |
| `openrouter` | frontier (agregador) | `OPENROUTER_API_KEY` | `--provider openrouter --model <vendor/modelo>` |
| `ollama` (`local`) | **local** | – | `--provider ollama --model qwen2.5:14b` |
| `lmstudio` | **local** | – | `--provider lmstudio` (porta 1234) |
| `llamacpp` | **local** | – | `--provider llamacpp` (porta 8080, `llama-server`) |
| `vllm` | **local** | – | `--provider vllm` (porta 8000) |
| `openai-compat` | local/qualquer | `OPENAI_COMPAT_API_KEY` | `--provider openai-compat --base-url http://host:porta/v1` |
| `mock` | offline (teste) | – | respostas sintéticas determinísticas |

- Os modelos padrão são só sugestões — **use `--model`**. Dica: use um modelo local com boa aderência a JSON/instruções;
  traduções toleram modelos menores, **expansões** (patches e eventos) se beneficiam de modelos maiores.
- Detecte servidores locais: `maker-rebuild providers --local`. No Ollama, `--num-ctx` aumenta a janela de contexto (padrão 16384).
- Escolha persistente: `maker-rebuild config set provider ollama` · `config set model qwen2.5:14b`.
- **Chaves de API nunca são gravadas em disco** — só variáveis de ambiente.
- Respostas são **cacheadas** em `~/.cache/maker-rebuild` (traduções repetidas custam zero); `--no-cache` desliga.

### Sobre conteúdo adulto/violento

O system prompt do projeto instrui o agente a trabalhar **sem restrições** com jogos SFW e NSFW, sem recusar, censurar ou
adicionar avisos ao texto do jogo. Atenção: **provedores hospedados aplicam as próprias políticas de uso** e podem recusar um pedido
(o CLI avisa claramente quando isso acontece). Se isso for um problema para o seu projeto, use um **modelo local**
(`--provider ollama|lmstudio|llamacpp|vllm`), onde você controla o modelo.

---

## Suporte por engine

| engine | leitura | assets criptografados | mapas/tiles | eventos | banco de dados | status |
|---|---|---|---|---|---|---|
| **MV** | JSON | `.rpgmvp` `.rpgmvm` `.rpgmvo` ✔ | autotiles A1–A4, sombras, regiões | ✔ | completo | **estável** |
| **MZ** | JSON (mesmo modelo do MV) | `.png_` `.m4a_` `.ogg_` ✔ | idem MV | ✔ (comandos de plugin `357` exigem `port`) | completo | **bom** |
| **VX Ace** | Ruby Marshal | `.rgss3a` ✔ | completo (mesmo modelo do MV) | ✔ (scripts Ruby → `port`) | completo | **bom** |
| VX | Ruby Marshal | `.rgss2a` ✔ | parcial | básicos | parcial | experimental |
| XP | Ruby Marshal | `.rgssad` ✔ | autotiles simplificados | básicos | parcial | experimental |
| 2000 / 2003 | LCF (mapas) | n/a | só camadas de tiles brutas | ✘ (reconstruir com IA) | ✘ | experimental |

Em engines experimentais o CLI **diz o que não conseguiu converter** (avisos no `analyze` e no relatório) em vez de fingir fidelidade.

## Limitações conhecidas

Seja direto com você mesmo sobre o que o runtime ainda **não** faz:

- **Autotiles**: o chão (A2) foi validado visualmente; água/cachoeira (A1), paredes (A3) e topos/paredes (A4) estão implementados a partir
  do layout padrão do MV, mas **ainda não foram conferidos contra arte real** — se algum tile sair errado, abra uma *issue*.
- **Plugins MV/MZ não rodam como estão** (o runtime não é o `rpg_*.js`). O comando `port` pede à IA para portá-los; o resultado é
  gerado em `code/js/ext/port-*.js` com cabeçalho "gerado por IA — **revisar**".
- **Scripts Ruby** (XP/VX/VXA): one-liners comuns (switches, variáveis, ouro, itens) são convertidos por regras; o resto vai para a IA.
- **Batalha**: por turnos, com fórmulas de dano/variância, ações de inimigo, itens, fuga, EXP/ouro/drops. Ainda **sem** animações de
  batalha, estados com efeitos além de “morto”, elementos/resistências, críticos, TP, *side-view*, eventos de batalha (páginas de tropa).
- **Menu**: itens (uso fora de batalha), status, salvar, sair. **Ainda sem** menus de habilidades/equipamento/formação.
- **Comandos de evento** não suportados são listados pelo `analyze`/`validate` (ex.: animações `212`, clima `236`, veículos, seguidores)
  e ignorados com aviso em runtime (F9 mostra os avisos no jogo). Dá para estendê-los: `MR.ext.commands[codigo] = fn`.
- **Áudio MIDI/WMA** não toca em navegadores — use `--convert-audio` (precisa de `ffmpeg`; MIDI também de `fluidsynth` + `MAKER_REBUILD_SOUNDFONT`).
- **Assets RTP** (Runtime Package) não vêm dentro dos projetos VX/VXA/XP/2000: sem eles, o `validate` lista o que falta.
- **Jogos HD/resoluções customizadas** de plugins (tela, tile) não são lidos de plugins; use as configurações do `System.json`.
- A suíte de testes usa **projetos sintéticos** (sem arte/jogos de terceiros). Jogos reais têm mais variações — abra *issues* com os
  avisos do `analyze` (sem anexar material com direitos autorais).

## Uso responsável

Use o MAKER-Rebuild com **jogos seus**, de domínio público ou com **permissão** do autor. A conversão é técnica; **música, arte e
roteiro continuam sendo de quem os criou**. Trechos do projeto são enviados ao provedor de IA que você escolher — para material
confidencial, prefira modelos locais.

---

## Desenvolvimento

```bash
pip install -e ".[dev]"
python -m pytest -q          # 90+ testes: leitores, builder, patches, tradução, provedores (servidor HTTP falso) e jogabilidade
```

- Os testes de jogabilidade (Chromium headless via Playwright) **pulam sozinhos** se `node`/`playwright` não existirem.
  Para rodá-los: `npm i -g playwright && npx playwright install chromium` (e `NODE_PATH=$(npm root -g)`).
- Quer adicionar um provedor de IA, comando de evento ou idioma de UI? Veja [`CONTRIBUTING.md`](CONTRIBUTING.md).

### Roadmap

- [ ] Menus de habilidades/equipamento/formação; animações de batalha; estados e elementos
- [ ] Clima, animações de mapa (`212`), veículos e seguidores
- [ ] Fidelidade total de VX/XP (autotiles, banco de dados) e leitor LCF completo (2000/2003: eventos e banco)
- [ ] Geração de arte/áudio por modelos locais (Stable Diffusion/ComfyUI) para os *placeholders*
- [ ] Modo *watch* + recarga rápida; empacotadores para desktop/mobile (Tauri/Capacitor)

## Licença

[MIT](LICENSE) © 2026 KMC
