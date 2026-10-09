# WordPress target-local verifier release copy

This file is a packaging copy of the canonical Project Brain verifier at
`lifeenergy-eu/project-brain:control-plane/controlled-execution/target_local_ticket.py`, GitHub source commit `3a82c86b9e1ad587d12b3776d3fc44a57e0e1727`.

Only the **canonical Project Brain owner** defines ticket schemas, issuer and
verification behavior. This packaged copy has no separate runtime authority and
contains no secrets. It must be installed only as an attested exact-SHA source
artifact to `trusted/target_local_ticket.py` on the WordPress host; all
signing keys are separately provisioned by existing canonical Run Core policy.

A packaged verifier alone does not enable native execution. No extra MCP
route, independent issuer, runner, shell or token is provided here.
