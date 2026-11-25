# Tools

Tools are the tabbed views around the negotiation desk: your preferences, the scenario description, plots of the offers, a table of the trace, outcome pickers and your results. Each tool is a small Python object that lives for one browser session. It receives the negotiation lifecycle callbacks and describes its UI with the declarative components in `hani2.tools.ui`. The web app renders that description; tool authors never write JavaScript.

This page lists the built-in tools and shows how to configure which tools a deployment offers. To write your own, follow the [tools tutorial](../tutorials/tools.md); to add one, save its file in the tools folder (`$HANI2_HOME/tools`, see [Adding tools](#adding-tools)). How tools look and behave for participants (tabs, the enable switch, moving and hiding) is described in [The interface](interface.md).

## Panes

Every tool lives in one of three panes:

| Pane | Where it appears |
|------|------------------|
| `upper` | The tab strip at the top left of the desk |
| `lower` | The tab strip at the bottom left |
| `side` | The tab strip on the right, next to the action panel |

A tool's class sets its default pane. Participants can move a tool to another pane from the tool's menu (unless an admin switched off `allow_moving_tools`), an admin can change the default in `env.json`, and an Assistant with the `tool_order` capability can move tools too.

## When tools appear

The `timing` attribute decides when a tool is created for a session:

| Timing | The tool is added |
|--------|-------------------|
| `always` | When the session is created (the page opens) |
| `load` | When the first scenario is loaded |
| `start` | When the first negotiation starts |
| `end` | When the first negotiation ends |

A tool is created once per session and stays for the rest of it; later scenarios reuse the same object and call its lifecycle hooks again.

## Built-in tools

| Name | Pane | Timing | On by default | Who gets it | What it shows |
|------|------|--------|---------------|-------------|---------------|
| Preferences | upper | load | yes (permanent) | everyone | A donut chart of your issue weights, a bar chart of the value of every option of the selected issue, your value on disagreement, and a collapsible explanation of how a deal's value is computed. |
| Scenario Info | upper | load | yes (permanent) | everyone | The scenario title, a "You act as ..." badge, the short description, a table of issues with their options and per-role descriptions, the hints for your role, and the long description in a collapsible card. |
| Briefing | upper | load | yes | when the participant has a private briefing or decisions only they make ([Who knows what](information.md)) | The participant's private instructions and limits, and which issues and actions only they decide. |
| Past Negotiations | upper | load | yes | when the participant holds past negotiations ([Who knows what](information.md)) | The past negotiations in this scenario that the participant holds: a table of them, and for the one picked its offers in a chart and a table. It says how many more the Assistant holds. |
| Market Research | upper | load | yes | when the participant gets market research ([Who knows what](information.md)) | What parties like the opponent usually want: typical issue weights, the option of each issue most often liked best, the most likely best deal and the usual value on disagreement. |
| My Results | upper | always | yes (permanent) | logged-in users (not guests) | Your score (the average of your best result per scenario), the number of negotiations and agreements, a per-scenario score table and a searchable table of every negotiation you finished, with a column picker. Practice rounds appear in the table but not in the score or counts. |
| Value Histogram | lower | start | yes | everyone | How often each value of the selected issues was offered by you and by the opponent. Bar charts for discrete issues with at most 25 values, histograms otherwise. Options: which issues, include your offers, two columns. |
| Utility Plot | lower | start | no | everyone | The utility (for you) of every offer over time, one line per party, with a dotted line labelled *No deal* at your value on disagreement. You can choose the X axis (relative time, step, time) and Y axis. Admins (or everyone, see below) can also plot the opponent's utility. |
| Negotiation Plot | lower | load | yes | admins only; everyone while an [estimate of the opponent](#an-estimate-of-the-opponents-preferences) is set | The negotiation in utility space: every outcome placed by its utility for you (x) and for the opponent (y), the Pareto frontier, the Nash and Kalai points, dotted lines at both sides' values on disagreement, both parties' offer trajectories and the agreement. Options: show all outcomes, the frontier, the Nash/Kalai points. |
| Outcome Plot | lower | start | no | everyone | The offers placed in the outcome space: any two issues, relative time or step on the axes, with an option to hide your own offers. |
| Trace | lower | start | no | everyone | A table of every offer: step, relative time, who made it, the offer, the message and its utility for you. Admins (or everyone, see below) can add an "Opponent utility" column. |
| Utility-based Selector | side | start | yes | everyone | Two sliders choose a utility range (minimum and width, in percent of the span from your worst to your best outcome, so un-normalized utility functions work too). The width starts at 100%, so by default the range runs from the minimum up to your best outcome. A table lists the outcomes in that range, best first; clicking a row puts it into your counter-offer. A **Set Offer** button picks one outcome from the range. While an [estimate of the opponent](#an-estimate-of-the-opponents-preferences) is set, it can also show the opponent's estimated utility and choose deals by it. |
| LLM | side | start | yes | admins only | Write an instruction in plain words ("propose a fair middle ground"), choose text and offer, text only or offer only, and let the configured language model write a suggested offer and message. **Apply to my offer** copies them into the counter-offer. |
| Random | side | start | yes | admins only | A **Set Offer** button that fills the counter-offer with a random outcome. |
| All Results | upper | always | yes | admins only | Every participant's results, a leaderboard and the full results table (practice rounds are not scored or ranked). |
| Opponent Preferences | upper | load | yes | admins only | The opponent's private preferences, in the same layout as Preferences. |

Every tool has a help text that says what it does and how it works. Participants read it from the **?** button next to the tool's tabs, and an Assistant with **Use tools** gets it at the top of what `read_tool` returns.

"Permanent" tools have no enable switch and cannot be hidden. Tools that are off by default still show their tab; their view is not computed until the participant (or the Assistant) switches them on.

"Admins only" means a logged-in admin account. `?admin=1` in the URL changes nothing for other users.

### Opening admin-only tools to participants

Every admin-only tool can be given to all participants: in the admin console under **Tools**, untick **Admins only** next to the tool (this writes `tools.overrides.<name>.admin_only = false` in `env.json`). Tick **Participants see opponent utilities** (`tools.show_opponent_utility`) to let everyone show the opponent's utility in the Utility Plot and Trace. Both apply to sessions started after saving. Keep in mind that Opponent Preferences, Negotiation Plot and the opponent-utility options reveal the opponent's private preferences, and All Results shows other participants' results.

### An estimate of the opponent's preferences

An estimate of the opponent's utility function can be set for a negotiation: by the Assistant
(`set_opponent_estimate`, see [Estimating the opponent](assistant.md#estimating-the-opponent)), by
Python code with `session.set_opponent_estimate(ufun)`, or straight on the human's negmas negotiator
(`private_info["opponent_ufun"]`, which negmas exposes as `Negotiator.opponent_ufun`). It lasts
until the next scenario loads. While one is set:

- **Negotiation Plot.** A participant who does not have the tool gets it, beside the other plots
  (marked as added by the Assistant when the Assistant set the estimate). It places every deal by
  its value for the participant and by the opponent's *estimated* value, scaled from 0% to 100%,
  with the Pareto frontier (dashed), Nash and Kalai points and both sides' offers computed from
  the estimate. A yellow **Estimate** banner says so, and the y axis reads *Opponent utility
  (estimate)*. This copy never shows the real preferences and goes away when the estimate is
  cleared. Those who have the tool anyway (admins, or everyone when an admin opened it) see the
  estimate by default too, and switch to the real preferences with **Opponent's side**; the
  banner then reads **Real preferences**, as it does whenever no estimate is set.
- **Utility-based Selector.** A banner says an estimate is set. The table gets an *Opponent
  (estimate)* column (**Show the opponent's estimate**), and **Choose deals by** switches the
  sliders, the order of the table and **Set Offer** to the opponent's estimated utility, while the
  *Utility* column keeps showing what each deal is worth to the participant. Picking a row fills
  only the issues.

None of this appears while no estimate is set. A participant who may not see what deals are worth
to them ([Who knows what](information.md)) does not get the plot, and `tools.disabled` or a study's
`offer` list that leaves out the Negotiation Plot keeps it away as well.

The Utility-based Selector needs the inverse of your utility function. When the scenario folder contains a cached inverter (`inverter_h<index>.pkl`, created by `hani2 generate`; see [Scenarios](scenarios.md)) and it matches the utility function, the tool uses it; otherwise it computes one when the negotiation starts.

The LLM tool uses the language model configured in `llm_settings.json` (see [Language models](llms.md)). When the model is not configured it shows a warning instead of failing.

## Adding tools

Save a tool's Python file in the **tools folder**, `$HANI2_HOME/tools` (by default `~/negmas/hani2/tools`), and every new session gets the tools it defines. No restart is needed: changed files are read again when the next session starts. `hani2 tools new "My Tool"` creates a file there to start from, `hani2 tools list` shows every tool and where it comes from, and `hani2 tools path` shows the folders searched. More folders can be added with `hani2 --tools DIR` or `tools.paths` in `env.json`. The [tools tutorial](../tutorials/tools.md) explains how to write the file, and the `examples/tools` folder of the repository holds five examples, including two that use a language model.

You can also add a tool through the [library](library.md): `hani2 library add tools offer_counter.py`
(or a `.zip`, or `--link` to a file or folder that stays where it is), for every study or only for
one project or study (`--layer project:P`, `--layer study:P/S`). The admin API does the same
([Library API](../reference/library-api.md)).

## Tool groups

Every tool belongs to groups: the ones its class lists in `groups` (for example
`groups = ("visualization",)`), plus `admin` for admin-only tools, `assistant` for tools with
timing `"agent"` and `all`. The built-in tools are in `information` (Preferences, Opponent
Preferences, Scenario Info, Trace, My Results, All Results), `visualization` (Utility Plot,
Negotiation Plot, Outcome Plot, Value Histogram) and `recommendation` (Utility-based Selector,
LLM, Random; every `OutcomeSelector` is in it). You can define your own groups, made of tools and
other groups, in `tools.yaml`, and choose the tools a study offers with `offer`:

```yaml title="projects/HI2027/tools.yaml"
groups:
  core: ["@information", "Utility-based Selector"]
offer: ["@core", "Utility Plot"]
```

Without `offer` every tool is offered, as before. See
[Tool groups](library.md#tool-groups).

## Placement per view

The page has a full, a simple and a focus view. A tool can sit in another pane, at another
place, or be hidden, depending on the view: set `placement` on the class
(`placement = {"simple": {"pane": "upper", "visible": False}}`) or per tool in `tools.yaml`. A
view not given uses the tool's `pane` and `order`, shown. When the view changes, every tool moves
to its place in the new view; where the participant moved or hid a tool is remembered per view.
Tools without a placement never move. See
[Where tools go in each view](library.md#where-tools-go-in-each-view).

## Configuring tools in env.json

The `"tools"` section of `env.json` (see [Configuration reference](configuration.md)) controls which tools exist and their defaults. It has these keys:

```json
{
  "tools": {
    "paths": ["/srv/study/tools"],
    "extra": ["my_package.tools:WhatIf", "my_package.tools.OfferCounter"],
    "disabled": ["Trace", "Outcome Plot"],
    "overrides": {
      "Utility Plot": {"enabled": true, "pane": "side"},
      "Value Histogram": {"order": 1}
    }
  }
}
```

`paths`
:   Folders (or single `.py` files) to load tools from, in addition to `$HANI2_HOME/tools`.

`extra`
:   A list of tool classes to add. Each entry is an import path, `module:Class` or `module.Class`, or a file and class, `path/to/file.py:Class`. A folder or a `.py` file without a class name loads every tool in it, like `paths`. The class must be a subclass of `hani2.tools.Tool`; otherwise the server prints `[hani2] could not load tool ...` and skips it. The module must be importable by the server process, so put it in an installed package or start the server with its folder on `PYTHONPATH`.

`disabled`
:   Tool names to remove. Matching ignores case. Disabled tools are not created at all, for anyone.

`overrides`
:   A mapping from a tool's name (case-insensitive) to new defaults. The accepted keys are:

    | Key | Meaning |
    |-----|---------|
    | `pane` | `upper`, `lower` or `side` |
    | `timing` | `always`, `load`, `start` or `end` |
    | `enabled` | Default state of the enable switch |
    | `admin_only` | Only admins get the tool |
    | `guest` | Whether playground and Prolific sessions get the tool |
    | `order` | Sort key inside the pane (smaller first) |
    | `at_front` | Make this the selected tab of its pane when it appears. Defaults to true when `order` is 0 or 1. |

Tools are collected in this order: the built-in tools, then tools published by installed packages through the `hani2.tools` entry-point group, then classes registered with `hani2.tools.register_tool`, then the tool folders, then the `extra` list. A class that appears twice is added once, and when two tools share a name the first one wins (the server log names the one it ignored). `disabled` and `overrides` then apply to all of them, so you can also disable or move a tool that a package provides.

The server reads this section each time a session reaches a timing, so a change reaches new sessions and any timing an existing session has not reached yet. Tools a session already created stay as they are.

### Publishing tools from a package

A package can make its tools available without touching `env.json` by declaring an entry point in the `hani2.tools` group in its `pyproject.toml`:

```toml
[project.entry-points."hani2.tools"]
what_if = "my_package.tools:WhatIf"
```

After `pip install` of that package, every session gets the tool (subject to `disabled` and `overrides`).

## Who sees what

When a session reaches a tool's timing, a tool is created for it unless:

- the tool is `admin_only` and the session does not belong to an admin account, or
- the tool has `guest = false` and the session is a playground or Prolific session (`/play`).

Two settings of `env.json → negotiation` also affect tools; the admin console sets them on the Participant interface page, for all projects, a project or a study (see [Admin console](admin.md#participant-interface)):

- `allow_tool_switch`: when off, participants do not see the enable switch, and tools that are off by default render anyway.
- `allow_moving_tools`: when off, the "Move to ..." entries disappear from the tool menu and move requests are ignored.

## Tools and the Assistant

The Assistant sees the list of tools in its context and, depending on its capabilities, can switch tools on or off (`tool_enable`), hide and show them (`tool_visibility`) and move them or bring one to the front (`tool_order`). Both the participant's buttons and the agent go through the same server-side controller, so permanent tools cannot be hidden or switched off by either.

With **Use tools** (`tool_use`) the agent can also read any tool's help text and what it shows, as text, and operate its inputs, buttons and selectable tables, exactly as the participant would; whatever the tool then does to the offer follows the agent's own permissions. With **Add tools** (`tool_add`) it can put new tools on the screen during the session: its own tools, tools from its `toolbox` setting, registered tools the participant does not have yet, and tools whose `timing` is `"agent"` (these appear only when an agent adds them). A tool added this way carries a small assistant mark on its tab. See [Tools the agent can find, use and add](assistant.md#tools-the-agent-can-find-use-and-add).

## Extra tools from the command line

`hani2 --tools package.module:Class,path/to/file.py:Class` loads extra tools when the server starts (each class is imported first, so a typo stops the server with an error). An entry can also be a folder or a `.py` file, which loads every tool in it and, like the tools folder, re-reads changed files for new sessions, and `hani2 experiment create NAME --tools ...` saves them in an experiment. Use it for tools submitted by competition teams.

## How tools are rendered

Only the tools the participant can see are computed: the front tab of each pane and an enlarged tool. A hidden tool is brought up to date when its tab is opened. Tools are computed in their own worker threads, never on the server's main loop, so a slow tool does not delay the rest of the page; in the browser, charts are drawn when the browser is idle and only when on screen.
