# Tools

Tools are the tabbed views around the negotiation desk: your preferences, the scenario description, plots of the offers, a table of the trace, outcome pickers and your results. Each tool is a small Python object that lives for one browser session. It receives the negotiation lifecycle callbacks and describes its UI with the declarative components in `hani2.tools.ui`. The web app renders that description; tool authors never write JavaScript.

This page lists the built-in tools and shows how to configure which tools a deployment offers. To write your own, follow the [tools tutorial](../tutorials/tools.md). How tools look and behave for participants (tabs, the enable switch, moving and hiding) is described in [The interface](interface.md).

## Panes

Every tool lives in one of three panes:

| Pane | Where it appears |
|------|------------------|
| `upper` | The tab strip at the top left of the desk |
| `lower` | The tab strip at the bottom left |
| `side` | The tab strip on the right, next to the action panel |

A tool's class sets its default pane. Participants can move a tool to another pane from the tool's menu (unless an admin switched off `allow_moving_tools`), an admin can change the default in `env.json`, and a support agent with the `tool_order` capability can move tools too.

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
| My Results | upper | always | yes (permanent) | logged-in users (not guests) | Your score (the average of your best result per scenario), the number of negotiations and agreements, a per-scenario score table and a searchable table of every negotiation you finished, with a column picker. |
| Value Histogram | lower | start | yes | everyone | How often each value of the selected issues was offered by you and by the partner. Bar charts for discrete issues with at most 25 values, histograms otherwise. Options: which issues, include your offers, two columns. |
| Utility Plot | lower | start | no | everyone | The utility (for you) of every offer over time, one line per party, with a dotted line labelled *No deal* at your value on disagreement. You can choose the X axis (relative time, step, time) and Y axis. Admins (or everyone, see below) can also plot the opponent's utility. |
| Negotiation Plot | lower | load | yes | admins only | The negotiation in utility space: every outcome placed by its utility for you (x) and for the opponent (y), the Pareto frontier, the Nash and Kalai points, dotted lines at both sides' values on disagreement, both parties' offer trajectories and the agreement. Options: show all outcomes, the frontier, the Nash/Kalai points. |
| Outcome Plot | lower | start | no | everyone | The offers placed in the outcome space: any two issues, relative time or step on the axes, with an option to hide your own offers. |
| Trace | lower | start | no | everyone | A table of every offer: step, relative time, who made it, the offer, the message and its utility for you. Admins (or everyone, see below) can add an "Opponent utility" column. |
| Utility-based Selector | side | start | yes | everyone | Two sliders choose a utility range (minimum and width, in percent of the span from your worst to your best outcome, so un-normalized utility functions work too). The width starts at 100%, so by default the range runs from the minimum up to your best outcome. A table lists the outcomes in that range, best first; clicking a row puts it into your counter-offer. A **Set Offer** button picks one outcome from the range. |
| LLM | side | start | yes | admins only | Write an instruction in plain words ("propose a fair middle ground"), choose text and offer, text only or offer only, and let the configured language model write a suggested offer and message. **Apply to my offer** copies them into the counter-offer. |
| Random | side | start | yes | admins only | A **Set Offer** button that fills the counter-offer with a random outcome. |
| All Results | upper | always | yes | admins only | Every participant's results, a leaderboard and the full results table. |
| Opponent Preferences | upper | load | yes | admins only | The partner's private preferences, in the same layout as Preferences. |

"Permanent" tools have no enable switch and cannot be hidden. Tools that are off by default still show their tab; their view is not computed until the participant (or the support agent) switches them on.

"Admins only" means a logged-in admin account. Opening a page with `?admin=1` turns on the admin badge and the opponent picker in the UI but does not give a session the admin-only tools, and the admin-only options inside tools stay hidden.

### Opening admin-only tools to participants

Every admin-only tool can be given to all participants: in the admin console under **Server & studies → Tools**, untick **Admins only** next to the tool (this writes `tools.overrides.<name>.admin_only = false` in `env.json`). Tick **Participants see opponent utilities** (`tools.show_opponent_utility`) to let everyone show the opponent's utility in the Utility Plot and Trace. Both apply to sessions started after saving. Keep in mind that Opponent Preferences, Negotiation Plot and the opponent-utility options reveal the opponent's private preferences, and All Results shows other participants' results.

The Utility-based Selector needs the inverse of your utility function. When the scenario folder contains a cached inverter (`inverter_h<index>.pkl`, created by `hani2 generate`; see [Scenarios](scenarios.md)) and it matches the utility function, the tool uses it; otherwise it computes one when the negotiation starts.

The LLM tool uses the language model configured in `llm_settings.json` (see [Language models](llms.md)). When the model is not configured it shows a warning instead of failing.

## Configuring tools in env.json

The `"tools"` section of `env.json` (see [Configuration reference](configuration.md)) controls which tools exist and their defaults. It has three keys:

```json
{
  "tools": {
    "extra": ["my_package.tools:WhatIf", "my_package.tools.OfferCounter"],
    "disabled": ["Trace", "Outcome Plot"],
    "overrides": {
      "Utility Plot": {"enabled": true, "pane": "side"},
      "Value Histogram": {"order": 1}
    }
  }
}
```

`extra`
:   A list of tool classes to add. Each entry is an import path, either `module:Class` or `module.Class`. The class must be a subclass of `hani2.tools.Tool`; otherwise the server prints `[hani2] could not load tool ...` and skips it. The module must be importable by the server process, so put it in an installed package or start the server with its folder on `PYTHONPATH`.

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

Tools are collected in this order: the built-in tools, then tools published by installed packages through the `hani2.tools` entry-point group, then the `extra` list. A class that appears twice is added once. `disabled` and `overrides` then apply to all of them, so you can also disable or move a tool that a package provides.

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

Two admin settings in the per-session settings drawer also affect tools (see [Admin console](admin.md)):

- `allow_tool_switch`: when off, participants do not see the enable switch, and tools that are off by default render anyway.
- `allow_moving_tools`: when off, the "Move to ..." entries disappear from the tool menu and move requests are ignored.

## Tools and the support agent

The support agent sees the list of tools in its context and, depending on its capabilities, can switch tools on or off (`tool_enable`), hide and show them (`tool_visibility`) and move them or bring one to the front (`tool_order`). Both the participant's buttons and the agent go through the same server-side controller, so permanent tools cannot be hidden or switched off by either.

With **Use tools** (`tool_use`) the agent can also read what any tool shows, as text, and operate its inputs, buttons and selectable tables, exactly as the participant would; whatever the tool then does to the offer follows the agent's own permissions. With **Add tools** (`tool_add`) it can put new tools on the screen during the session: its own tools, tools from its `toolbox` setting, registered tools the participant does not have yet, and tools whose `timing` is `"agent"` (these appear only when an agent adds them). A tool added this way carries a small assistant mark on its tab. See [Tools the agent can find, use and add](support-agent.md#tools-the-agent-can-find-use-and-add).

## Extra tools from the command line

`hani2 --tools package.module:Class,path/to/file.py:Class` loads extra tools when the server starts (each class is imported first, so a typo stops the server with an error), and `hani2 experiment create NAME --tools ...` saves them in an experiment. Use it for tools submitted by competition teams.

## How tools are rendered

Only the tools the participant can see are computed: the front tab of each pane and an enlarged tool. A hidden tool is brought up to date when its tab is opened. Tools are computed in their own worker threads, never on the server's main loop, so a slow tool does not delay the rest of the page; in the browser, charts are drawn when the browser is idle and only when on screen.
