# Security policy

## Supported versions

MyTicket is currently a demonstration and learning project. Security fixes are
applied to the latest revision on the `main` branch; older revisions are not
maintained as separate release lines.

## Reporting a vulnerability

Do not open a public issue for suspected vulnerabilities, leaked credentials,
authorization bypasses, or privacy problems. Use GitHub's private vulnerability
reporting option on the repository **Security** page when it is enabled.

Include, where possible:

- affected endpoint, tool, or workflow;
- reproduction steps and required account role;
- observed and expected behavior;
- potential impact;
- a minimal proof of concept without real customer data.

Do not include API keys, access tokens, real passwords, or personal customer
data in a report. This repository contains synthetic demonstration data only.

## Deployment notice

The sample credentials and local defaults are intended only for local
demonstration. Before any shared or internet-facing deployment, replace every
secret, enable HTTPS-secure cookies, restrict metrics access, and review the
production boundaries documented in the main README.
