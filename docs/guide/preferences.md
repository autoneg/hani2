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

## Weights as a donut or a bar

Issue weights are drawn as a donut by default. A thin horizontal bar, split
into one segment per issue, takes much less room: set `tools.weights_chart` to
`bar` in `env.json` (in the settings folder, a project or a study), or choose
*Issue weights shown as* on the console's **Tools** page. Each segment shows
its share when it fits, and the legend under the bar names every issue with
its share. Signed weights (linear preferences with negative weights) are always
drawn as signed bars.

```json
{"tools": {"weights_chart": "bar"}}
```

## Supported types

| Utility function | What is shown |
| --- | --- |
| `LinearAdditiveUtilityFunction`, `LinearUtilityAggregationFunction` | Issue weights (donut or bar, see below), the value of each option of the selected issue, the starting amount if not zero |
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
