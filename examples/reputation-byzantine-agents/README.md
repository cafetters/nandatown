# Experiment: does `byzantine_agents` catch more cheaters, or hide them?

Part A/B/C exercise for the NANDA Town quickstart. Scenario: `reputation`.
Setting changed: `failures.byzantine_agents` (`0.0` -> `0.2`), one setting,
everything else identical (same seed, same agent counts, same rounds).

## Why this scenario

I ran through the quickstart and then looked at what built-in scenarios were
available (`nest scenarios list`): `auction`, `consensus`, `marketplace`,
`reputation`, `shell_marketplace`, `supply_chain`, `voting`. I picked
`reputation` because it's a scenario about trust, not just message delivery:
honest agents trade reliably, malicious agents sometimes cheat, and an
observer keeps score and calls out bad actors once they cross a threshold.
That felt like a more interesting system to break than a simple buy/sell
negotiation.

## Hypothesis

My first instinct was: if I turn up `byzantine_agents`, reputation scores
should just go down more, since I'm adding another way for things to go
wrong on top of the cheating that's already happening.

But once I actually read how the observer gets its information
(`nest_core/scenarios_builtin/reputation.py`), I don't think that's right.
Reports only flow one way: the agent that *initiated* a trade is the one who
reports on whoever responded, and only honest agents ever send a report —
malicious agents never report anyone, even when they catch another malicious
agent cheating them. So a lot of bad behavior is already invisible to the
observer before `byzantine_agents` even enters the picture.

What `byzantine_agents` actually does is corrupt the *outgoing* messages of
whichever agents get flagged (confirmed in `nest_core/sim/simulator.py`). If
a malicious agent gets flagged and its `cheat:` reply gets corrupted on the
way to an honest trader, that honest trader never recognizes it as a cheat —
so it never sends the "bad" report that would've hurt that agent's score.
There's no retry, so that report is just gone.

**So my actual hypothesis is the opposite of my first guess:** increasing
`byzantine_agents` won't push reputation scores down further — it'll
suppress the observer's ability to detect bad behavior at all. I expect
fewer total reports reaching the observer as `byzantine_agents` goes up,
fewer (or later) warning broadcasts, and malicious agents potentially ending
up with *less* negative scores than in the base case — not because they're
behaving better, but because their bad behavior is getting silently dropped
before anyone can report it. In other words, adding byzantine failures
should mask cheating rather than expose more of it.

**What I checked to confirm or falsify this:** how many `report:` messages
actually reach the observer, how many `warning:` broadcasts go out, and
whether malicious agents' final scores end up higher (less negative) than in
the base case.

## How to reproduce

```
nest run reputation -o traces/reputation_baseline.jsonl
nest run reputation_byzantine.yaml -o traces/reputation_byzantine.jsonl
python analyze_reputation.py
```

`reputation_byzantine.yaml` is the base `reputation` scenario with exactly
one line changed: `failures.byzantine_agents: 0.0 -> 0.2`.

`nest`'s built-in metrics (`nest report`) don't cover reputation-specific
signal (report counts, warnings, per-agent scores), so `analyze_reputation.py`
replays the same `+1 good / -2 bad` scoring rule the `ObserverAgent` uses
internally, over the raw trace, to reconstruct exactly what the observer saw.

## Evidence

| | Baseline (0.0) | Experiment (0.2) | Δ |
|---|---|---|---|
| Total reports reaching observer | 80 | 38 | **-52%** |
| Bad reports specifically | 10 | 3 | **-70%** |
| Warnings broadcast | 3 | 1 | -2 |
| Avg malicious agent score | -3.00 | **-1.00** | **+2.00 (less negative)** |
| Total message volume (`nest report`) | 620 | 304 | -51% |
| Unique interacting pairs | 101 | 68 | -33 |

This matches the hypothesis: adding byzantine corruption didn't push scores
further down, it suppressed detection. Fewer reports overall, way fewer bad
reports specifically, fewer warnings, and malicious agents looking better on
average, not worse.

## Investigating the surprise

The one thing I didn't expect going in: `malicious-0` has a real score in
the baseline (-6) but doesn't appear in the experiment's results at all —
zero reports, good or bad, in either direction.

I traced this by grepping the raw experiment trace for `malicious-0`. It
turns out `malicious-0` itself got flagged byzantine. Every message it sends
comes out corrupted — for example its `cheat:1:malicious-0` reply to
`honest-15` arrives as unreadable bytes (same `corr` correlation ID, garbled
payload), so `honest-15` never recognizes it as a cheat and never files a
report. The same thing happens to `malicious-0`'s own `trade:` requests when
it's the initiator — nobody can respond to gibberish, so those threads never
go anywhere either.

So this isn't just "harder to catch" — being flagged byzantine can erase an
agent from the reputation system completely, in both directions (as cheater
and as trader), since corruption applies to every message that agent sends,
not just the ones relevant to a specific interaction. That's a sharper
version of the hypothesis than I'd predicted: masking isn't always partial.

One more thing worth noting, not surprising but worth being honest about:
honest agents' average score also dropped (3.88 -> 2.46 in my full run
output). That's not a separate effect — it's the same no-retry mechanism:
byzantine corruption stalls negotiation threads early throughout the system
(not just malicious-flagged ones), so there's less total activity for
anyone, honest or malicious, to be reported on.

## Use of AI / other help

I used Claude Code (an AI coding assistant) throughout this exercise:
- To explore the installed `nest-core` package source and explain how
  message delivery, failure injection, and the reputation scenario's
  scoring actually work at the code level (which methods call which, in
  what order) — I asked it to show me the exact file/line evidence before
  I trusted any claim about the mechanism.
- To run the `nest` CLI commands and write `analyze_reputation.py`, the
  small script used to reconstruct reputation-specific metrics from the
  raw trace (since the built-in metrics don't cover this scenario).

The choice of scenario, the setting to change, and the hypothesis (including
correcting my own first guess after understanding the reporting mechanism)
were mine — I worked through the reasoning with the assistant asking me
clarifying questions and citing code rather than handing me conclusions.
