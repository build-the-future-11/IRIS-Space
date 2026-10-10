# Residual-memory identity and input contract

The development residual-memory bank now owns immutable byte snapshots of its
keys, residual values and normalized metric weights. Array properties return
fresh, read-only NumPy views. Reassigning a bank setting, modifying an array,
changing its dtype or shape, or mutating the caller's original input cannot
change a bank while retaining its recorded digest.

Bank entry identifiers must be unique. Keys and residuals must have at least one
quaternion channel and contain finite real values; booleans, complex values and
numeric strings are rejected. Neighbor counts must be positive integers. The
cross-population switch must be an explicit boolean, and forced gates are
validated even when no neighbors are eligible. The source-group, time,
population and calibration exclusion rules otherwise retain their prior meaning.

The uniform-metric CLI memory artifact retains its v1 schema. Loading it now
validates its schema, entry count, settings and reconstructed memory digest
before retrieval. Previously the routing command ignored the recorded digest.
Valid existing artifacts still load, including the historical representation of
integer JSON cutoffs that the CLI hashed as floats. Routed evidence with an
enabled memory now includes the bank digest in `memory_route`.

For very large finite metric weights, normalization rescales before averaging
when the direct mean overflows. Unrepresentable distances, residual averages or
corrected forecasts raise `ValueError`; a supported retrieval never carries a
NaN or infinite numerical result. This changes invalid numerical handling,
without replacing retained study artifacts or their implementation revisions.

These changes are development engineering corrections. The tests use constructed
arrays and a local CLI fixture. They do not establish temporal availability of
the residual's future target, raw-source disjointness, canonical source
population identity, performance, discovery yield or promotion eligibility.
The existing study freezes and protected evaluation boundaries remain in force.
