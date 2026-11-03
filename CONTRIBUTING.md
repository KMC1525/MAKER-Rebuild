# Contribuindo

Obrigado por querer ajudar! O projeto é pequeno de propósito: **zero dependências de Python** e um runtime em JS puro (Canvas 2D).

## Ambiente

```bash
git clone https://github.com/kmc1525/MAKER-Rebuild.git && cd MAKER-Rebuild
pip install -e ".[dev]"
python -m pytest -q                 # testes rápidos (sem navegador)
python -m pytest -q tests/test_runtime.py   # jogabilidade em Chromium (precisa de node + playwright)
```

## Onde mexer

| quero… | arquivo(s) |
|---|---|
| suportar mais um comando de evento | `src/maker_rebuild/runtime/js/mr-interpreter.js` (`H[codigo] = function (p) {…}`) — o `analyze`/`validate` passam a reconhecê-lo sozinhos |
| corrigir/estender render de mapa, autotiles, personagens | `runtime/js/mr-map.js` |
| batalha / menus / lojas | `runtime/js/mr-battle.js`, `mr-scenes.js` |
| idioma da UI própria do runtime | `src/maker_rebuild/build/i18n.py` (um dicionário por idioma) |
| novo provedor de IA | `src/maker_rebuild/providers/` (herde de `Provider`, registre em `__init__.py` e `config.PROVIDERS`) |
| novo passo da DSL de eventos | `src/maker_rebuild/ai/eventdsl.py` (`s_<nome>`) + tabela em `prompts/runtime_api.md` |
| melhorar leitura de uma engine | `src/maker_rebuild/project.py`, `engines/` |

## Regras

1. **Teste junto.** Todo bug corrigido ganha um teste que falhava antes. Fixtures são **sintéticas** (`tests/fixtures.py`,
   `src/maker_rebuild/demo.py`) — **não** envie arte, música, roteiros ou jogos de terceiros no repositório.
2. **Fidelidade primeiro.** Comportamento do runtime deve seguir o RPG Maker original; quando divergir, documente em "Limitações" no README.
3. **A IA nunca escreve direto no jogo.** Tudo que vem de LLM passa por validação (`ai/patch.py`, `eventdsl.check_list`, `node --check`).
4. **Sem segredos em disco.** Chaves de API só via variáveis de ambiente.
5. Python **3.9+** (sintaxe) e JS **ES2017** no runtime (roda via `file://`, sem bundler).

## Reportando problemas de um jogo real

Cole a saída de `maker-rebuild analyze <jogo> --json` e a lista de avisos do `validate`. **Não** anexe assets/projetos protegidos por direitos autorais.
