# Security policy

Mojo OCR is an experimental, single-user local application. The current `main` branch is the supported development line; there is no response-time SLA or audited security guarantee.

## Report privately

Please use [GitHub private vulnerability reporting](https://github.com/goose4500/mojo-ocr/security/advisories/new) for suspected security vulnerabilities. Do not publish exploit details, credentials, or personal documents in an issue. Include a minimal synthetic reproducer, affected commit, platform, and impact where possible.

If private reporting is temporarily unavailable, open a public issue asking for a private contact **without disclosing the vulnerability**.

## Threat model and limits

- The HTTP UI binds to loopback, checks request host/origin, and requires a per-process token for mutations. This is defense against browser cross-origin access, **not authentication against other users/processes on the machine**.
- Do not expose the UI over a public tunnel, reverse proxy, or shared network interface.
- Native image/PDF parsers and the private Mojo C ABI are not a sandbox. Avoid hostile inputs and keep dependencies current. Buffer validation does not make arbitrary native calls safe.
- Upload/page/pixel limits reduce resource use but do not guarantee resistance to all denial-of-service inputs.
- Documents, model corrections, exported files, and indexes are unencrypted. Temporary files can remain after a crash or forced termination. Disk encryption and appropriate OS permissions are the user's responsibility.
- Model confidence is not a safety or correctness guarantee. Verify sensitive text against the source.

Do not attach private documents to security reports unless genuinely necessary and explicitly agreed upon. Prefer generated fixtures.
