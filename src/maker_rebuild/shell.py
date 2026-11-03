"""Terminal interativo (REPL): comandos com / e linguagem natural roteada pela IA."""
from __future__ import annotations

import shlex
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__, ui
from .config import PROVIDERS, Config

try:  # histórico de linha, quando disponível
    import readline  # noqa: F401
except ImportError:  # pragma: no cover
    readline = None  # type: ignore[assignment]

HELP = """\
comandos (também aceito linguagem natural quando há IA configurada):
  /open <caminho>          abre um projeto RPG Maker (pasta/.zip) ou jogo já recompilado
  /analyze                 mapeia estrutura, riscos e cobertura do runtime
  /recompile [pedido]      converte para HTML/CSS/JS (+ etapas de IA se houver pedido)
  /expand <pedido>         adiciona conteúdo/sistemas (IA)
  /improve [pedido]        melhorias seguras (IA)
  /translate <idioma>      traduz o jogo (IA)
  /port                    porta scripts Ruby/plugins para JS (IA)
  /validate                revisa o jogo gerado
  /serve                   joga no navegador (Ctrl+C volta ao terminal)
  /provider <nome> [modelo]   troca de IA (anthropic, openai, gemini, openrouter, ollama, lmstudio, llamacpp, mock…)
  /model <modelo>          troca só o modelo      /out <pasta>   pasta de saída
  /status                  estado atual           /help          esta ajuda          /quit   sair
"""


