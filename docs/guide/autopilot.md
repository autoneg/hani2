# Autopilot

Autopilot lets an agent make every negotiation decision for the participant. The participant presses **Autopilot** in the header, the action panel changes to "Autopilot is negotiating for you", and the history keeps updating while the agent plays. Pressing **Take back control** in the action panel (or the Autopilot button again) hands control back.

Use it to demo the interface, to test scenarios and opponents quickly, or to study how people delegate decisions. Autopilot is off by default.

## Drivers

The agent that plays is called the *driver*. There are two kinds.

| Driver | How it plays |
|--------|--------------|
| `Assistant` | The session's [Assistant](assistant.md) decides each turn through its functions. |
| A negotiator name | A negmas negotiator takes the participant's seat and plays with the participant's preferences. |

The negotiators offered are `AspirationNegotiator`, `NaiveTitForTatNegotiator`, `BoulwareTBNegotiator`, `ConcederTBNegotiator` and `LinearTBNegotiator`, followed by the text-producing negotiators from negmas-llm when that package provides them (`HybridWithTextNegotiator`, `BoulwareWithTextNegotiator`, `ConcederWithTextNegotiator`, `LinearWithTextNegotiator`, `LLMHybridNegotiator`, `LLMBoulwareTBNegotiator`, `LLMConcederTBNegotiator`, `LLMLinearTBNegotiator`). See [Opponents](opponents.md) for what these negotiators do.

To offer fewer drivers, list the ones you want in `allowed_drivers` (see [Settings](#settings)), or tick them under *Drivers offered* on the admin console's **Autopilot** page. No setting adds a driver: the negotiators come from the Python list `AUTOPILOT_NEGOTIATORS` in `hani2.support_agent.autopilot`, and code that appends a negmas negotiator name to it (for example `"MiCRONegotiator"`) before the server starts adds that driver.

## Settings

Autopilot reads `autopilot_settings.json` from the settings folder, merged over the bundled defaults. You can also edit it in the admin console under **Autopilot**. Changes apply immediately; the file is read on every autopilot request.

```json
{
  "allowed": false,
  "driver": "Assistant",
  "allowed_drivers": null,
  "step_delay": 0.5,
  "user_can_choose": null
}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `allowed` | `false` | The master switch. With `false`, the Autopilot button is not shown. |
| `driver` | `"Assistant"` | The default driver, used whenever the participant cannot or did not choose one. |
| `allowed_drivers` | `null` | The drivers that may be used. `null` allows all of them. When `driver` is not in this list, the first allowed driver is used instead. |
| `step_delay` | `0.5` | Seconds to wait before each autopilot move, so people can follow the play. |
| `user_can_choose` | `null` | Whether non-admin participants may pick the driver. `null` allows it only in the guest playground (not for Prolific participants). Admins can always choose. |

## When autopilot is available

The Autopilot button appears when `allowed` is true. It is enabled when a driver is configured and, for the `Assistant` driver, the session has an Assistant. When the participant may choose, a driver selector appears next to the button. The button and selector are shown on wide screens only.

Turning it on fails with a warning toast in these cases:

- autopilot is not allowed on the server;
- no driver is configured;
- the driver is `Assistant` and the session has no Assistant (for example with `--assistant off`);
- the driver is a negotiator but the current negotiation was started without one. The negotiator for the seat is built when the negotiation starts, so the participant has to wait for the next negotiation.

Switching the driver to another negotiator in the middle of a negotiation rebuilds the seat's driver so the switch takes effect at once.

## The Assistant driver

When the Assistant drives:

- its autonomy is raised to `full` for both the admin and the participant layer, and restored when autopilot stops;
- on each of the participant's turns it runs a model turn with the instruction to call exactly one of `submit_counter_offer`, `accept_offer` or `end_negotiation`, and the model is required to call a function;
- the turn ends as soon as one of those three functions runs;
- `ask_user` returns `None` immediately, since nobody is watching.

Capabilities still apply. If `submit_counter`, `accept` or `end` is not effective, the agent cannot make that move.

### The stall safety net

If a turn ends without one of the three actions, the agent counts a stall, shows a warning toast and sends the current draft as a counter-offer to keep the negotiation moving. After three stalls in a row it shows an error toast ("Autopilot disengaged: the Assistant kept failing to act. You're back in control.") and switches autopilot off. A successful turn resets the count.

!!! note
    The session drives autopilot turns itself: it calls the agent's `autopilot_step()` on every turn, independently of `on_event`. Custom agents that override `on_event` therefore work as drivers too, and the driver keeps moving even when the participant has switched the assistant's chat off. `step_delay` applies to Assistant drivers as well.

## Negotiator drivers

A negotiator driver plays the participant's seat directly. On each of the participant's turns the session waits `step_delay` seconds and then lets the negotiator respond: it may accept, end, or make an offer, computed from the participant's utility function. It never accepts a missing offer.

## Time limits

While autopilot is active, the participant's time limit does not force a move; the session keeps checking until autopilot stops or the negotiation ends. The negotiation's own step and time limits still end it as usual.

## Results

A negotiation in which autopilot was switched on at any time has `autopilot` set to true in `results.csv` (see [Study management](study-management.md)). With the Assistant driver, the agent's actions are also logged as `support_agent` events.

## Testing

`hani2.testing.make_session` runs autopilot headlessly. Write the settings file into the test home first:

```python
import json
import tempfile
from pathlib import Path

from hani2.testing import make_session

home = Path(tempfile.mkdtemp())
(home / "settings").mkdir(parents=True)
(home / "settings" / "autopilot_settings.json").write_text(
    json.dumps({"allowed": True, "driver": "ConcederTBNegotiator", "step_delay": 0})
)

s = make_session(n_steps=8, home=str(home))
s.start()
s.wait_for_turn()
assert s.set_autopilot(True)["ok"]
s.wait_until_done(timeout=30)
print(s.result)
```
