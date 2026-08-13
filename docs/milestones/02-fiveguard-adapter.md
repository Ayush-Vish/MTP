# Milestone 2: SecGuard-to-5Guard input adapter

## Objective

Turn SecGuard policy output into an input accepted by the original 5Guard slice
allocator without mutating the customer request or weakening its SLA.

## Upstream interface

- Repository: `https://github.com/mehdibolourian/5Guard.git`
- Tested revision: `adadaccfcb6febfbf9e73eaf83541a9d20e7c5d0`
- Input class: `data.sr`
- Isolation field: `gamma`, where 0=L0, 1=L1, and 2=L2.

The upstream code is downloaded under ignored `external/5guard`; it is not
vendored into this repository.

## Implementation

`adapt_slice_request` validates that the decision and request refer to the same
original isolation level, shallow-copies the request, and changes only the copy's
`gamma`. Quarantine decisions return no optimizer request.

Safety invariants:

1. Input `gamma` remains unchanged.
2. Target `gamma` is one of 0, 1, or 2.
3. Target `gamma` cannot be below the original SLA value.
4. Quarantine never enters 5Guard as an invented isolation level.
5. Revenue, deadlines, topology, and resource requirements remain intact.

## Results

| Slice | Before | SecGuard action | Optimizer input |
|---|---:|---|---|
| eMBB | L0 | Keep | `sr(gamma=0)` |
| mMTC | L0 | Upgrade L1 | `sr(gamma=1)` |
| uRLLC | L1 | Upgrade L2 | `sr(gamma=2)` |
| Mission-critical | L2 | Quarantine | Withheld |

- Decisions handled: 4/4.
- Valid optimizer requests: 3/3 non-quarantine decisions.
- Input requests unchanged: 4/4.
- Non-security fields preserved: 4/4.
- Adapter tests: 6/6 passed.
- Complete project tests: 11/11 passed.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\fetch_5guard.py
.\.venv\Scripts\python.exe -m secguard.fiveguard_demo
.\.venv\Scripts\python.exe -m pytest -q
```

Evidence: `artifacts/fiveguard_adapter.json`.

## Improvement over Milestone 1

Milestone 1 stopped at a JSON recommendation. Milestone 2 establishes a tested
boundary with the real 5Guard data model. Isolation upgrades can now enter the
allocator, and quarantine has explicit pre-optimizer semantics.

## Blocker for allocator-level claims

The environment has neither `gurobipy` nor `gurobi_cl`. Consequently, this
milestone makes no claim about profit, admission, migration, resource efficiency,
or optimization runtime. Those measurements begin only after Gurobi and a valid
licence are available.