class Shell:
    def __init__(self, cfg: Config, path: Optional[str] = None):
        self.cfg = cfg
        self.path = path
        self.out = "dist"
        self.last_game: Optional[Path] = None
        self.ai = None
        self.work = Path(tempfile.mkdtemp(prefix="maker-rebuild-shell-"))

    # -------------------------------------------------------------- infra
    def get_ai(self) -> Any:
        from .ai.client import AIClient
        if self.ai is None or self.ai.cfg is not self.cfg:
            self.ai = AIClient(self.cfg)
        p = self.ai.provider
        if p.kind == "frontier" and not p.api_key:
            raise RuntimeError(f"sem chave para '{p.name}': defina {' ou '.join(p.spec['key_env'])} ou troque de provedor "
                               f"(/provider ollama)")
        return self.ai

    def status(self) -> None:
        spec = self.cfg.resolved()
        ui.kv([("projeto", self.path or "(nenhum — use /open)"), ("saída", self.out), ("IA", f"{self.cfg.provider_name} / {spec['model']}"),
               ("último jogo", self.last_game or "-")])

    def require_path(self) -> str:
        if not self.path:
            raise RuntimeError("nenhum projeto aberto — use /open <caminho>")
        return self.path

    def opts(self, instruction: str = "", **kw: Any) -> Any:
        from .pipeline import Options
        return Options(out_dir=Path(self.out), instruction=instruction, interactive=True, **kw)

    # -------------------------------------------------------------- comandos
    def dispatch(self, cmd: str, rest: str) -> bool:
        from . import pipeline
        c = cmd.lower()
        if c in ("quit", "exit", "q", "sair"):
            return False
        if c in ("help", "h", "?", "ajuda"):
            print(HELP)
        elif c == "status":
            self.status()
        elif c == "open":
            p = Path(rest.strip().strip('"\'')).expanduser()
            if not p.exists():
                raise RuntimeError(f"caminho não encontrado: {p}")
            self.path = str(p)
            ui.ok(f"aberto: {p}")
        elif c == "out":
            self.out = rest.strip() or self.out
            ui.ok(f"saída: {self.out}")
        elif c == "provider":
            parts = rest.split()
            if not parts:
                print(", ".join(PROVIDERS))
            else:
                self.cfg.provider = parts[0]
                self.cfg.model = parts[1] if len(parts) > 1 else ""
                self.cfg.base_url = ""
                ui.ok(f"IA: {self.cfg.provider_name} / {self.cfg.resolved()['model']}")
        elif c == "model":
            self.cfg.model = rest.strip()
            ui.ok(f"modelo: {self.cfg.resolved()['model']}")
        elif c == "analyze":
            from .analyze import analyze, print_report
            print_report(analyze(pipeline.load_any(self.require_path(), self.work)))
        elif c == "validate":
            from .build.builtgame import open_built_game
            from .build.validate import validate_game
            target = str(self.last_game) if self.last_game else self.require_path()
            pipeline.print_validation(validate_game(open_built_game(target)))
        elif c == "recompile":
            wants_ai = bool(rest.strip())
            o = self.opts(rest.strip())
            o.use_ai = wants_ai
            res = pipeline.recompile(self.require_path(), o, self.cfg, self.get_ai() if wants_ai else None)
            self.finish(res)
        elif c in ("expand", "improve"):
            if c == "expand" and not rest.strip():
                raise RuntimeError("descreva o que adicionar: /expand <pedido>")
            o = self.opts(rest.strip())
            o.use_ai = True
            res = pipeline.expand(self.require_path(), rest.strip(), o, self.get_ai(), self.cfg, c)
            self.finish(res)
        elif c == "translate":
            if not rest.strip():
                raise RuntimeError("informe o idioma: /translate en")
            o = self.opts()
            o.use_ai = True
            self.finish(pipeline.translate(self.require_path(), rest.strip(), o, self.get_ai(), self.cfg))
        elif c == "port":
            o = self.opts()
            o.use_ai = True
            self.finish(pipeline.port(self.require_path(), o, self.get_ai(), self.cfg))
        elif c == "serve":
            from .cli import find_serve_root, cmd_serve
            import argparse
            target = str(self.last_game) if self.last_game else self.require_path()
            cmd_serve(argparse.Namespace(path=target, port=8000, open=False))
        else:
            raise RuntimeError(f"comando desconhecido: /{cmd}  (veja /help)")
        return True

    def finish(self, res: Any) -> None:
        from .cli import report_done
        self.last_game = res.game_dir
        report_done(res)

    # -------------------------------------------------------------- linguagem natural
    def natural(self, text: str) -> None:
        from .ai import prompts
        ai = self.get_ai()
        ctx = f"Projeto aberto: {self.path or 'nenhum'}. Último jogo gerado: {self.last_game or 'nenhum'}."
        data = ai.ask_json("route", f"{ctx}\nFrase do usuário: {text}", extra_system=prompts.ROUTE_TASK, desc="interpretando")
        action = str(data.get("action", "help")) if isinstance(data, dict) else "help"
        args: Dict[str, Any] = (data.get("args") or {}) if isinstance(data, dict) else {}
        say = data.get("say") if isinstance(data, dict) else None
        if say:
            print(ui.c(str(say), "cyan"))
        if args.get("path") and not self.path:
            self.path = str(args["path"])
        arg = str(args.get("request") or args.get("lang") or "")
        if action in ("help", "status", "quit", "analyze", "validate", "serve", "port"):
            self.dispatch(action, "")
        elif action in ("recompile", "expand", "improve", "translate"):
            if ui.confirm(f"executar /{action} {arg}".strip() + "?", True):
                self.dispatch(action, arg)

    # -------------------------------------------------------------- laço
    def run(self) -> None:
        print(ui.banner(__version__))
        print(ui.c("  digite /help para ver os comandos · Ctrl+D sai\n", "gray"))
        if self.path:
            ui.ok(f"aberto: {self.path}")
        while True:
            try:
                line = input(ui.c("maker-rebuild", "magenta", "bold") + ui.c(" › ", "gray")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            try:
                if line.startswith("/") or line.split()[0].lower() in ("help", "quit", "exit", "status"):
                    cmd, _, rest = line.lstrip("/").partition(" ")
                    if not self.dispatch(cmd, rest):
                        break
                elif Path(line.strip('"\'')).expanduser().exists():
                    self.dispatch("open", line)
                else:
                    self.natural(line)
            except KeyboardInterrupt:
                ui.err("interrompido")
            except SystemExit:
                raise
            except Exception as e:  # noqa: BLE001
                ui.err(str(e))
