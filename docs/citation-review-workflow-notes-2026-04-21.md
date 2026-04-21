# Citation / review workflow notes

Date: 2026-04-21
Context: live CUV initiation debugging and workflow design review

## Core conclusion

Citation should not be treated only as a terminal pass/fail gate after the report is written. It should also act as a bounded revision signal for the lead.

Current behavior observed in AZIMUTHFM:
1. Lead writes report
2. Red-team reviews
3. Citation runs
4. If citation finds unsourced claims, pipeline fails closed

Desired behavior discussed:
1. Lead draft
2. Red-team review
3. Lead revision from red-team feedback
4. Citation scan
5. Lead revision from citation feedback
6. Citation re-check
7. Ship if clean

## Why this ordering

- Red-team is a thesis / valuation / risk reviewer.
- Citation is an attribution / grounding reviewer.
- Red-team should happen before final prose is locked.
- Citation should happen after substantive argument is mostly settled.
- Citation should not replace red-team.
- Citation should not be the first reviewer.

## Practical interpretation

- Red-team shapes the argument.
- Citation trims unsupported residue.
- The same lead should handle both revisions in sequence.
- Avoid spawning a second separate lead agent after citation failure.

## Bounded revision policy

Recommended bounded loop:
1. Lead 1
2. Red-team
3. Lead 2 (red-team revision)
4. Citation 1
5. Lead 3 (citation-only repair pass)
6. Citation 2
7. Done or fail closed

Use at most:
- 1 red-team reopen
- 1 citation reopen

Avoid endless loops.

## Important claim handling

Prompt policy discussed and adopted:
- If a claim is important to thesis, valuation, risks, or catalysts and is likely sourceable from public materials or already-collected evidence, the lead should make one bounded effort to source or reconcile it before dropping or narrowing it.
- If that bounded effort fails, prefer the strongest narrower supported claim.

Citation policy discussed and adopted:
- If a flagged claim looks important and likely sourceable, citation should describe it precisely in `unsourced_claims` so the lead can research/reconcile it on revision instead of silently deleting it.

## General precision rules worth preserving

For the lead:
- Name the exact accounting/disclosure definition used when multiple definitions exist.
- Do not present market interpretation or investor-motivation narratives as fact unless sourced.
- Do not use evaluative language unless supported by findings and/or computation output.
- Do not narrate intermediate valuation outputs unless they exist in computation log or are directly derivable from logged inputs.
- Prefer narrower fully supported claims over broader elegant claims that overreach.

For citation:
- Mixed accounting definitions should be treated as unsupported unless wording is narrowed to the exact sourced definition.
- Market-causality language should require direct support.
- Intermediate valuation numbers not present in computation log should be treated as unsupported.

## Self-healing principle discussed

Do not abort on:
- "material caveat exists"

Abort only on:
- "material caveat remains unresolved after one bounded repair pass"

General decision rule:
- material_caveat -> attempt_repair_once -> {resolved | narrowed | blocked}
- abort only on blocked

## Notes from CUV debugging

Observed structural issue:
- runtime gates were initially treating caveat-like wording as terminal before the lead's repair step could count as success
- after narrowing false-positive gates, the pipeline advanced to citation, which is a healthier failure mode

Observed citation failure class:
- unsupported evaluative prose
- unsupported market-causality statements
- unsupported intermediate valuation numbers
- loose accounting-definition mixing

## Future implementation candidate

Consider turning citation from a pure terminal validator into:
- citation reviewer pass
- lead repair pass
- citation confirmation pass

while still keeping fail-closed after the bounded repair loop.
