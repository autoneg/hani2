# Library API

The admin API behind the [library](../guide/library.md): list, add and remove scenarios,
opponents, Assistants and tools, edit their groups, choose the tools a study offers and where
tools go in each view. Every route is **admin-only**: without a login it answers `401`, for a
user who is not an admin `403`.

Base path: `/api/admin/library` (behind a reverse proxy, the server's root path comes first).

## Common parameters

| Parameter | Meaning |
|---|---|
| `{kind}` | `scenarios`, `opponents`, `assistants` or `tools` (singular forms work too) |
| `?layer=` | Where to read from and write to: `settings` (default), `project:<P>` or `study:<P>/<S>`. `project:default` is the settings folder. A layer sees its own items and groups and those of the less specific layers. |

Names (items, groups, uploads) use letters, digits, `.`, `_` and `-` (items and tool and set
groups may also contain spaces), at most 64 characters; `..`, `/` and `\` are refused.

Errors are JSON `{"detail": "<message>"}` with these codes:

| Code | When |
|---|---|
| 400 | Invalid kind, layer, name or body; unsafe archive (absolute path, `..`, symbolic link, too large) |
| 404 | Unknown project, study, item or group (at this layer) |
| 409 | Name clash (an item or group of that name exists, a name that clashes with or starts like a registered scenario type, a package module that clashes with an installed one); deleting a built-in group, `Custom`, or a group defined at another layer; a layer file the request would rewrite (`library.yaml`, `scenario_links.yaml`, `scenario_sets.yaml`, `tools.yaml`) is not valid YAML (fix it by hand: it is never replaced) |
| 413 | Upload larger than 100 MB |
| 422 | The item cannot be used: no class found, the class does not load (`import` error, wrong base class), invalid scenario, scenarios that bring Python files without `allow_code` |

!!! warning "Uploaded code runs on the server"
    Opponents, Assistants and tools are Python code; a scenario may bring a `display.py`. Adding
    them runs that code inside the HANI2 server, with its permissions, when they are checked and
    whenever they are used. Responses of `upload` and `link` carry a `notice` saying so; show it.

## Items

### `GET /api/admin/library`

`{"kinds": [...], "layers": ["settings", "project:<P>", "study:<P>/<S>"], "notice": "..."}`.

### `GET /api/admin/library/{kind}?layer=`

```json
{"kind": "opponents", "layer": "project:P1", "items": [
  {"name": "LibBoulware", "title": "LibBoulware", "description": "A Boulware opponent",
   "source": "uploaded", "layer": "project:P1", "spec": "file:/…/library/opponents/mine/mine.LibBoulware",
   "path": "library/opponents/mine", "groups": ["lib"], "removable": true}
]}
```

| Field | Meaning |
|---|---|
| `name` | The item's name: scenario type, class name (or the name given when adding), tool name |
| `title`, `description` | For display (scenario `_info.yaml` title, class docstring, tool description) |
| `source` | `builtin` (ships with HANI2), `registered` (a plugin, env.json, an environment variable, a group file), `uploaded` (a copy the library owns) or `linked` (a path or spec left in place) |
| `layer` | Where an uploaded or linked item was added (`null` otherwise) |
| `spec` | Opponents, Assistants, tools: the class spec HANI2 loads |
| `path` | The folder or file behind the item, when there is one |
| `groups` | Groups whose expanded members contain the item |
| `removable` | Uploaded or linked **at this layer** |

Kind-specific extras: scenarios have `n_scenarios`; tools have `pane`, `timing`, `admin_only`,
`guest`, `enabled`, `origin`, `tool_groups` (built-in groups from metadata), `placement` (per
view, see below) and `offered`.

### `POST /api/admin/library/{kind}/upload`

`multipart/form-data`. Each form field may also be a query parameter (the form field wins).

| Field | Meaning |
|---|---|
| `file` | A `.zip` (every kind) or a `.py` file (opponents, Assistants, tools) |
| `layer` | As above |
| `name` | Scenarios: the type (category) name (default: the zip's single top folder, else its file name). Code: the upload's folder name and, for one class, the item's name |
| `group` | Also add the new items to this group (created when missing; a group of a lower layer is copied to this layer) |
| `classes` | Code: comma-separated class names to take (default: every class of the kind) |
| `allow_code` | Scenarios: accept archives with Python files (`display.py`) |
| `replace` | Replace an item of the same name added at this layer |

A scenario zip holds one scenario folder (`<Type>.yml` plus one file per role) or a category of
them. Every scenario is checked (`hani2 scenario check`); errors refuse the upload, warnings come
back. Uploaded scenarios go to `<layer>/scenarios/<name>/`. Code goes to
`<layer>/library/<kind>/<name>/` and is listed in `<layer>/library.yaml`; a package (a zip with
`__init__.py` folders) is imported by its dotted names with that folder on `sys.path`, a `.py`
file by its path.

Response:

```json
{"ok": true, "layer": "project:P1", "items": [{"name": "LibBoulware", "spec": "…", "layer": "project:P1",
 "source": "uploaded"}], "warnings": [], "notice": "Uploaded code runs inside the HANI2 server …"}
```

### `POST /api/admin/library/{kind}/link?layer=`

JSON body:

```json
{"target": "/abs/path/or/pkg.module:Class", "name": null, "group": null, "classes": null,
 "syspath": ["/abs/folder"], "allow_code": false, "replace": false}
```

- Scenarios: `target` is an absolute path to a scenario folder or a category; it is recorded in
  `<layer>/scenario_links.yaml`.
- Code: `target` is an absolute path to a `.py` file or a package folder (every class of the kind
  in it), or a class spec (`pkg.module:Class`, `pkg.module.Class`; opponents also
  `file:path/to/module.Class`) importable now or from `syspath`. Recorded in
  `<layer>/library.yaml`.

Response as for `upload`.

### `DELETE /api/admin/library/{kind}/items/{name}?layer=`

Removes an item added at this layer: an upload's files (when no other item uses them) are moved
to the layer's `.trash` folder (`scenarios/.trash/<name>-<time>`, `library/<kind>/.trash/<name>-<time>`),
a link is removed and its target left alone. A replaced upload (`replace`) is moved there too.
Built-in and registered items cannot be removed (`404` / `409`). Groups that list the item are
not changed.
`{"ok": true, "removed": "LibBoulware", "how": "deleted" | "removed" | "unlinked", "layer": "…", "trash": "/…/.trash/mine-20261118-101500"}`
(`trash` when files were moved).

### `POST /api/admin/library/{kind}/describe?layer=`

Body: a list of group entries (or `{"entries": [...]}`, at most 2000). What each one is, for
showing the members of a group or pool:

```json
{"kind": "opponents", "entries": [
  {"entry": "@qualified", "kind": "group", "name": "qualified", "title": "qualified", "description": "", "n": 3, "ok": true, "error": ""},
  {"entry": "LibBoulware", "kind": "item", "name": "LibBoulware", "title": "LibBoulware", "description": "A Boulware opponent", "ok": true, "error": ""},
  {"entry": "no.such.Class", "kind": "unknown", "name": "no.such.Class", "title": "no.such.Class", "description": "", "ok": false,
   "error": "cannot load 'no.such.Class': ModuleNotFoundError: …"}
]}
```

`kind` is `group` (with `n`, its expanded size), `item` or `unknown`. Opponent and Assistant
classes that are no listed item, or have no description, are loaded (as when they are used, once
per server process) to give their docstring or the import error.

## Groups

The groups of each kind: scenario sets (`scenario_sets.yaml`), opponent groups
(`groups/<key>.json`), Assistant groups (`assistant_groups/<key>.json`) and tool groups
(`tools.yaml` → `groups`, plus the built-in ones).

Entries are items or other groups: `@name` (or `:name`) always names a group; a bare entry is a
group when one has that name (opponents and Assistants: a group *file*; built-ins need `@`/`:`),
else an item. Expansion is in place, duplicates are dropped keeping the first, cycles are
reported and broken, names are case-insensitive. See
[Groups and composition](../guide/library.md#groups-and-composition).

### `GET /api/admin/library/{kind}/groups?layer=`

```json
{"kind": "opponents", "layer": "study:P1/s1", "groups": [
  {"name": "finalists", "entries": ["@qualified", "pkg.Team1"], "expanded": ["pkg.A", "pkg.B", "pkg.Team1"],
   "source": "file", "layer": "project:P1", "path": "/…/groups/finalists.json", "active": true,
   "editable": false, "description": "…", "assistant": null}
]}
```

| Field | Meaning |
|---|---|
| `entries` | The raw entries, as written |
| `expanded` | The members after composition |
| `source` | `file`, `builtin` or (scenario sets) `custom` |
| `layer` | Where the group is defined; opponent/Assistant groups of a study may also come from `results` (an outside system's files, read-only here) |
| `active` | `false` when a more specific group of the same name hides it |
| `editable` | Defined at this layer (so `PUT` replaces it and `DELETE` works) |

Scenario sets also have `default`; opponent groups `assistant`.

### `PUT /api/admin/library/{kind}/groups/{name}?layer=`

Body: a list of raw entries, or

```json
{"entries": ["@base", "Grocery"], "description": "…", "rename_from": "OldName",
 "syspath": ["/abs"], "assistant": "pkg.module:Coach"}
```

Creates or replaces the group at this layer (a group of a lower layer is shadowed, not changed).
The group is saved even when its entries look wrong; `warnings` says what: a reference to an
unknown group, an entry that is no known scenario type or tool (or, for opponents and
Assistants, a class that does not load), a cycle through other groups.
`rename_from` renames a group of this layer. Opponent and Assistant group files keep their other
fields (`syspath`, `assistant`, `description`); a library item's name in `entries` is stored as
its spec, and its `syspath` is added, so the file works on its own. Built-in tool groups and the
scenario set `Custom` cannot be written (`409`).
Response: `{"ok": true, "name", "entries", "expanded", "layer", "path", "warnings"}`.

### `DELETE /api/admin/library/{kind}/groups/{name}?layer=`

Deletes a group defined at this layer. `409` for a built-in group, `Custom`, or a group defined
at another layer.

## Scenarios

### `GET /api/admin/library/scenarios/default?layer=` / `PUT`

The default scenario set (`scenario_sets.yaml` → `default`).

- `GET` → `{"layer", "here": "<set>" | null, "effective": "<set>", "sets": [...]}`: this layer's
  own default (`null`: not set here), the default its sessions get, and every set name.
- `PUT` body: `{"default": "<set>"}` (matched case-insensitively, `404` for an unknown set) or
  `{"default": null}` (remove this layer's default). Returns the same as `GET`. An admin's
  session choice, `HANI2_SCENARIO_SET` and a study's `scenario_set` still win over it.

## Tools

### `GET /api/admin/library/tools/offer?layer=` / `PUT`

The tools sessions get: `tools.yaml` → `offer`, from the most specific layer that sets it
(default: every tool).

- `GET` → `{"layer", "here": [...] | null, "effective": [...] | null, "tools": ["Preferences", …]}`
- `PUT` body: a list (`["@information", "Utility-based Selector"]`), `null` (remove this layer's
  choice) or `{"offer": …}`. An empty list offers no tool. Returns the same as `GET`.

### `GET /api/admin/library/tools/placement?layer=` / `PUT`

Where each tool goes in each view (`full`, `simple`, `focus`).

`GET` →

```json
{"layer": "settings", "views": ["full", "simple", "focus"], "panes": ["upper", "lower", "side"],
 "tools": {"Trace": {"effective": {"full": {"pane": "lower", "visible": true, "order": 100},
                                   "simple": {"pane": "lower", "visible": false, "order": 100},
                                   "focus": {"pane": "lower", "visible": true, "order": 100}},
                     "here": {"simple": {"visible": false}}}}}
```

`effective` is the placement sessions of this layer get; `here` is this layer's `tools.yaml`
entry (`null`: none).

`PUT` body: `{"<tool>": <placement> | null}` (or `{"tools": {...}}`); each tool's placement
replaces that tool's entry at this layer, and the other tools' entries are kept (`?replace=true` replaces them all; `null` removes a tool's entry). A placement has
`pane` (`upper`, `lower`, `side`), `visible` (bool) and `order` (number) for every view, and/or a
mapping per view: `{"pane": "side", "simple": {"visible": false}}`. Returns the same as `GET`.

## Files written

| Layer folder | File |
|---|---|
| settings: `$HANI2_HOME/settings/` | `library.yaml`, `library/<kind>/…` (removed uploads: `library/<kind>/.trash/`), `scenarios/<name>/` (`scenarios/.trash/`), `scenario_links.yaml`, `scenario_sets.yaml`, `tools.yaml`, `groups/`, `assistant_groups/` |
| project: `projects/<P>/` | the same |
| study: `projects/<P>/studies/<S>/` (default project: the study folder) | the same |
