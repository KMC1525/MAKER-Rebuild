"""Terminal interativo (REPL): comandos com / e linguagem natural roteada pela IA."""
from __future__ import annotations

import shlex
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import __version__, dropin, ui
from .config import PROVIDERS, Config

try:  # histórico de linha, quando disponível
    import readline  # noqa: F401
except ImportError:  # pragma: no cover
    readline = None  # type: ignore[assignment]

HELP = """\
ARRASTE E SOLTE na janela: .zip ou pasta do jogo (original ou já recompilado) e, se quiser, roteiro/GDD (.md .txt .csv .json).
Depois de soltar, escolha o próximo passo pelo número do menu — ou escreva um pedido em linguagem natural (com IA configurada).

comandos:
  /open <caminho>          abre um projeto RPG Maker (pasta/.zip) ou jogo já recompilado (aceita o caminho colado/arrastado)
  /docs [caminhos|clear]   documentos do autor (GDD, roteiro, fichas) usados como contexto da IA
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
    def __init__(self, cfg: Config, path: Optional[str] = None, paths: Optional[List[str]] = None):
        self.cfg = cfg
        self.path = path
        self.source: Optional[str] = None            # projeto original (para recompilar de novo)
        self.kind = ""                               # project | built
        self.engine = ""
        self.docs: List[str] = []
        self.menu: List[Tuple[str, Callable[[], None]]] = []
        self.initial = list(paths or [])
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
            raise RuntimeError("nenhum projeto aberto — solte o .zip/pasta aqui ou use /open <caminho>")
        return self.path

    def original(self) -> str:
        """Projeto original para (re)compilar: o que foi solto, mesmo depois de já ter gerado o jogo."""
        return self.source or self.require_path()

    def opts(self, instruction: str = "", **kw: Any) -> Any:
        from .pipeline import Options, read_docs
        return Options(out_dir=Path(self.out), instruction=instruction, interactive=True, extra_notes=read_docs(self.docs), **kw)

    # -------------------------------------------------------------- arrastar e soltar
    def ask_request(self, question: str) -> str:
        """Pergunta ao usuário; se ele soltar documentos em vez de escrever, anexa-os e pergunta de novo."""
        for _ in range(3):
            ans = ui.ask(question, "").strip()
            if ans and dropin.looks_like_path(ans):
                items, _missing = dropin.classify_all(ans)
                self._add_docs([d for d in items if d.kind == "docs"])
                if not any(d.kind == "docs" for d in items):
                    ui.warn("aqui eu espero o texto do pedido (documentos .md/.txt/.csv/.json são anexados como contexto)")
                continue
            return ans
        return ""

    def _add_docs(self, docs: List[dropin.Dropped]) -> int:
        n = 0
        for d in docs:
            if str(d.path) not in self.docs:
                self.docs.append(str(d.path))
                n += 1
                ui.ok(f"documento anexado: {d.path.name}")
        return n

    def drop(self, text: str) -> None:
        """Texto colado pelo terminal (arrastar e soltar) → abre o jogo/documentos e mostra os próximos passos."""
        items, missing = dropin.classify_all(text)
        self.apply_drop(items, missing)

    def apply_drop(self, items: List[dropin.Dropped], missing: List[Path]) -> None:
        for m in missing:
            ui.warn(f"não encontrei: {m}")
        added = 0
        for d in items:
            if d.kind in ("built", "project"):
                label = "jogo já recompilado" if d.kind == "built" else f"projeto original ({d.engine})"
                ui.ok(f"{label}: {d.path}")
            elif d.kind == "docs":
                added += self._add_docs([d])
            else:
                ui.warn(f"{d.path.name}: {d.detail}")
        mains = [d for d in items if d.kind in ("built", "project")]
        if len(mains) > 1:
            ui.warn(f"vários jogos soltos; vou usar o último: {mains[-1].path.name}")
        main = dropin.pick_main(items)
        if main:
            self.path, self.kind, self.engine = str(main.path), main.kind, main.engine
            self.source = str(main.path) if main.kind == "project" else None
            self.last_game = None
        if main or added or self.path:
            self.show_menu()

    # -------------------------------------------------------------- menu de próximos passos
    def build_menu(self) -> List[Tuple[str, Callable[[], None]]]:
        d = self.dispatch
        if self.kind == "project":
            return [
                ("Analisar a estrutura (sem IA, não altera nada)", lambda: d("analyze", "")),
                ("Recompilar fielmente para HTML/CSS/JS (sem IA) → .zip", lambda: d("recompile", "")),
                ("Recompilar com um pedido (IA): traduzir, melhorar, expandir…",
                 lambda: self._with_request("O que você quer? (ex.: traduzir para inglês e adicionar um chefe)", lambda r: d("recompile", r))),
                ("Portar scripts Ruby / plugins para JS (IA)", lambda: d("port", "")),
            ]
        return [
            ("Validar o jogo (estrutura, assets, comandos)", lambda: d("validate", "")),
            ("Jogar no navegador (servidor local)", lambda: d("serve", "")),
            ("Expandir: adicionar conteúdo/sistemas (IA)", lambda: self._with_request("O que adicionar?", lambda r: d("expand", r))),
            ("Melhorar: balanceamento, UI, correções (IA)", lambda: d("improve", self.ask_request("Foco da melhoria (Enter = geral)"))),
            ("Traduzir (IA)", lambda: self._with_request("Para qual idioma? (ex.: en, es, pt-BR)", lambda r: d("translate", r))),
            ("Portar scripts Ruby / plugins para JS (IA)", lambda: d("port", "")),
        ]

    def _with_request(self, question: str, fn: Callable[[str], Any]) -> None:
        req = self.ask_request(question)
        if not req:
            ui.warn("cancelado (nenhum pedido informado)")
            return
        fn(req)

    def show_menu(self) -> None:
        if not self.path:
            ui.info("Solte (arraste) aqui o .zip ou a pasta do jogo para começar.")
            return
        self.menu = self.build_menu()
        ui.heading("Próximo passo")
        for i, (label, _fn) in enumerate(self.menu, 1):
            print(f"  {ui.c(str(i), 'magenta', 'bold')}) {label}")
        extra = f" · {len(self.docs)} documento(s) anexado(s)" if self.docs else ""
        print(ui.c(f"  digite o número, um pedido em linguagem natural, ou solte mais arquivos (roteiro/GDD){extra}", "gray"))

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
            if not rest.strip():
                raise RuntimeError("uso: /open <caminho>  (ou apenas arraste o .zip/pasta para a janela)")
            self.drop(rest)
        elif c == "docs":
            arg = rest.strip()
            if arg.lower() == "clear":
                self.docs.clear()
                ui.ok("documentos removidos")
            elif arg:
                items, missing = dropin.classify_all(arg)
                for m in missing:
                    ui.warn(f"não encontrei: {m}")
                if not self._add_docs([d for d in items if d.kind == "docs"]):
                    ui.warn("nenhum documento válido (.md .txt .csv .json .tsv .yaml .html)")
            else:
                ui.kv([(f"doc {i}", p) for i, p in enumerate(self.docs, 1)] or [("docs", "(nenhum — arraste um roteiro/GDD para a janela)")])
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
            self.show_menu()
        elif c == "validate":
            from .build.builtgame import open_built_game
            from .build.validate import validate_game
            target = str(self.last_game) if self.last_game else self.require_path()
            pipeline.print_validation(validate_game(open_built_game(target)))
            self.show_menu()
        elif c == "recompile":
            wants_ai = bool(rest.strip())
            o = self.opts(rest.strip())
            o.use_ai = wants_ai
            res = pipeline.recompile(self.original(), o, self.cfg, self.get_ai() if wants_ai else None)
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
        # continua o fluxo: a partir daqui o jogo recompilado passa a ser o "projeto aberto"
        if self.kind == "project" and not self.source:
            self.source = self.path
        self.path, self.kind = str(res.game_dir), "built"
        self.show_menu()

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
    COMMANDS = {"quit", "exit", "q", "sair", "help", "h", "?", "ajuda", "status", "open", "docs", "out", "provider", "model",
                "analyze", "validate", "recompile", "expand", "improve", "translate", "port", "serve"}
    WORDS = {"help", "quit", "exit", "status", "sair", "ajuda"}

    def handle(self, line: str) -> bool:
        """Processa uma linha digitada/colada. Devolve False para sair."""
        line = line.strip()
        if not line:
            return True
        if line.startswith("/"):                       # '/comando' — mas '/home/ana/jogo.zip' é um caminho solto!
            cmd, _, rest = line[1:].partition(" ")
            if cmd.lower() in self.COMMANDS:
                return self.dispatch(cmd, rest)
        elif line.lower() in self.WORDS:
            return self.dispatch(line.lower(), "")
        if line.isdigit() and self.menu:
            n = int(line)
            if 1 <= n <= len(self.menu):
                self.menu[n - 1][1]()
                return True
            raise RuntimeError(f"escolha de 1 a {len(self.menu)}")
        if dropin.looks_like_path(line):
            self.drop(line)
            return True
        self.natural(line)
        return True

    def run(self) -> None:
        print(ui.banner(__version__))
        print(ui.c("  arraste o .zip (ou a pasta) do jogo para esta janela · /help · Ctrl+D sai\n", "gray"))
        if self.initial:
            try:
                items = [dropin.classify(Path(dropin.clean_path(a))) for a in self.initial]
                self.apply_drop([d for d in items if d.path.exists()], [d.path for d in items if not d.path.exists()])
            except Exception as e:  # noqa: BLE001
                ui.err(str(e))
        elif self.path:
            self.drop(f'"{self.path}"')
        else:
            ui.info("Solte aqui o .zip ou a pasta do jogo (e, se tiver, o roteiro/GDD) para começar.")
        while True:
            try:
                line = input(ui.c("maker-rebuild", "magenta", "bold") + ui.c(" › ", "gray"))
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                if not self.handle(line):
                    break
            except KeyboardInterrupt:
                ui.err("interrompido")
            except SystemExit:
                raise
            except Exception as e:  # noqa: BLE001
                ui.err(str(e))
