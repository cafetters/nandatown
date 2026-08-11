# SPDX-License-Identifier: Apache-2.0
"""Reputation-specific analysis not covered by nest's built-in metrics.

Counts reports reaching the observer, warning broadcasts, and reconstructs
each agent's final score by replaying the same +1 good / -2 bad rule the
ObserverAgent uses internally (see reputation.py). Compares baseline
(byzantine_agents=0.0) against the experiment (byzantine_agents=0.2).

Run from a directory containing traces/reputation_baseline.jsonl and
traces/reputation_byzantine.jsonl (see README.md for how to generate them).
"""

from __future__ import annotations

import json
from pathlib import Path


def load_events(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def analyze(path: Path) -> dict:
    events = load_events(path)

    reports = []  # (round, agent, outcome)
    warnings = []  # (ts, round, agent)
    scores: dict[str, int] = {}

    for ev in events:
        kind = ev.get("kind", "")
        msg = ev.get("msg", "")

        if kind == "send" and msg.startswith("report:"):
            parts = msg.split(":")
            if len(parts) >= 4:
                rnd, agent, outcome = parts[1], parts[2], parts[3]
                reports.append((rnd, agent, outcome))
                scores.setdefault(agent, 0)
                scores[agent] += 1 if outcome == "good" else -2

        elif kind == "broadcast" and msg.startswith("warning:"):
            parts = msg.split(":")
            if len(parts) >= 4:
                warnings.append((ev.get("ts", 0.0), parts[1], parts[2]))

    good = sum(1 for _, _, o in reports if o == "good")
    bad = sum(1 for _, _, o in reports if o == "bad")

    return {
        "total_reports": len(reports),
        "good_reports": good,
        "bad_reports": bad,
        "warnings": warnings,
        "scores": scores,
    }


def print_run(label: str, result: dict) -> None:
    print(f"\n=== {label} ===")
    print(f"total reports reaching observer: {result['total_reports']}")
    print(f"  good: {result['good_reports']}   bad: {result['bad_reports']}")
    print(f"warnings broadcast: {len(result['warnings'])}")
    for ts, rnd, agent in result["warnings"]:
        print(f"  ts={ts:.1f} round={rnd} agent={agent} -> untrusted")

    malicious = {a: s for a, s in result["scores"].items() if a.startswith("malicious")}
    honest = {a: s for a, s in result["scores"].items() if a.startswith("honest")}

    print("malicious agent final scores:")
    for a in sorted(malicious, key=lambda x: malicious[x]):
        print(f"  {a}: {malicious[a]}")
    print("honest agent final scores:")
    for a in sorted(honest, key=lambda x: honest[x]):
        print(f"  {a}: {honest[a]}")

    if malicious:
        avg_malicious = sum(malicious.values()) / len(malicious)
        print(f"avg malicious score: {avg_malicious:.2f}")
    if honest:
        avg_honest = sum(honest.values()) / len(honest)
        print(f"avg honest score: {avg_honest:.2f}")


if __name__ == "__main__":
    baseline = analyze(Path("traces/reputation_baseline.jsonl"))
    byzantine = analyze(Path("traces/reputation_byzantine.jsonl"))

    print_run("baseline (byzantine_agents=0.0)", baseline)
    print_run("experiment (byzantine_agents=0.2)", byzantine)

    print("\n=== delta (experiment - baseline) ===")
    print(f"total reports: {byzantine['total_reports'] - baseline['total_reports']}")
    print(f"bad reports:   {byzantine['bad_reports'] - baseline['bad_reports']}")
    print(f"warnings:      {len(byzantine['warnings']) - len(baseline['warnings'])}")

    b_mal = {a: s for a, s in baseline["scores"].items() if a.startswith("malicious")}
    x_mal = {a: s for a, s in byzantine["scores"].items() if a.startswith("malicious")}
    if b_mal and x_mal:
        b_avg = sum(b_mal.values()) / len(b_mal)
        x_avg = sum(x_mal.values()) / len(x_mal)
        print(f"avg malicious score: baseline={b_avg:.2f}  experiment={x_avg:.2f}  delta={x_avg - b_avg:+.2f}")
