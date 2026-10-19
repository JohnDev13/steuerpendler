# ESTV 2026 standard budget: estimated rent

## Owner-selected standard-default policy

The product owner selected ESTV standard defaults throughout rather than new
personal-expense inputs. Accordingly, rent may use this fixed-profile estimate
when presenting a clearly labelled estimate/disclaimer. It must not be shown as
a user's personal rent, an official value for arbitrary profiles, or evidence of
production approval.

## Evidence-based model

All 29 captured native ESTV 2026 budget responses in
`tests/reference/estv-2026/estv-2026-*-budget.response.json` satisfy:

```text
MIETAUSGABEN = nearest CHF 10 to
               25% × (NETTOLOHN_P1 + NETTOLOHN_P2)
```

Ties are rounded upward. The pure helper
`estimateAnnualRent2026FixedProfile` implements that observed relationship.
This is an evidence-based reconstruction for the fixed 2026 capture profile,
not source-published ESTV backend code and not a person's actual rent.

## Verification and coverage limits

The model matches 29/29 captures exactly. Captured combined annual net income
ranges from CHF 54,243 to CHF 362,539; every capture has
`NETTOLOHN_P2 = 0`. Therefore the evidence does not establish behavior for
other tax years, profile settings, negative income, non-finite values,
two-earner households, values outside that observed range, or future ESTV
changes. The helper accepts finite non-negative inputs and rejects invalid
inputs, but behavior beyond the captures remains an explicit extrapolation.
