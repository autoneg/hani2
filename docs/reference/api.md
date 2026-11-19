# Python API

This page is generated from the docstrings in the source. It covers the modules you use when you write tools, Assistants and tests. The guides explain how the pieces fit together: see [Tools](../guide/tools.md), [Assistant](../guide/assistant.md) and the [tutorials](../tutorials/assistant.md).

## Tools

::: hani2.tools.base

## LLM tools

::: hani2.tools.llm_tool

## Tool registration

::: hani2.tools.registry

## Showing offers

::: hani2.display

## UI components

::: hani2.tools.ui

## Assistant runtime

::: hani2.support_agent.runtime

## Assistant functions

::: hani2.support_agent.tools

## Capabilities

::: hani2.support_agent.capabilities

## Testing helpers

::: hani2.testing

## Recordings

::: hani2.recording.format

## Scheduling

::: hani2.scheduling
    options:
      members: [register, methods, check_method, check_scheduling, resolve, methods_for, rng, pick_opponent, pick_scenario_type, pick_assistant_fixed]

## Evaluation

::: hani2.evaluation

::: hani2.evaluation.base

### Evaluation criteria, combined scores and leaderboards

::: hani2.evaluation.tasks
    options:
      members: [criteria_of, check_target, COMPONENTS, RULES]

::: hani2.evaluation.scores
    options:
      members: [SCORES, NORMALISERS, Score, Component, compute, score_row]

::: hani2.evaluation.tracks
    options:
      members: [TRACKS, leaderboard, leaderboards]

## Models and connections

::: hani2.model_chain

::: hani2.connections

::: hani2.providers

::: hani2.harness
    options:
      members: [complete, run_tools, capabilities, refused_for, HarnessReply, Limits, HarnessError, HarnessUnavailable, HarnessTimeout]
