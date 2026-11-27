# Showing other kinds of preferences

The **Preferences** tool (and the admin-only **Opponent Preferences** tool)
explains how a negotiator values every possible deal. Scenarios can describe
preferences in many ways, so HANI2 picks a *view* that fits the type of the
utility function and falls back to a general view for anything it does not
know.

Every view shows the **value on disagreement** as one sentence under the
charts ("If you do not reach agreement you get 10% (your best option gives you
100%)."), and a short, plain-language explanation of how the total is worked
out (collapsed at the bottom). The charts carry a one-line caption saying what
they mean.

The Preferences tool also shows, for every scenario:

- **In short** (at the top; clicking its title folds it away, and it stays
  folded while the tool updates): the preferences in two or three sentences,
  such as the issues that matter most and least and their weights, followed by
  the hints below.
- **Hints** (inside *In short*): the hints of the participant's role and, for
  every issue, what the participant wants in plain words. After each sentence
  an icon, as tall as the text, shows the direction at a glance: a green arrow
  up (the more, the better), a red arrow down (the less, the better) or two
  blue arrows meeting at a line (best at one value). Unordered options and
  "worst at …" issues get no icon. The sentence follows
  the shape of the issue's value function: "The higher, the better (every step
  is worth the same).", "The lower, the better.", "Best at 5 days; the further
  away from it, the worse.", "Worst at …; the further away from it, the
  better.", "The more clocks you get, the better." (item splits), or the
  options from best to worst for unordered options. A participant who knows
  only part of their preferences ([Who knows what](information.md)) sees no
  hints.

## Weights as a bar or a donut

Issue weights are drawn as one thin horizontal bar by default, split into one
coloured segment per issue: it takes much less room than a donut. Each segment
shows its share when it fits, and the legend under the bar names every issue
with its share. Set `tools.weights_chart` to `donut` in `env.json` (in the
settings folder, a project or a study), or choose *Issue weights shown as* on
the console's **Tools** page, to draw a ring instead. Signed weights (linear
preferences with negative weights) are always drawn as signed bars.

When the tool is **enlarged or popped out** (in its own window rather than
pinned in a pane), `tools.weights_chart_window` decides on its own: `donut` or
`bar`, or `same` (the default) for the pane's chart (*Issue weights in an
enlarged or popped-out tool* on the **Tools** page).

```json
{"tools": {"weights_chart": "bar", "weights_chart_window": "donut"}}
```

## Side by side in a pinned pane

In a tool pane pinned outside the full view (the simple view on a desktop), the
weights and the value of each option sit **side by side** whenever the pane is
wide enough for two columns of about 170 px; in the full view's narrower
columns, and in the tool's window, the usual two-column layout applies (it
stacks below about 520 px).

## Normalized percentages or raw numbers

By default (`tools.preferences_scale: normalized`) everything is a percentage,
normalized the way negmas normalizes: every deal is worth 0% (the worst) to
100% (the best), the weights are shares adding up to 100% and every issue's
options are worth 0% to 100%. Preferences that are not normalized are
**normalized for display** by negmas (`ufun.normalize()`); the value on
disagreement goes through the same map, so it keeps its place among the deals
(below 0% if it is worse than the worst deal). The scenarios HANI2 generates
are normalized already and are shown as they are. Preferences on an outcome
space too large to search (and not linear-additive) are shown as they are.

With `tools.preferences_scale: raw` (*Preferences shown as* on the **Tools**
page) the tools show the utility function's own numbers: the weights as they
are, the value of every option and the value on disagreement (with what the
best deal is worth), without percentages. Not normalized, a deal can be worth anything (negative
included), an issue's options any amount and the weights any size; a negative
weight is drawn in red.

## Many options: a line instead of bars

An issue with more than `tools.values_line_above` options (12 by default), and
every continuous issue, shows the value of its options as a **line** drawn the
same way round as the bars: the options down the side, top to bottom, and their
value across. Set the number on the **Tools** page (*Line plot above
(options)*).

## Supported types

| Utility function | What is shown |
| --- | --- |
| `LinearAdditiveUtilityFunction`, `LinearUtilityAggregationFunction` | Issue weights (a bar or a donut, see above), the value of each option of the selected issue (bars, or a line for many options), the starting amount if not zero |
| `LinearUtilityFunction`, `AffineUtilityFunction` | Signed weight per numeric issue, the formula, the starting amount |
| `GLAUtilityFunction` | Weight of each factor; for the selected factor its value function, or a heatmap for two small discrete issues |
| `PAUtilityFunction`, `GPAUtilityFunction` | Table of polynomial terms (coefficient and product of factors) and the value functions |
| `NonLinearAggregationUtilityFunction` | Value of each option per issue, best deals, a note on the custom rule |
| `HyperRectangleUtilityFunction`, `NonlinearHyperRectangleUtilityFunction` | Table of regions with their ranges, values and weights |
| `WeightedUtilityFunction` | Donut of the parts' weights and a collapsible, nested view of every part |
| `ComplexNonlinearUtilityFunction` | Collapsible, nested view of every part |
| `ExpDiscountedUFun`, `LinDiscountedUFun` | The time-pressure parameters and the view of the underlying preferences |
| `RankOnlyUtilityFunction` | Deals from best to worst |
| `ConstUtilityFunction` | The single value of every deal |
| Probabilistic ones (`IPUtilityFunction`, `ProbMappingUtilityFunction`, ...) | Deals ranked by expected value |
| `MappingUtilityFunction` and anything else | Table of the best deals and a histogram of values |

Spaces with more than 5000 possible deals are *sampled*, and the view says so.
Nesting is limited to three levels; deeper parts use the general view. A view
that fails never breaks the tool: it falls back to the general view.

## Registering a custom view

A view is a function that takes a context and returns a list of
[UI components](../tutorials/tools.md). Register it for a class with the
`register_ufun_view` decorator. The most specific class in the utility
function's MRO wins; `priority` breaks ties for the same class.

```python
from hani2.tools import ui
from hani2.tools.ufun_views import register_ufun_view
from my_package import SeasonalUtility

@register_ufun_view(SeasonalUtility)
def seasonal_view(ctx):
    u = ctx.ufun
    season, select = ctx.choose("season", u.seasons, "Season")  # widget name unique when nested
    return [
        ctx.layout(
            ui.text_block("Deals are worth more in the high season."),
            right=ui.card(select, title=f"{ctx.title_prefix}Value by season"),
        ),
        *ctx.explain("Your total depends on the **season** of the deal."),
    ]
```

`ctx` gives you the tool (`ctx.tool`), the utility function (`ctx.ufun`),
`ctx.title_prefix` (for example `"Opponent "`), `ctx.issues`,
`ctx.issue_names`, `ctx.key()` / `ctx.value()` for widget names and values, and
`ctx.child(ufun, label)` for nested views (render them with
`render_ufun_view(ctx.tool, sub, ctx=ctx.child(sub, "part1"))`). The value on
disagreement is added automatically; `ctx.layout(...)` places it for you.

The module `hani2.tools.ufun_views` also offers helpers such as
`ranking_components(ctx)` (the general view) and `sample_outcomes(ufun)`.

### From a package: entry point

Packages can ship views without any change to HANI2. Declare an entry point in
the `hani2.ufun_views` group that points to a module that registers its views
when imported, or to a function that does the registering:

```toml
[project.entry-points."hani2.ufun_views"]
seasonal = "my_package.views"
```

Entry points are loaded the first time preferences are shown. A failing entry
point only produces a warning.
