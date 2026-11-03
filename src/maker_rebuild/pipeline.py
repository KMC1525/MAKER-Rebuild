"""Orquestração dos fluxos: recompilação, expansão/melhoria, tradução e porte de scripts."""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import ui
from .ai import jobs
from .ai.client import AIClient
from .ai.port import port_game
from .ai.translate import load_glossary, translate_game
from .analyze import analyze, print_report
from .build.builder import build_game, slugify
from .build.builtgame import BuiltGame, copy_game, is_built_game, open_built_game
from .build.validate import validate_game
from .build.zipper import make_zip
from .config import Config
from .project import Project, open_project


@dataclass
class Options:
    out_dir: Path = Path("dist")
    name: Optional[str] = None             # nome da pasta/zip (padrão: slug do título)
    instruction: str = ""                  # pedido livre do usuário
    use_ai: bool = False
    interactive: bool = False
    translate_to: Optional[str] = None
    translate_from: str = ""
    tone: str = ""
    glossary: Optional[str] = None
    port: bool = False
    port_modules: bool = True
    convert_audio: bool = False
    ui_lang: Optional[str] = None
    review: bool = False
    max_features: int = 6
    keep_dir: bool = True
    check_syntax: bool = True
    extra_notes: List[str] = field(default_factory=list)   # documentos do usuário (GDD, roteiro...)
    suffix: str = ""


@dataclass
class Result:
    zip_path: Path
    game_dir: Path
    validation: Dict[str, Any]
    log: List[str] = field(default_factory=list)


def read_docs(paths: List[str]) -> List[str]:
    """Documentos do autor (GDD, roteiro, fichas...) como texto — .txt/.md/.csv/.json (outros: ignorados com aviso)."""
    out = []
    for p in paths or []:
        f = Path(p)
        if not f.exists():
            ui.warn(f"documento não encontrado: {p}")
            continue
        if f.suffix.lower() in (".txt", ".md", ".csv", ".json", ".tsv", ".html", ".htm", ".yaml", ".yml"):
            out.append(f"[{f.name}]\n" + f.read_text(encoding="utf-8", errors="replace")[:30000])
        else:
            ui.warn(f"formato não suportado para leitura direta ({f.suffix}): converta {f.name} para .txt/.md/.csv")
    return out


def _progress(i: int, n: int, label: str = "") -> None:
    ui.progress(i, n, label)


