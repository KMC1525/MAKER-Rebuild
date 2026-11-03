# Changelog

Todas as mudanças relevantes do MAKER-Rebuild ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota
[Versionamento Semântico](https://semver.org/lang/pt-BR/) (enquanto estiver em `0.x`, mudanças incompatíveis podem ocorrer entre versões menores).

Categorias: **Adicionado** · **Alterado** · **Corrigido** · **Removido** · **Segurança** · **Limitações** (o que ainda não funciona).

## [Não lançado]

## [0.2.0] - 2026-11-03

### Adicionado
- **Instalação como executável autônomo** (não exige Python) para **Windows, macOS e Linux**:
  - `install.sh` (Linux e macOS, POSIX sh), `install.ps1` (Windows PowerShell 5.1+/7) e `install.bat` (atalho para o `.ps1`).
  - Três modos: `auto` (padrão: baixa o executável da última release e, se não houver, cai para o modo Python), `exe` e `python`
    (ambiente virtual isolado em `~/.local/share/maker-rebuild` ou `%LOCALAPPDATA%\MAKER-Rebuild`).
  - Opções: `--prefix`, `--version`, `--ref`, `--from-local`, `--dry-run`, `--uninstall` (`-Prefix`, `-Version`, `-FromLocal`, `-DryRun`, `-Uninstall`, `-NoPath` no PowerShell).
  - Verificação de **checksum SHA-256** do download (a instalação é abortada se não conferir), remoção da quarentena no macOS e ajuste do `PATH` do usuário no Windows.
  - `MAKER_REBUILD_BASE_URL` para instalar a partir de um espelho/servidor interno.
- **`packaging/build_exe.py`**: gera o executável com PyInstaller (`--onefile`, com runtime e prompts embutidos), roda um *smoke test*
  do binário (`--version`, `demo`, `recompile`, `validate`, `expand` com o provedor mock) e produz
  `maker-rebuild-<so>-<arch>.tar.gz|zip` + `.sha256` (`linux|macos|windows` × `x86_64|arm64`). Extra opcional: `pip install -e ".[exe]"`.
- **CI de release** (`.github/workflows/release.yml`): ao publicar uma tag `v*`, compila os executáveis em Linux, macOS (Intel e Apple Silicon) e Windows e
  anexa os pacotes e checksums à release, usando a seção correspondente deste `CHANGELOG.md` como notas (`packaging/changelog_section.py`).
- **CI**: jobs que testam os instaladores em Linux, macOS e Windows e que compilam/testam o executável nos três sistemas.
- `maker-rebuild doctor` informa a versão e se está rodando como executável autônomo ou como pacote Python.
- `CHANGELOG.md` (este arquivo) e a seção “Publicando uma release” no `CONTRIBUTING.md`.
- `.gitattributes` para manter `install.sh` em LF e `*.ps1`/`*.bat` em CRLF independentemente do sistema do contribuidor.
- 9 novos testes (instalador contra uma “release” falsa servida localmente, checksum adulterado, dry-run, desinstalação, empacotamento).

### Alterado
- Versão `0.1.0` → `0.2.0` (`pyproject.toml`, `maker_rebuild.__version__`, runtime `MR.version`).
- `pyproject.toml`: licença em formato SPDX (`license = "MIT"`) e `setuptools>=77` (remove o aviso de depreciação no `pip install`).
- README (pt-BR e en): nova seção de instalação com as três formas (executável, instalador via Python, `pip`).

### Limitações
- Os executáveis de **Windows e macOS são compilados pelo CI** na primeira release; só o binário e o instalador de **Linux** foram executados localmente
  durante o desenvolvimento. Os scripts `install.ps1`/`install.bat` passam por verificações estáticas nos testes e por um job de CI no Windows.
- Os executáveis **não são assinados digitalmente**: o Windows SmartScreen e o Gatekeeper do macOS podem exibir um aviso na primeira execução.
- Windows em ARM não tem executável pronto (o instalador cai para o modo Python).

## [0.1.0] - 2026-11-03

Primeira versão pública (alfa).

### Adicionado
- CLI `maker-rebuild` em Python 3.9+ **sem dependências**, com os comandos `analyze`, `recompile`, `expand`, `improve`, `translate`, `port`,
  `validate`, `serve`, `providers`, `doctor`, `config`, `prompt`, `demo` e um terminal interativo (`shell`).
- **Leitores de projeto**: RPG Maker MV/MZ (JSON, descriptografia `.rpgmvp/.rpgmvm/.rpgmvo` e `.png_/.m4a_/.ogg_`), VX Ace/VX/XP
  (leitor próprio de *Ruby Marshal* + arquivos `.rgss3a/.rgss2a/.rgssad`) e um leitor LCF mínimo para 2000/2003.
- **Builder**: estrutura `game-x/` (`code/{html,css,js}`, `assets/{sprites,background,ui-ux,music,sfx}`, `Game.html` que abre via `file://`),
  entrega em `.zip` determinístico, relatório de validação e manifesto com histórico.
- **Runtime em HTML5 Canvas** (sem frameworks): tilemap com autotiles, personagens e rotas de movimento, interpretador de eventos,
  janelas com o `Window.png` do jogo, batalha por turnos, loja, menu, save/load, áudio e efeitos de tela.
- **IA frontier e local** sem SDKs (streaming, *retry*): Anthropic, OpenAI, Gemini, OpenRouter, Ollama, LM Studio, llama.cpp, vLLM,
  servidores compatíveis com OpenAI e um provedor `mock` offline. System prompt do projeto embutido.
- **Fluxos de IA**: esclarecer → planejar → expandir/melhorar (patch `MR-PATCH v1` validado e aplicado atomicamente), tradução com
  proteção de códigos de controle, porte de scripts Ruby/plugins, DSL de eventos que compila para comandos MV.
- 94 testes (leitores, builder, patches, tradução, provedores contra servidor HTTP falso e jogabilidade real em Chromium headless), CI e documentação
  (`README.md`, `README.en.md`, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`).

### Limitações
- XP, VX e 2000/2003 são experimentais; autotiles A1/A3/A4 sem validação com arte real; plugins MV/MZ só via `port`;
  batalha sem animações/estados/elementos; menu sem habilidades/equipamento. Detalhes no README.

[Não lançado]: https://github.com/KMC1525/MAKER-Rebuild/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/KMC1525/MAKER-Rebuild/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/KMC1525/MAKER-Rebuild/releases/tag/v0.1.0
