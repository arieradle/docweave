- source_spec: `_bmad-output/implementation-artifacts/spec-0-0-development-environment-with-frappe-v16-and-erpnext.md`
  summary: Add an automated check that runs post-create.sh twice against the Compose stack and asserts the rebuild path skips reinstall and never wipes the bench.
  evidence: The repo has no CI or shell-test harness; idempotency and the destructive-recovery guards are verified only manually (verification-gap review, Story 0.0 loop 1).