def _finish(game: BuiltGame, opts: Options, title_suffix: str, log: List[str], ai: Optional[AIClient] = None,
            history: Optional[Dict[str, Any]] = None) -> Result:
    game.save()
    if history:
        history["at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        game.log_history(history)
    ui.info("revisando o jogo gerado…")
    rep = validate_game(game, check_syntax=opts.check_syntax)
    if ai and opts.review and opts.use_ai:
        try:
            rep["aiReview"] = jobs.review(ai, game, rep)
        except Exception as e:  # noqa: BLE001 — revisão é opcional
            ui.warn(f"revisão por IA indisponível: {e}")
    (game.root / "code" / "validation-report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    slug = opts.name or slugify(game.title)
    suffix = f"-{opts.suffix}" if opts.suffix else ""
    zip_path = make_zip(game.root, Path(opts.out_dir) / f"{slug}{suffix}.zip")
    return Result(zip_path, game.root, rep, log)


def print_validation(rep: Dict[str, Any]) -> None:
    for e in rep["errors"]:
        ui.err(e)
    for w in rep["warnings"]:
        ui.warn(w)
    for i in rep["info"]:
        ui.info(i)
    if rep.get("aiReview"):
        ui.heading("Revisão da IA")
        print(rep["aiReview"])


# ---------------------------------------------------------------------------------- recompilação
def load_any(src: str, workdir: Path) -> Any:
    """Projeto original (Project) ou jogo já recompilado (BuiltGame)."""
    p = Path(src)
    if p.is_dir() and is_built_game(p):
        return open_built_game(src)
    if p.is_file() and p.suffix.lower() == ".zip":
        try:
            return open_built_game(src, workdir / "in")
        except Exception:  # noqa: BLE001 — não é jogo recompilado: tenta como projeto
            shutil.rmtree(workdir / "in", ignore_errors=True)
    return open_project(src, workdir / "in")


def recompile(src: str, opts: Options, cfg: Optional[Config] = None, ai: Optional[AIClient] = None) -> Result:
    log: List[str] = []
    work = Path(tempfile.mkdtemp(prefix="maker-rebuild-work-"))
    total = 5 + (1 if opts.use_ai else 0)
    n = 0

    def step(msg: str) -> None:
        nonlocal n
        n += 1
        ui.step(n, total, msg)

    step("Lendo o projeto original")
    proj = open_project(src, work / "in")
    ui.info(f"{proj.label} · '{proj.title}' · {len(proj.maps)} mapas · {len(proj.assets)} assets · suporte: {proj.support}")
    proj.notes += opts.extra_notes
    step("Mapeando estrutura (mapas, eventos, banco de dados, assets, plugins)")
    rep = analyze(proj)
    print_report(rep)

    request = opts.instruction
    plan: Dict[str, Any] = {}
    if opts.use_ai and ai:
        step("Entendendo o pedido (esclarecer → planejar)")
        if request:
            request = jobs.clarify(ai, proj, request, opts.interactive)
            plan = jobs.plan(ai, proj, request)
            ui.info(f"plano: {plan.get('summary', '')}  [modo: {plan.get('mode')}]")
            log.append(json.dumps(plan, ensure_ascii=False))
        else:
            ui.info("sem instrução: conversão fiel (a IA será usada só para o que a conversão automática não resolve)")

    step("Convertendo para HTML + CSS + JS")
    ui_lang = opts.ui_lang or opts.translate_to or plan.get("translateTo") or (cfg.language if cfg else "pt-BR")
    out_dir = Path(opts.out_dir)
    gdir = build_game(proj, out_dir, opts.name, lang=(opts.translate_to or plan.get("translateTo") or "pt-BR"), ui_lang=ui_lang,
                      progress=_progress, convert_audio=opts.convert_audio,
                      extra_manifest={"options": {"instruction": opts.instruction, "ai": opts.use_ai}})
    game = BuiltGame(gdir)
    game.plugins = proj.plugins  # type: ignore[attr-defined]
    game.scripts = proj.scripts
    game.plugin_sources = proj.plugin_sources
    game.notes = proj.notes  # type: ignore[attr-defined]
    game.warnings = list(proj.warnings)
    ui.ok(f"jogo gerado em {gdir}")

    history: Dict[str, Any] = {"action": "recompile", "instruction": opts.instruction}
    target = opts.translate_to or plan.get("translateTo")
    do_port = opts.port or bool(plan.get("portScripts"))
    step("Revisando e aplicando etapas de IA" if opts.use_ai else "Revisando o resultado")
    if (target or do_port or plan.get("features")) and not (opts.use_ai and ai):
        ui.warn("etapas que exigem IA foram ignoradas (use --ai/--provider e uma chave ou modelo local)")
    if opts.use_ai and ai:
        if do_port or proj.scripts or proj.plugins:
            pr = port_game(ai, game, modules=opts.port_modules and do_port)
            ui.info(f"scripts: {pr.deterministic} portados por regras, {pr.ai} pela IA, {len(pr.failed)} falhas, {len(pr.modules)} módulos")
            history["port"] = {"deterministic": pr.deterministic, "ai": pr.ai, "modules": pr.modules}
            for w in pr.warnings + pr.failed:
                ui.warn(w)
        if plan.get("features") and plan.get("mode") in ("expand", "mixed", "modernize", "fix"):
            er = jobs.expand_game(ai, game, request, "expand", plan["features"], opts.max_features, lambda i, n_, t: ui.info(f"feature {i}/{n_}: {t}"))
            report_expand(er)
            history["expand"] = er.applied
        if target:
            tr = translate_game(ai, game, target, opts.translate_from, opts.tone, load_glossary(opts.glossary), progress=_progress)
            ui.info(f"tradução: {tr.translated}/{tr.units} unidades ({tr.unique} únicas), {len(tr.failed)} falhas")
            history["translate"] = {"to": target, "units": tr.units, "failed": len(tr.failed)}
    step("Empacotando (.zip)")
    res = _finish(game, opts, "", log, ai, history)
    return res


def report_expand(er: "jobs.ExpandReport") -> None:
    for a in er.applied:
        added = ", ".join(f"+{n} {k}" for k, n in a["added"].items()) or "nada novo"
        changed = ", ".join(f"~{n} {k}" for k, n in a["updated"].items())
        ui.ok(f"{a['feature']}: {a['summary']}  ({added}{'; ' + changed if changed else ''})")
    for f in er.failed:
        ui.err(f"feature falhou: {f}")
    for w in er.warnings:
        ui.warn(w)
    if er.assets_todo:
        ui.warn(f"{len(er.assets_todo)} asset(s) novos pedidos pela IA (criados como placeholders — substitua pela arte final):")
        for a in er.assets_todo:
            print(f"    · {a['category']}/{a['name']}  {a.get('note', '')}")


# ---------------------------------------------------------------------------------- jogo já recompilado
def prepare_built(src: str, opts: Options, cfg: Optional[Config] = None) -> BuiltGame:
    """Abre um jogo recompilado (copiando para a pasta de saída) ou recompila um projeto original antes."""
    work = Path(tempfile.mkdtemp(prefix="maker-rebuild-work-"))
    p = Path(src)
    out_dir = Path(opts.out_dir)
    if (p.is_dir() and is_built_game(p)) or (p.is_file() and p.suffix.lower() == ".zip" and _zip_is_built(p)):
        g = open_built_game(src, work / "in")
        opts.name = opts.name or slugify(g.title)     # fixa o nome antes de traduzir o título
        dest_dir = out_dir / opts.name
        if dest_dir.exists() and dest_dir.resolve() == g.root.resolve():
            # a saída cairia em cima do próprio jogo de origem (ex.: continuar o fluxo a partir de dist/<jogo>):
            # nunca apagar a origem — grava numa pasta irmã com o sufixo da operação
            dest_dir = out_dir / f"{opts.name}-{opts.suffix or 'novo'}"
        dest = copy_game(g.root, dest_dir)
        return BuiltGame(dest)
    ui.info("entrada é um projeto original: recompilando primeiro…")
    proj = open_project(src, work / "in")
    proj.notes += opts.extra_notes
    gdir = build_game(proj, out_dir, opts.name, lang="pt-BR", ui_lang=opts.ui_lang or (cfg.language if cfg else "pt-BR"),
                      progress=_progress, convert_audio=opts.convert_audio)
    g = BuiltGame(gdir)
    g.plugins = proj.plugins  # type: ignore[attr-defined]
    g.scripts, g.plugin_sources = proj.scripts, proj.plugin_sources
    g.notes = proj.notes  # type: ignore[attr-defined]
    return g


def _zip_is_built(p: Path) -> bool:
    import zipfile
    with zipfile.ZipFile(p) as z:
        return any(n.endswith("code/js/data/db.js") for n in z.namelist())


def expand(src: str, request: str, opts: Options, ai: AIClient, cfg: Config, mode: str = "expand") -> Result:
    opts.suffix = opts.suffix or ("expanded" if mode == "expand" else "improved")
    ui.step(1, 4, "Abrindo o jogo")
    game = prepare_built(src, opts, cfg)
    game.notes = getattr(game, "notes", []) + opts.extra_notes  # type: ignore[attr-defined]
    ui.step(2, 4, "Entendendo o pedido")
    req = jobs.clarify(ai, game, request, opts.interactive) if request else "melhorias gerais seguras"
    ui.step(3, 4, "Implementando" if mode == "expand" else "Aplicando melhorias")
    er = jobs.expand_game(ai, game, req, mode, None, opts.max_features, lambda i, n, t: ui.info(f"feature {i}/{n}: {t}"))
    report_expand(er)
    ui.step(4, 4, "Revisando e empacotando")
    res = _finish(game, opts, "", [], ai, {"action": mode, "instruction": request, "applied": er.applied, "failed": er.failed,
                                            "assetsTodo": er.assets_todo})
    if er.assets_todo:
        todo = res.game_dir / "code" / "assets-todo.md"
        todo.write_text("# Assets pendentes (placeholders criados)\n\n" + "\n".join(
            f"- `{a['category']}/{a['name']}` — {a.get('note', '')}" for a in er.assets_todo) + "\n", encoding="utf-8")
    return res


def translate(src: str, target: str, opts: Options, ai: AIClient, cfg: Config) -> Result:
    opts.suffix = opts.suffix or target.lower()
    ui.step(1, 3, "Abrindo o jogo")
    game = prepare_built(src, opts, cfg)
    ui.step(2, 3, f"Traduzindo para {target}")
    tr = translate_game(ai, game, target, opts.translate_from, opts.tone, load_glossary(opts.glossary), progress=_progress)
    ui.info(f"{tr.translated}/{tr.units} unidades traduzidas ({tr.unique} únicas); {len(tr.failed)} mantidas no original")
    for w in tr.warnings[:10]:
        ui.warn(w)
    ui.step(3, 3, "Revisando e empacotando")
    return _finish(game, opts, "", [], ai, {"action": "translate", "to": target, "units": tr.units, "failed": len(tr.failed)})


def port(src: str, opts: Options, ai: Optional[AIClient], cfg: Config) -> Result:
    opts.suffix = opts.suffix or "ported"
    ui.step(1, 3, "Abrindo o jogo")
    game = prepare_built(src, opts, cfg)
    ui.step(2, 3, "Portando scripts e plugins")
    pr = port_game(ai, game, modules=opts.port_modules)
    ui.info(f"{pr.ruby_groups} script(s) Ruby em eventos: {pr.deterministic} por regras, {pr.ai} pela IA; módulos: {pr.modules or 'nenhum'}")
    for w in pr.warnings + pr.failed:
        ui.warn(w)
    ui.step(3, 3, "Revisando e empacotando")
    return _finish(game, opts, "", [], ai, {"action": "port", "deterministic": pr.deterministic, "ai": pr.ai, "modules": pr.modules})
