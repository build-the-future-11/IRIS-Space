# Security policy

SIDEREA 0.3 is a local, human-supervised research platform. It is not a hardened
multi-user service and contains no unattended Transient Name Server submission
path. Security reports should describe the affected version, the smallest safe
reproduction, and the expected impact. Send them privately to
`ryangomez.hs@gmail.com` and `aadinair310@gmail.com`; do not include live API keys,
private observations, or other third-party secrets.

Only the latest 0.3.x release receives security fixes. The historical root scripts
and `cool-stuff-master/` are retained for migration comparison and are outside the
supported runtime boundary. The maintained code is `src/siderea/`, with packaging and
dependency policy in `pyproject.toml`.

## Security boundaries

- The review server is for loopback use. It validates loopback `Host` headers,
  requires a per-process CSRF token, limits form size and shape, emits restrictive
  browser headers, and has no report or follow-up endpoint. It does not provide
  identity authentication. Do not expose it directly to a network.
- Reviewer and adjudicator names are normalized audit labels, not authenticated
  principals. A multi-user deployment requires an identity provider,
  authorization, TLS termination, signed decisions, backups, monitoring, and a
  separate threat review.
- TNS credentials are runtime-only environment variables. Supply all of
  `TNS_API_KEY`, `TNS_BOT_ID`, and `TNS_BOT_NAME`, or none. Never place them in
  TOML, source, fixtures, shell history, issue reports, or committed `.env` files.
- Baseline `joblib` bundles are executable serialization. `load_baseline_bundle`
  requires explicit trust consent and verifies the bundle hash, but a matching
  hash does not establish who created it. Load only artifacts from a trusted
  origin. JEPA checkpoint loading uses PyTorch's restricted `weights_only` mode.
- SHA-256 values in manifests, evidence records, and review sets detect accidental
  or out-of-band changes relative to the recorded digest. They are integrity
  identifiers, not digital signatures and not protection from a malicious local
  administrator.
- Network errors, malformed service replies, missing provenance, stale evidence,
  and disabled checks fail closed. No model score can override those gates.

## Dependency and release hygiene

CI uses read-only repository permissions, full-commit pins for third-party
actions, branch-aware coverage, static typing, package-isolation smoke tests, and
dependency vulnerability auditing. Dependabot tracks Python and GitHub Actions
updates. Before a release, run the complete gate in `CONTRIBUTING.md`, inspect the
dependency-audit result, build from a clean source tree, and verify the wheel in a
fresh environment.
