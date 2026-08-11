# Experiment: does `byzantine_agents` catch more cheaters, or hide them?

Part A/B/C exercise for the NANDA Town quickstart. Scenario: `reputation`.
Setting changed: `failures.byzantine_agents` (`0.0` -> `0.2`), one setting,
everything else identical (same seed, same agent counts, same rounds).

The diff against the bundled `reputation` scenario touches four lines:
`name` and `description` are renamed for the variant, `output.trace` points
to a separate file so this run doesn't overwrite the baseline trace, and
`failures.byzantine_agents` goes from unset (0.0 default) to 0.2. That last
one is the only functional change. I confirmed this by running
`nest scenarios show reputation` and diffing it against
`reputation_byzantine.yaml`.

## Which setting I changed, and why

I changed `failures.byzantine_agents` in the reputation scenario from 0.0 to
0.2, holding seed, agent counts, and rounds constant. I picked `reputation`
because trust between counterparties is the part of any market I find most
interesting. It's not just about whether messages get delivered, it's about
whether bad behavior gets caught.

## Hypothesis

Reading the source with Claude Code, two things stood out: only honest
agents ever file reports (`nest_core/scenarios_builtin/reputation.py`), and
byzantine mode corrupts everything an agent sends
(`nest_core/sim/simulator.py`).

So my hypothesis was that raising `byzantine_agents` would not make cheaters
look worse, it would make them harder to see: fewer reports reaching the
observer, fewer warnings, and malicious agents scoring closer to neutral
because their behavior gets dropped instead of caught.

## How to reproduce

```
nest run reputation -o traces/reputation_baseline.jsonl
nest run ./reputation_byzantine.yaml -o traces/reputation_byzantine.jsonl
python analyze_reputation.py
```

`reputation_byzantine.yaml` is the base `reputation` scenario with exactly
one functional line changed: `failures.byzantine_agents: 0.0 -> 0.2`.

`nest`'s built-in metrics (`nest report`) don't cover reputation-specific
signal (report counts, warnings, per-agent scores), so `analyze_reputation.py`
replays the same `+1 good / -2 bad` scoring rule the `ObserverAgent` uses
internally, over the raw trace, to reconstruct exactly what the observer saw.

## Evidence

Baseline at 0.0: 80 reports reached the observer, 70 good and 10 bad, 3
warnings broadcast, malicious agents averaging -3.00 and honest agents 3.88,
across 620 messages and 101 unique pairs.

At 0.2: 38 reports, 35 good and 3 bad, 1 warning, malicious average up to
-1.00, honest average down to 2.46, 304 messages, 68 pairs.

| | Baseline (0.0) | Experiment (0.2) | Δ |
|---|---|---|---|
| Total reports reaching observer | 80 | 38 | **-52%** |
| Bad reports specifically | 10 | 3 | **-70%** |
| Warnings broadcast | 3 | 1 | -2 |
| Avg malicious agent score | -3.00 | **-1.00** | **+2.00 (less negative)** |
| Total message volume (`nest report`) | 620 | 304 | -51% |
| Unique interacting pairs | 101 | 68 | -33 |

What really matters is that bad reports fell 70 percent while total reports
fell 52 percent. The agents behaving worst came out of it looking better
than before.

## Investigating the surprise

What I didn't expect was malicious-0 vanishing. It scored -6 in the baseline
and disappears from the experiment with zero reports, good or bad, in
either direction.

I went into the raw trace, pulled every event involving it, and matched
sends against receives by correlation ID. Its cheat reply to honest-15
arrived as corrupted bytes, so honest-15 never recognized a cheat and filed
nothing. Its own trade requests were corrupted too, so nobody could respond
to those either. Malicious-0 had itself been flagged byzantine, and that
corrupts everything it sends, not just the messages tied to one interaction.
It wasn't harder to catch, it was erased from the reputation system in both
directions. That's a stronger failure mode than I predicted, and the more
concerning one, because the system can't tell the difference between an
agent behaving well and an agent it can't hear.

One more thing, and I want to be precise about what I actually checked:
honest agents' average score also fell, from 3.88 to 2.46. I verified why
rather than assume it was the same story as malicious-0. `HonestAgent`,
`MaliciousAgent`, and `ObserverAgent` (all in `reputation.py`) handle
`on_message` with an if/elif chain and no `else` branch, and nothing in the
scenario schedules a timeout or retry. A corrupted payload that doesn't
match `trade:`, `deliver:`, `cheat:`, or `report:` isn't rejected, it's
silently ignored: the method returns, the round never advances, and nobody
sends the next message. With `byzantine_agents=0.2` that happens throughout
the run, not only to malicious-flagged agents, so total activity drops and
honest agents end up with fewer interactions to be reported on too. This is
a reporting artifact of the no-retry design, not honest agents behaving any
worse.

## What I'd build next for NANDA Town

A "silence detector." My experiment showed that corrupted agents disappear
from the reputation record entirely, because reputation is built only from
reports that arrive. I'd build a service that tracks expected versus
received traffic per agent and flags the ones that go quiet or unreadable,
feeding that to the trust layer as evidence rather than as absence. Right
now, an agent nobody can hear from is scored the same as an agent that
isn't there.

## Use of AI / other help

I used Claude Code in PowerShell throughout: to read the installed
`nest-core` source and explain the delivery, failure-injection, and
reputation-scoring paths with file and line references; to run the `nest`
CLI (`scenarios cp`, `run`, `report`); and to write `analyze_reputation.py`,
which rebuilds reputation-specific metrics from the raw trace. I used the
NANDA Town quickstart and the writing-a-scenario doc for CLI syntax and YAML
structure. I also used Claude in the browser to pressure-test the experiment
design, including catching an unverified claim in an earlier draft about
why honest agents' scores dropped, which sent me back to the source to
confirm the mechanism before writing it up here.

The scenario, the setting, and the hypothesis were mine, arrived at by
questioning what the code actually did.
