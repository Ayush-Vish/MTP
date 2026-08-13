# Claim ledger

This ledger prevents the draft or presentation from overstating the evidence.

## Supported now

- The ML-selected policy improved mean profit by 164.92% over fixed SecGuard on
  30 held-out trace-derived scenarios.
- Mean admission improved by 27.94% and quarantine frequency fell by 70.00%
  versus fixed SecGuard.
- Learned SecGuard retained 90.44% of static 5Guard mean profit while reducing
  the isolation-exposure proxy by 67.12%.
- The paired mean profit gain over fixed SecGuard was 4579.49 with a
  normal-approximation 95% CI of [2206.50, 6952.49].
- The paired learned-versus-fixed profit difference was significant under a
  two-sided Wilcoxon test (p=0.0028), with paired Cohen's dz=0.69.
- Learned exposure was below static exposure in 29 of 30 scenarios (one tie),
  with p=2.56e-6 and paired Cohen's dz=-3.43.
- Learned held-out profit was 2.41% below the exhaustive training oracle; the
  paired difference was not significant (p=0.2843).
- The learned search evaluated 81 policies instead of the exhaustive 165,
  avoiding 84 policies or 420 five-scenario allocator runs in this design.
- A local warm-batch benchmark measured 47.66 microseconds per detector packet
  and 1.21 microseconds per threshold decision; disk I/O, model loading,
  telemetry transport, and network reconfiguration were excluded.
- The original 5Guard request object is not mutated and its SLA level cannot be
  lowered by the adapter.

## Must be qualified

- Say "modeled isolation-exposure proxy," not attack containment.
- Say "held-out trace-derived scenarios," not independent deployments.
- Say "5Guard IAR synthetic topology," not full 5Guard or a real network.
- Say "within-source held-out classifier result," not general detection rate.
- Say "preliminary" or "proof of concept" for the current evaluation.
- Say the surrogate reduced expensive evaluations in this run, not that it was
  more sample-efficient than random search.
- Report local warm-batch inference timing, not end-to-end containment latency.

## Not supported yet

- Generalization to unseen attacks, networks, or traffic distributions.
- Measured prevention of cross-slice attack propagation.
- Superiority on the BRAIN topology or with the full 5Guard ensemble.
- Real-time production performance or operational deployment readiness.
- A claim that security has no economic cost.
- Superiority of the Random-Forest surrogate over equal-budget random search;
  Random-81 found the exact exhaustive training oracle.
- A security benefit from quarantine; replacing quarantine with L2 increased
  raw profit by 19.25%, while the current exposure proxy was unchanged.
