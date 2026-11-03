"""Interface de linha de comando do MAKER-Rebuild."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import socketserver
import sys
import threading
from pathlib import Path
from typing import Any, List, Optional

from . import __version__, ui
from .config import ALIASES, PROVIDERS, Config, config_dir, load_config, save_config

EXAMPLES = """\
exemplos:
  maker-rebuild analyze ./MeuJogo                      mapeia o projeto (sem IA)
  maker-rebuild recompile ./MeuJogo.zip -o dist        conversão fiel para HTML/CSS/JS (.zip pronto)
  maker-rebuild recompile ./MeuJogo -i "traduza para inglês" --provider ollama --model qwen2.5:14b
  maker-rebuild expand dist/meu-jogo.zip "adicione uma dungeon com chefe e 3 itens" --provider anthropic
  maker-rebuild translate dist/meu-jogo.zip --to en --provider openai --glossary nomes.csv
  maker-rebuild port ./JogoVXAce --provider gemini     converte scripts Ruby/plugins para JS
  maker-rebuild serve dist/meu-jogo.zip                joga no navegador (servidor local)
  maker-rebuild demo && maker-rebuild recompile demo-mv  testa tudo com um jogo de exemplo embutido
  maker-rebuild                                        abre o terminal interativo
"""


# ---------------------------------------------------------------------------------- helpers
def add_ai_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("IA (frontier ou local)")
    g.add_argument("--provider", help=f"provedor: {', '.join(PROVIDERS)} (padrão: config/ambiente)")
    g.add_argument("--model", help="nome do modelo")
    g.add_argument("--base-url", help="URL base (servidores locais / compatíveis com OpenAI)")
    g.add_argument("--temperature", type=float)
    g.add_argument("--max-tokens", type=int, help="limite de tokens de saída por chamada")
    g.add_argument("--num-ctx", type=int, help="janela de contexto (Ollama)")
    g.add_argument("--no-cache", action="store_true", help="não reutilizar respostas anteriores")


def add_common(p: argparse.ArgumentParser, out: bool = True) -> None:
    if out:
        p.add_argument("-o", "--out", default="dist", help="pasta de saída (padrão: dist)")
        p.add_argument("-n", "--name", help="nome da pasta/zip do jogo (padrão: título)")
    p.add_argument("--docs", nargs="*", default=[], metavar="ARQ", help="documentos do autor (GDD, roteiro, fichas) .txt/.md/.csv/.json")
    p.add_argument("-y", "--yes", action="store_true", help="não perguntar nada (usa padrões razoáveis)")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--skip-syntax-check", action="store_true", help="não rodar node --check nos JS")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="maker-rebuild", description="Recompila, melhora e expande jogos de RPG Maker (2000 → MZ) "
                                 "para HTML + CSS + JS com ajuda de IAs generativas (frontier ou locais).",
                                 epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"maker-rebuild {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("analyze", help="mapeia o projeto: engine, mapas, eventos, assets, plugins, riscos")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-color", action="store_true")

    p = sub.add_parser("recompile", help="converte um projeto RPG Maker (pasta/.zip) em um jogo HTML5 + .zip")
    p.add_argument("path")
    p.add_argument("-i", "--instruction", default="", help="pedido livre (ex.: 'traduzir para inglês e adicionar um chefe') — requer IA")
    p.add_argument("--ai", action="store_true", help="usa IA para esclarecer/planejar/portar scripts")
    p.add_argument("--translate-to", metavar="IDIOMA")
    p.add_argument("--from", dest="translate_from", default="", metavar="IDIOMA")
    p.add_argument("--port", action="store_true", help="porta scripts Ruby/plugins para JS (IA)")
    p.add_argument("--convert-audio", action="store_true", help="converte MIDI/WMA para OGG (ffmpeg/fluidsynth)")
    p.add_argument("--ui-lang", help="idioma da UI própria do runtime (pt-BR, en, es)")
    p.add_argument("--review", action="store_true", help="revisão final por IA")
    p.add_argument("--max-features", type=int, default=6)
    add_common(p)
    add_ai_args(p)

    for name, hlp in (("expand", "adiciona conteúdo/sistemas ao jogo (IA)"), ("improve", "melhorias seguras: balanceamento, UI, correções (IA)")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("path", help="jogo recompilado (pasta/.zip) ou projeto original")
        p.add_argument("request", nargs="?" if name == "improve" else None, default="", help="o que adicionar/melhorar")
        p.add_argument("--max-features", type=int, default=6)
        p.add_argument("--review", action="store_true")
        add_common(p)
        add_ai_args(p)

    p = sub.add_parser("translate", help="traduz diálogos, banco de dados e UI (IA)")
    p.add_argument("path")
    p.add_argument("--to", required=True, metavar="IDIOMA", help="idioma de destino (en, pt-BR, es, ja...)")
    p.add_argument("--from", dest="translate_from", default="", metavar="IDIOMA")
    p.add_argument("--tone", default="", help="tom/estilo a manter (ex.: 'jovial, gírias leves')")
    p.add_argument("--glossary", help="CSV 'termo,tradução' para nomes próprios")
    add_common(p)
    add_ai_args(p)

    p = sub.add_parser("port", help="porta scripts Ruby (VX/VXA/XP) e plugins MV/MZ para JS (IA + regras)")
    p.add_argument("path")
    p.add_argument("--no-modules", action="store_true", help="só scripts de eventos (não gera módulos ext/)")
    add_common(p)
    add_ai_args(p)

    p = sub.add_parser("validate", help="revisa um jogo gerado: estrutura, assets, referências, comandos, sintaxe JS")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--skip-syntax-check", action="store_true")

    p = sub.add_parser("serve", help="serve o jogo em http://localhost para jogar no navegador")
    p.add_argument("path")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--open", action="store_true", help="abre o navegador")

    p = sub.add_parser("providers", help="lista provedores de IA e detecta modelos locais")
    p.add_argument("--local", action="store_true", help="consulta Ollama/LM Studio/llama.cpp/vLLM em localhost")
    p.add_argument("--provider")

    p = sub.add_parser("demo", help="cria um mini-projeto RPG Maker MV de exemplo (sem arte de terceiros) para você testar a ferramenta")
    p.add_argument("dir", nargs="?", default="demo-mv")
    p.add_argument("--encrypted", action="store_true", help="gera com assets criptografados (.rpgmvp/.rpgmvo)")
    p.add_argument("--no-color", action="store_true")

    sub.add_parser("doctor", help="verifica o ambiente (python, node, ffmpeg, chaves, servidores locais)")

    p = sub.add_parser("config", help="mostra/altera a configuração persistente")
    p.add_argument("action", choices=["show", "set", "path"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")

    p = sub.add_parser("shell", help="terminal interativo")
    p.add_argument("path", nargs="?")
    add_ai_args(p)
    sub.add_parser("prompt", help="imprime o system prompt usado com a IA")
    return ap


def make_config(args: Any) -> Config:
    cfg = load_config()
    for k in ("provider", "model", "base_url", "temperature", "max_tokens"):
        v = getattr(args, k, None)
        if v is not None:
            setattr(cfg, k, v)
    if getattr(args, "num_ctx", None):
        cfg.extras["num_ctx"] = args.num_ctx
    return cfg


def make_ai(cfg: Config, args: Any) -> "Any":
    from .ai.client import AIClient
    return AIClient(cfg, use_cache=not getattr(args, "no_cache", False))


def need_ai(cfg: Config, args: Any) -> "Any":
    ai = make_ai(cfg, args)
    if ai.provider.kind == "frontier" and not ai.provider.api_key:
        envs = " ou ".join(ai.provider.spec.get("key_env", []))
        raise SystemExit(f"Provedor '{ai.provider.name}' sem chave de API. Defina {envs}, ou use um modelo local:\n"
                         f"  maker-rebuild ... --provider ollama --model <modelo>\n"
                         f"  (veja `maker-rebuild providers --local`; para testar sem IA real: --provider mock)")
    return ai


def pipeline_options(args: Any) -> "Any":
    from .pipeline import Options, read_docs
    return Options(out_dir=Path(args.out), name=args.name, instruction=getattr(args, "instruction", "") or "",
                   interactive=ui.is_interactive() and not args.yes, translate_to=getattr(args, "translate_to", None),
                   translate_from=getattr(args, "translate_from", "") or "", tone=getattr(args, "tone", "") or "",
                   glossary=getattr(args, "glossary", None), port=getattr(args, "port", False),
                   port_modules=not getattr(args, "no_modules", False), convert_audio=getattr(args, "convert_audio", False),
                   ui_lang=getattr(args, "ui_lang", None), review=getattr(args, "review", False),
                   max_features=getattr(args, "max_features", 6), check_syntax=not args.skip_syntax_check,
                   extra_notes=read_docs(args.docs))


def report_done(res: Any) -> None:
    from .pipeline import print_validation
    print_validation(res.validation)
    ui.heading("Pronto")
    ui.kv([("Jogo (pasta)", res.game_dir), ("Entrega (.zip)", res.zip_path),
           ("Jogar", f"maker-rebuild serve {res.zip_path}   (ou abra {res.game_dir}/Game.html)")])
    if not res.validation.get("ok"):
        ui.warn("há erros na validação — veja code/validation-report.json")


# ---------------------------------------------------------------------------------- comandos
def cmd_analyze(args: Any) -> int:
    from .analyze import analyze, print_report
    from .pipeline import load_any
    import tempfile
    obj = load_any(args.path, Path(tempfile.mkdtemp(prefix="maker-rebuild-")))
    rep = analyze(obj)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_report(rep)
    return 0


def cmd_recompile(args: Any) -> int:
    from . import pipeline
    cfg = make_config(args)
    opts = pipeline_options(args)
    wants_ai = bool(args.ai or args.instruction or args.translate_to or args.port or args.review)
    opts.use_ai = wants_ai
    ai = need_ai(cfg, args) if wants_ai else None
    res = pipeline.recompile(args.path, opts, cfg, ai)
    report_done(res)
    return 0 if res.validation.get("ok") else 1


def cmd_expand(args: Any, mode: str = "expand") -> int:
    from . import pipeline
    cfg = make_config(args)
    if mode == "expand" and not args.request:
        raise SystemExit("descreva o que adicionar: maker-rebuild expand <jogo> \"seu pedido\"")
    opts = pipeline_options(args)
    opts.use_ai = True
    ai = need_ai(cfg, args)
    res = pipeline.expand(args.path, args.request, opts, ai, cfg, mode)
    report_done(res)
    return 0 if res.validation.get("ok") else 1


def cmd_translate(args: Any) -> int:
    from . import pipeline
    cfg = make_config(args)
    opts = pipeline_options(args)
    opts.use_ai = True
    ai = need_ai(cfg, args)
    res = pipeline.translate(args.path, args.to, opts, ai, cfg)
    report_done(res)
    return 0 if res.validation.get("ok") else 1


def cmd_port(args: Any) -> int:
    from . import pipeline
    cfg = make_config(args)
    opts = pipeline_options(args)
    opts.use_ai = True
    ai = need_ai(cfg, args)
    res = pipeline.port(args.path, opts, ai, cfg)
    report_done(res)
    return 0 if res.validation.get("ok") else 1


def cmd_validate(args: Any) -> int:
    from .build.builtgame import open_built_game
    from .pipeline import print_validation
    g = open_built_game(args.path)
    rep = validate_report(g, not args.skip_syntax_check)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_validation(rep)
        (ui.ok if rep["ok"] else ui.err)("jogo válido" if rep["ok"] else "jogo com erros")
    return 0 if rep["ok"] else 1


def validate_report(g: Any, syntax: bool = True) -> dict:
    from .build.validate import validate_game
    return validate_game(g, check_syntax=syntax)


def find_serve_root(path: str) -> Path:
    from .build.builtgame import find_game_root, open_built_game
    p = Path(path)
    if p.is_file():
        import tempfile
        return open_built_game(path, Path(tempfile.mkdtemp(prefix="maker-rebuild-serve-"))).root
    r = find_game_root(p)
    if r is None:
        raise SystemExit("não encontrei Game.html (informe a pasta ou o .zip do jogo gerado)")
    return r


def cmd_serve(args: Any) -> int:
    root = find_serve_root(args.path)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:  # noqa: D401
            pass

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    handler = functools.partial(Quiet, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), handler) as srv:
        url = f"http://127.0.0.1:{args.port}/Game.html"
        ui.ok(f"servindo {root.name} em {url}  (Ctrl+C para parar; F9 mostra avisos do runtime)")
        if args.open:
            import webbrowser
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


def cmd_providers(args: Any) -> int:
    from .providers import make_provider
    rows = []
    for name, spec in PROVIDERS.items():
        key = "—"
        if spec["key_env"]:
            key = "✔ " + next((e for e in spec["key_env"] if os.environ.get(e)), "") if any(os.environ.get(e) for e in spec["key_env"]) else "✖ " + spec["key_env"][0]
        rows.append([name, spec["kind"], spec["model"], spec["base_url"] or "-", key])
    ui.table(["provedor", "tipo", "modelo padrão", "url base", "chave"], rows)
    print(f"\naliases: {', '.join(f'{k}→{v}' for k, v in ALIASES.items())}")
    if args.local:
        ui.heading("Servidores locais")
        for name in ("ollama", "lmstudio", "llamacpp", "vllm"):
            cfg = Config(provider=name)
            try:
                models = make_provider(cfg).list_models()
            except Exception:  # noqa: BLE001
                models = []
            if models:
                ui.ok(f"{name} ({cfg.resolved()['base_url']}): {', '.join(models[:8])}{' …' if len(models) > 8 else ''}")
            else:
                ui.info(f"{name} ({cfg.resolved()['base_url']}): não detectado")
    return 0


def cmd_demo(args: Any) -> int:
    from .demo import make_mv_project
    root = Path(args.dir)
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"{root} já existe e não está vazia")
    make_mv_project(root, encrypted=args.encrypted, title="Demo Quest")
    ui.ok(f"projeto de demonstração criado em {root}/")
    print(f"\n  maker-rebuild analyze {root}\n  maker-rebuild recompile {root} -o dist\n  maker-rebuild serve dist/demo-quest.zip\n")
    return 0


def cmd_doctor(args: Any) -> int:
    import platform
    from .providers import make_provider
    ui.heading("Ambiente")
    ok = True
    ui.kv([("Python", platform.python_version()), ("Sistema", platform.platform())])
    for tool, why in (("node", "valida a sintaxe dos JS gerados (opcional)"), ("ffmpeg", "converte áudio WMA/MIDI (opcional)"),
                      ("fluidsynth", "MIDI → OGG com soundfont (opcional)")):
        path = shutil.which(tool)
        (ui.ok if path else ui.info)(f"{tool}: {path or 'não encontrado'} — {why}")
    ui.heading("IA")
    cfg = load_config()
    ui.kv([("provedor atual", cfg.provider_name), ("modelo", cfg.resolved()["model"]), ("config", config_dir() / "config.json")])
    for name, spec in PROVIDERS.items():
        if spec["key_env"] and any(os.environ.get(e) for e in spec["key_env"]):
            ui.ok(f"chave encontrada para {name}")
    for name in ("ollama", "lmstudio", "llamacpp", "vllm"):
        try:
            ms = make_provider(Config(provider=name)).list_models()
        except Exception:  # noqa: BLE001
            ms = []
        if ms:
            ui.ok(f"{name} local ativo: {len(ms)} modelo(s)")
    return 0 if ok else 1


def cmd_config(args: Any) -> int:
    cfg = load_config()
    if args.action == "path":
        print(config_dir() / "config.json")
    elif args.action == "show":
        print(json.dumps({k: v for k, v in cfg.__dict__.items()}, ensure_ascii=False, indent=2))
    else:
        if not args.key or args.value is None:
            raise SystemExit("uso: maker-rebuild config set <chave> <valor>   (chaves: provider, model, base_url, temperature, max_tokens, timeout, language)")
        if args.key not in ("provider", "model", "base_url", "temperature", "max_tokens", "timeout", "context_chars", "language"):
            raise SystemExit(f"chave desconhecida: {args.key}. Chaves de API ficam em variáveis de ambiente, não no arquivo.")
        cur = getattr(cfg, args.key)
        setattr(cfg, args.key, type(cur)(args.value) if not isinstance(cur, str) else args.value)
        ui.ok(f"salvo em {save_config(cfg)}")
    return 0


def cmd_shell(args: Any) -> int:
    from .shell import Shell
    cfg = make_config(args) if args is not None else load_config()
    Shell(cfg, getattr(args, "path", None)).run()
    return 0


def cmd_prompt(args: Any) -> int:
    from .ai import prompts
    print(prompts.system_prompt(with_api=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if getattr(args, "no_color", False):
        ui.set_color(False)
    if not args.cmd:
        if sys.stdin.isatty():
            return cmd_shell(None)
        ap.print_help()
        return 0
    handlers = {"analyze": cmd_analyze, "recompile": cmd_recompile, "expand": cmd_expand, "improve": lambda a: cmd_expand(a, "improve"),
                "translate": cmd_translate, "port": cmd_port, "validate": cmd_validate, "serve": cmd_serve, "providers": cmd_providers,
                "doctor": cmd_doctor, "demo": cmd_demo, "config": cmd_config, "shell": cmd_shell, "prompt": cmd_prompt}
    try:
        return handlers[args.cmd](args)
    except KeyboardInterrupt:
        ui.err("interrompido")
        return 130
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — erros esperados viram mensagens limpas
        from .ai.client import AIOutputError
        from .build.builtgame import BuiltGameError
        from .project import ProjectError
        from .providers import LLMError
        if isinstance(e, (ProjectError, BuiltGameError, LLMError, AIOutputError, FileNotFoundError, ValueError)):
            ui.err(str(e))
            if os.environ.get("MAKER_REBUILD_DEBUG"):
                raise
            return 2
        raise


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
