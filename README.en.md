<div align="center">

# MAKER-Rebuild

**Rebuild, improve and expand RPG Maker games (2000 → MZ) as HTML + CSS + JS, with the help of generative AI — frontier or local models.**

[![CI](https://github.com/kmc1525/MAKER-Rebuild/actions/workflows/ci.yml/badge.svg)](https://github.com/kmc1525/MAKER-Rebuild/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![deps](https://img.shields.io/badge/dependencies-zero-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)
![status](https://img.shields.io/badge/status-alpha-orange)

**English** · [Português](README.md) · [Changelog](CHANGELOG.md)

</div>

---

## What is it

**MAKER-Rebuild** is a **Python command-line tool** that takes a game made with RPG Maker and delivers a **self-contained web game**
(`Game.html` + CSS + JS + assets) inside a `.zip` — no NW.js, no Electron, no proprietary plugin, no heavy framework: just **HTML5 Canvas**.

It does three things:

1. **Rebuilds** — reads the original project (`Data/`, `img/`, `audio/`, `.rpgmvp`, `.rgss3a`…), decrypts assets, maps maps/events/database/plugins
   and generates a faithful HTML/CSS/JS version.
2. **Improves** — fixes, modernizes and rebalances (data, UI theme, JS modules) with an AI's help.
3. **Expands** — adds new content (maps, NPCs, items, enemies, quests, systems) coherently with the game, from a natural-language request,
   a script/GDD or spreadsheets.

It also **translates** the whole game (dialogue, database, system terms) while preserving control codes (`\C[2]`, `\V[1]`, `\N[1]`…).

The agent's behaviour is defined by the [project system prompt](src/maker_rebuild/prompts/system_base.md) (in Portuguese): fidelity to the
original first, clean code, keep variable/switch/event names, and **ask before assuming** when critical information is missing.

> **Status: alpha.** **MV, MZ and VX Ace** conversion works end-to-end and is tested in a real browser. XP, VX and 2000/2003 are
> **experimental** (see the [support matrix](#support-by-engine)). Read [Known limitations](#known-limitations) first.

## Install

Pick one — all of them give you the `maker-rebuild` command.

### 1) Standalone executable (no Python needed) — Windows · macOS · Linux

**Linux & macOS** (`sh`):

```bash
curl -fsSL https://raw.githubusercontent.com/KMC1525/MAKER-Rebuild/main/install.sh | sh
```

**Windows** (PowerShell):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/KMC1525/MAKER-Rebuild/main/install.ps1))) -Mode auto
```

Or, with the repo cloned, double-click `install.bat` (or run `install.bat --exe`).

The installer downloads the executable from the [latest release](https://github.com/KMC1525/MAKER-Rebuild/releases/latest) for your platform
(`linux`/`macos`/`windows` × `x86_64`/`arm64`), **verifies its SHA-256 checksum**, installs it to `~/.local/bin` (Windows: `%LOCALAPPDATA%\MAKER-Rebuild\bin`, added to your `PATH`).
If there is no release yet it falls back to the Python mode (item 2) by itself.

| option (`sh` / PowerShell) | effect |
|---|---|
| `--exe` / `-Mode exe` · `--python` / `-Mode python` | force the executable or the Python environment |
| `--prefix DIR` / `-Prefix DIR` | install location (default `~/.local` · `%LOCALAPPDATA%\MAKER-Rebuild`) |
| `--version X.Y.Z` / `-Version X.Y.Z` | specific release |
| `--dry-run` / `-DryRun` | show what would happen, change nothing |
| `--uninstall` / `-Uninstall` | remove (user config and cache are kept) |

> **OS security prompts:** executables are **not code-signed yet**. Windows SmartScreen may warn ("unknown publisher" → *More info* → *Run anyway*); on macOS the installer
> clears the quarantine flag, and for a manual download use `xattr -d com.apple.quarantine maker-rebuild`. If you'd rather not trust binaries, use option 2 or 3.

### 2) Python installer (isolated virtual environment)

Needs **Python 3.9+**; no Python dependencies.

```bash
git clone https://github.com/KMC1525/MAKER-Rebuild.git && cd MAKER-Rebuild
sh install.sh --python        # Windows: install.bat --python
```

### 3) `pip` / `pipx`

```bash
pip install -e .
pipx install git+https://github.com/KMC1525/MAKER-Rebuild.git
```

Optional for all: `node` (syntax-checks generated JS), `ffmpeg` (WMA/MIDI → OGG). Check your setup with `maker-rebuild doctor`.
Build your own executable: `pip install -e ".[exe]" && python packaging/build_exe.py`.

## Try it in one minute (no game needed)

```bash
maker-rebuild demo                               # creates ./demo-mv (a synthetic RPG Maker MV project)
maker-rebuild analyze demo-mv
maker-rebuild recompile demo-mv -o dist          # → dist/demo-quest/ and dist/demo-quest.zip
maker-rebuild serve dist/demo-quest.zip --open   # play it in the browser
maker-rebuild expand dist/demo-quest.zip "add a potion and an NPC" --provider mock -o dist2   # offline, no key
```

## Real usage

```bash
maker-rebuild analyze ./MyGame                    # folder or .zip; project root, www/ or parent folder
maker-rebuild recompile ./MyGame -o dist          # faithful conversion (no AI)
maker-rebuild validate dist/mygame.zip
export ANTHROPIC_API_KEY=...                      # or OPENAI_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY
maker-rebuild translate dist/mygame.zip --to en --glossary examples/glossary.csv
maker-rebuild port ./MyVXAceGame                  # Ruby scripts / MV-MZ plugins → JS
maker-rebuild improve dist/mygame.zip "rebalance early difficulty and make the menu more readable"
maker-rebuild expand dist/mygame.zip "add an ice dungeon with a boss, 3 items and a quest" --docs script.md sheets.csv
maker-rebuild recompile ./MyGame -i "translate to English and add a secret boss" --provider ollama --model qwen2.5:14b
maker-rebuild                                     # interactive terminal (/open, /analyze, /recompile, natural language…)
```

### Drag & drop (continue where you left off)

No need to type paths. **Drag the game's `.zip` (or folder) onto the terminal window** — the terminal pastes the path, MAKER-Rebuild recognises what it is and
shows a numbered menu of next steps (original project → analyze / faithful rebuild / rebuild with an AI request / port scripts; already-rebuilt game → validate / play / expand / improve /
translate / port). After each step the flow **continues**: the freshly built game becomes the open project and the next menu appears.

- Understands each terminal's format (macOS `My\ Game.zip`, GNOME `'…'`/`file://…`, cmd `"C:\…"`, PowerShell `& '…'`), several items at once, and paths with spaces.
- Drop your **script/GDD/sheets** too (`.md .txt .csv .json`): they become AI context (`/docs` lists or clears them), even in the middle of a question ("What to add?").
- You can drop an **already-rebuilt game** and continue from there.
- **Dragging a file onto the executable/shortcut** (or `maker-rebuild game.zip [script.md …]`) opens the terminal with everything loaded.
- `analyze`, `recompile`, `translate`, `port`, `validate` and `serve` ask "Drag the .zip here…" when the path is omitted.

| command | what it does | AI |
|---|---|:-:|
| `analyze` | engine, maps, events, database, assets, plugins, risks, runtime coverage (`--json`) | – |
| `recompile` | converts to HTML/CSS/JS and builds the `.zip`; `-i "request"` chains translate/port/expand | optional |
| `expand` / `improve` | add content & systems / safe improvements (balance, theme/UI, fixes) | ✔ |
| `translate --to LANG` | translates dialogue, database and UI preserving control codes | ✔ |
| `port` | ports Ruby (VX/VXA/XP) scripts and MV/MZ plugins to JS modules | ✔ |
| `validate` · `serve` · `providers` · `doctor` · `config` · `prompt` · `demo` · `shell` | utilities | – |

## Delivered structure

```
mygame.zip
└── mygame/
    ├── Game.html                 ← open it and play (works over file://)
    ├── code/{html,css,js}/       js/: mr-*.js runtime · data/ · ext/ (AI-generated modules) · plugins/_original · scripts-ruby
    └── assets/{sprites,background,ui-ux,music,sfx}/
```

plus `code/validation-report.json`, `code/rebuild-manifest.json` (history of everything done to the game) and, when the AI asks for new art,
`code/assets-todo.md` with generated **placeholders**.

## How it works

Deterministic readers (MV/MZ JSON, a custom **Ruby Marshal** reader for VX Ace/VX/XP — nothing is executed —, `.rgssad/.rgss2a/.rgss3a`
archives, MV/MZ asset decryption, a minimal LCF reader for 2000/2003) → a common **IR in MV naming** → builder + a **custom Canvas runtime**
(tilemap with autotiles, characters, collision, event interpreter, windows using the game's own `Window.png`, turn-based battle driven by
the database formulas, shop, menu, save/load, audio, screen effects).

**AI works through contracts**: it never writes into the game directly. It returns **JSON** (a `MR-PATCH v1` patch, translation batches, port batches);
the CLI **validates everything** (shapes, ids, bounds, paths, `node --check` on all JS) and applies it **atomically** (any failure → nothing applied),
retrying with the validation errors as feedback. Events are described through a small **DSL** (`{"say": …}`, `{"if": …}`, `{"battle": …}`)
compiled into correct RPG Maker commands — see the [contract](src/maker_rebuild/prompts/runtime_api.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (Portuguese).

## Supported AI (frontier and local)

No SDKs: plain HTTP with streaming, retries/backoff, and rejected parameters are dropped and the call is retried.

| provider | type | env var | example |
|---|---|---|---|
| `anthropic` | frontier | `ANTHROPIC_API_KEY` | `--provider anthropic --model claude-sonnet-5-5` |
| `openai` | frontier | `OPENAI_API_KEY` | `--provider openai --model gpt-4.1` |
| `gemini` | frontier | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `--provider gemini --model gemini-2.5-pro` |
| `openrouter` | frontier (aggregator) | `OPENROUTER_API_KEY` | `--provider openrouter --model <vendor/model>` |
| `ollama` · `lmstudio` · `llamacpp` · `vllm` | **local** | – | `--provider ollama --model qwen2.5:14b` |
| `openai-compat` | local/any | `OPENAI_COMPAT_API_KEY` | `--provider openai-compat --base-url http://host:port/v1` |
| `mock` | offline (testing) | – | deterministic synthetic responses |

Default models are only suggestions — use `--model`. **API keys are never written to disk.** Responses are cached in `~/.cache/maker-rebuild`.
`maker-rebuild providers --local` detects local servers.

**About adult/violent content:** the project's system prompt tells the agent to work without restrictions on SFW and NSFW games and not to
refuse, censor or add warnings to game text. Note that **hosted providers enforce their own usage policies** and may refuse a request
(the CLI says so clearly). If that matters for your project, use a **local model**.

## Support by engine

| engine | read | encrypted assets | maps/tiles | events | database | status |
|---|---|---|---|---|---|---|
| **MV** | JSON | `.rpgmvp/.rpgmvm/.rpgmvo` ✔ | A1–A4 autotiles, shadows, regions | ✔ | full | **stable** |
| **MZ** | JSON (MV model) | `.png_/.m4a_/.ogg_` ✔ | like MV | ✔ (`357` plugin commands need `port`) | full | **good** |
| **VX Ace** | Ruby Marshal | `.rgss3a` ✔ | full (same model as MV) | ✔ (Ruby scripts → `port`) | full | **good** |
| VX | Ruby Marshal | `.rgss2a` ✔ | partial | basic | partial | experimental |
| XP | Ruby Marshal | `.rgssad` ✔ | simplified autotiles | basic | partial | experimental |
| 2000 / 2003 | LCF (maps) | n/a | raw tile layers only | ✘ (rebuild with AI) | ✘ | experimental |

In experimental engines the CLI **reports what it could not convert** instead of pretending fidelity.

## Known limitations

- **Autotiles:** ground (A2) is visually verified; water/waterfall (A1), walls (A3) and roof/wall tops (A4) follow the standard MV layout but are **not yet checked against real art**.
- **MV/MZ plugins don't run as-is** (the runtime isn't `rpg_*.js`); `port` asks the AI to port them into `code/js/ext/port-*.js` marked "AI-generated — **review**".
- **Battle:** turn-based with damage formulas/variance, enemy actions, items, escape, EXP/gold/drops. No battle animations, state effects beyond KO, elements, crits, TP, side-view or troop-page battle events yet.
- **Menu:** items, status, save, quit. No skills/equipment/formation menus yet.
- Unsupported **event commands** (e.g. animations `212`, weather `236`, vehicles, followers) are listed by `analyze`/`validate` and ignored with a warning at runtime (F9 shows warnings). Extend with `MR.ext.commands[code] = fn`.
- **MIDI/WMA** audio doesn't play in browsers — use `--convert-audio` (needs `ffmpeg`; MIDI also needs `fluidsynth` + `MAKER_REBUILD_SOUNDFONT`).
- **RTP assets** aren't inside VX/VXA/XP/2000 projects; `validate` lists what's missing.
- The test suite uses **synthetic projects** (no third-party art/games). Real games have more variety — open issues with `analyze` output (without attaching copyrighted material).

## Responsible use

Use MAKER-Rebuild with **your own games**, public-domain ones, or with the **author's permission**. The conversion is technical; **music, art and
writing remain the property of their creators**. Excerpts of the project are sent to the AI provider you choose — use local models for confidential material.

## Development

```bash
pip install -e ".[dev]" && python -m pytest -q    # 90+ tests; browser gameplay tests skip themselves without node/playwright
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Roadmap: skills/equipment menus, battle animations/states/elements, weather & map animations, full VX/XP fidelity and a
complete LCF reader, local image/audio generation for placeholders, watch mode, desktop/mobile packaging.

## Changelog

All changes are recorded in [`CHANGELOG.md`](CHANGELOG.md) (Portuguese).

## License

[MIT](LICENSE) © 2026 KMC
