# Release and study approval intake

No repository automation may impersonate these decisions. Every approval below must
name a human owner, date, exact artifact digest or Git tag, decision, and any scope
restriction. A blank row blocks final publication or prospective protocol freeze.

| Decision | Required approver | Exact object to approve | Status |
|---|---|---|---|
| Historical attribution | campaign/data owner | TNS capture plus summary-attributed claims | PENDING |
| Raw/data redistribution | data copyright/licensing owner | dataset manifest and redistribution terms | PENDING |
| Source-code license | repository copyright owner | `LICENSE` and dependency notices | PENDING |
| Authorship/order/affiliations | every listed author | final author block and CRediT statement | PENDING |
| Prospective protocol | PI, statistician, operations owner | frozen protocol digest | PENDING |
| Independent outcome review | designated independent adjudicators | outcome taxonomy and blinded packets | PENDING |
| Venue/compliance | corresponding author and institutional reviewer | venue, policy checklist, disclosures | PENDING |
| Final artifact release | corresponding author and release owner | clean verifier digest and signed tag | PENDING |

Replace `PENDING` only with a signed or otherwise attributable decision. Do not put
credentials, private keys, or personal signatures in Git; archive a reference to the
approved institutional record when the approval itself must remain private.
