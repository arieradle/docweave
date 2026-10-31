- source_spec: `_bmad-output/implementation-artifacts/spec-0-0-development-environment-with-frappe-v16-and-erpnext.md`
  summary: Add an automated check that runs post-create.sh twice against the Compose stack and asserts the rebuild path skips reinstall and never wipes the bench.
  evidence: The repo has no CI or shell-test harness; idempotency and the destructive-recovery guards are verified only manually (verification-gap review, Story 0.0 loop 1).
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-spike-time-the-per-candidate-permission-check-ad-4.md`
  summary: Apply Spike 0.1's AD-4 decision to the planning docs: the scan budget default in the architecture's "Default limit values", Story 2.3's defaults and tests, and Story 1.2's DocWeave Settings default.
  evidence: The spike report's decision names these changes; the architecture still marks the 2,000 budget as [ASSUMPTION]. Changing planning docs is the human's call (correct-course).
  resolved: 2026-10-31. The human chose 200 after Spike 0.2. Applied to the architecture's "Default limit values" and to Stories 1.2 and 2.3.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-4-fast-start-for-new-codespaces.md`
  summary: Add a CI job that runs post-create.sh against a MariaDB service and tests the orphaned-site recovery (database present keeps the site; database absent moves the folder and recreates it).
  evidence: The recovery path moves a site folder on every codespace start when it misfires, and only manual tests cover it (Story 0.4 review, finding 14).
- source_spec: `_bmad-output/implementation-artifacts/spec-0-4-fast-start-for-new-codespaces.md`
  summary: Warn in dev-image.yml when docker-compose.yml's image tag does not match the pins in post-create.sh after a publish.
  evidence: A forgotten second bump push leaves new codespaces on an old bench, which then stops with version drift; no CI signal (Story 0.4 review, finding 15).
