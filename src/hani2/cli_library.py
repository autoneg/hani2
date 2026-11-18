"""``hani2 library``: list, add and remove scenarios, opponents, Assistants and
tools, and edit their groups (see :mod:`hani2.library`)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

library_app = typer.Typer(help="Scenarios, opponents, Assistants and tools: list, add (upload or link), remove, groups.")

KindArg = Annotated[str, typer.Argument(help="scenarios, opponents, assistants or tools")]
LayerOpt = Annotated[str, typer.Option("--layer", help="Where to read and write: settings, project:<P> or study:<P>/<S>.")]


def _run(fn, *a, **kw):
    from hani2.library import LibraryError

    try:
        return fn(*a, **kw)
    except LibraryError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from None


@library_app.command("list")
def list_cmd(kind: KindArg, layer: LayerOpt = "settings") -> None:
    """List the items of a kind with their source, layer and groups."""
    from hani2 import library

    rows = _run(library.list_items, kind, layer)
    for it in rows:
        where = f" [{it['layer']}]" if it.get("layer") else ""
        groups = f"  groups: {', '.join(it['groups'])}" if it.get("groups") else ""
        typer.echo(f"{it['name']:<32} {it['source']}{where}{groups}")
        if it.get("description"):
            typer.echo(f"    {it['description']}")


@library_app.command("add")
def add_cmd(kind: KindArg,
            target: Annotated[str, typer.Argument(help="A .zip or .py file to copy in, a path to link (--link), or a class spec pkg.module:Class (linked).")],
            link: Annotated[bool, typer.Option("--link", help="Link the path instead of copying it.")] = False,
            group: Annotated[Optional[str], typer.Option("--group", "-g", help="Also add the item(s) to this group.")] = None,
            name: Annotated[Optional[str], typer.Option("--name", help="Name of the item (one class) or scenario type.")] = None,
            classes: Annotated[Optional[str], typer.Option("--classes", help="Only these classes (comma-separated).")] = None,
            syspath: Annotated[Optional[str], typer.Option("--syspath", help="Folders to import a class spec from (comma-separated).")] = None,
            allow_code: Annotated[bool, typer.Option("--allow-code", help="Accept scenarios that bring Python files (display.py).")] = False,
            replace: Annotated[bool, typer.Option("--replace", help="Replace an item of the same name at this layer.")] = False,
            layer: LayerOpt = "settings") -> None:
    """Add items: copy a .zip / .py into the library, or link a path or class spec."""
    from hani2 import library

    p = Path(target).expanduser()
    cls = [c.strip() for c in (classes or "").split(",") if c.strip()] or None
    if p.exists() and not link and p.is_file():
        out = _run(library.add_upload, kind, p.name, p.read_bytes(), layer, name=name, group=group, classes=cls,
                   allow_code=allow_code, replace=replace)
    else:
        if p.exists():
            target = str(p.resolve())
        sp = [x.strip() for x in (syspath or "").split(",") if x.strip()] or None
        out = _run(library.add_link, kind, target, layer, name=name, group=group, classes=cls, syspath=sp,
                   allow_code=allow_code, replace=replace)
    for it in out["items"]:
        typer.echo(f"added {it['name']} ({it['source']}, {it['layer']})" + (f": {it['spec']}" if it.get("spec") else ""))
    for w in out.get("warnings") or []:
        typer.secho(f"warning: {w}", fg="yellow")
    if out.get("notice"):
        typer.secho(out["notice"], fg="yellow")


@library_app.command("remove")
def remove_cmd(kind: KindArg, name: Annotated[str, typer.Argument(help="The item's name.")],
               layer: LayerOpt = "settings") -> None:
    """Remove an uploaded item or unlink a linked one."""
    from hani2 import library

    out = _run(library.remove_item, kind, name, layer)
    typer.echo(f"{out['how']} {out['removed']} ({out['layer']})")


@library_app.command("groups")
def groups_cmd(kind: KindArg, layer: LayerOpt = "settings",
               expanded: Annotated[bool, typer.Option("--expanded", "-e", help="Show the members after composition.")] = False) -> None:
    """List the groups of a kind (scenario sets for scenarios)."""
    from hani2 import library

    for g in _run(library.list_groups, kind, layer):
        where = g.get("layer") or g["source"]
        flag = "" if g.get("active", True) else "  (shadowed)"
        members = g["expanded"] if expanded else g["entries"]
        typer.echo(f"{g['name']:<24} {where}{flag}: {', '.join(map(str, members))}")


@library_app.command("group-set")
def group_set_cmd(kind: KindArg, name: Annotated[str, typer.Argument(help="The group's name.")],
                  entries: Annotated[list[str], typer.Argument(help="Items and groups (@name) in order.")],
                  description: Annotated[Optional[str], typer.Option("--description", help="Opponent / Assistant groups: a description.")] = None,
                  rename_from: Annotated[Optional[str], typer.Option("--rename-from", help="Rename this group of the layer to NAME.")] = None,
                  layer: LayerOpt = "settings") -> None:
    """Create or replace a group (entries may be other groups: @name)."""
    from hani2 import library

    out = _run(library.put_group, kind, name, entries, layer, description=description, rename_from=rename_from)
    typer.echo(f"{out['name']} ({out['layer']}): {', '.join(map(str, out['expanded']))}")


@library_app.command("group-delete")
def group_delete_cmd(kind: KindArg, name: Annotated[str, typer.Argument(help="The group's name.")],
                     layer: LayerOpt = "settings") -> None:
    """Delete a group defined at this layer."""
    from hani2 import library

    out = _run(library.delete_group, kind, name, layer)
    typer.echo(f"deleted {out['deleted']} ({out['layer']})")


@library_app.command("placement")
def placement_cmd(tool: Annotated[Optional[str], typer.Argument(help="A tool's name (omit to list every tool's placement).")] = None,
                  view: Annotated[Optional[str], typer.Option("--view", help="full, simple or focus (default: every view).")] = None,
                  pane: Annotated[Optional[str], typer.Option("--pane", help="upper, lower or side.")] = None,
                  visible: Annotated[Optional[bool], typer.Option("--visible/--hidden", help="Shown or hidden.")] = None,
                  order: Annotated[Optional[int], typer.Option("--order", help="Sort key inside the pane.")] = None,
                  clear: Annotated[bool, typer.Option("--clear", help="Remove the tool's placement at this layer.")] = False,
                  layer: LayerOpt = "settings") -> None:
    """Show or set where tools go in each view (tools.yaml → placement)."""
    from hani2 import library

    if tool and (clear or pane is not None or visible is not None or order is not None):
        if clear:
            _run(library.put_placement, {tool: None}, layer)
        else:
            cur = (_run(library.get_placement, layer)["tools"].get(tool) or {}).get("here") or {}
            change = {k: v for k, v in (("pane", pane), ("visible", visible), ("order", order)) if v is not None}
            if view:
                cur = dict(cur)
                cur[view] = {**(cur.get(view) or {}), **change}
            else:
                cur = {**cur, **change}
            _run(library.put_placement, {tool: cur}, layer)
    pl = _run(library.get_placement, layer)
    for name, p in pl["tools"].items():
        if tool and name.lower() != tool.lower():
            continue
        views = "  ".join(f"{v}: {e['pane']}{'' if e['visible'] else ' (hidden)'} #{e['order']}"
                          for v, e in p["effective"].items())
        typer.echo(f"{name:<24} {views}")


@library_app.command("offer")
def offer_cmd(entries: Annotated[Optional[list[str]], typer.Argument(help="Tools and tool groups (@name) to offer.")] = None,
              all_tools: Annotated[bool, typer.Option("--all", help="Offer every tool (remove this layer's choice).")] = False,
              layer: LayerOpt = "settings") -> None:
    """Show or choose the tools sessions get (tools.yaml → offer)."""
    from hani2 import library

    out = _run(library.put_offer, None, layer) if all_tools else \
        _run(library.put_offer, list(entries), layer) if entries else _run(library.get_offer, layer)
    typer.echo(f"offer: {', '.join(out['effective']) if out['effective'] is not None else 'every tool'}")
    typer.echo(f"tools: {', '.join(out['tools'])}")
