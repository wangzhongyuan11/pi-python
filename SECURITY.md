# Security policy

## Supported versions

Before the first stable release, security fixes are made only on the current
`main` branch. After stable releases begin, the latest released minor line and
`main` are supported unless a release note states otherwise.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting from the repository's **Security**
tab. If private reporting is unavailable, contact the repository owner through
a verified private channel. Do not disclose the issue in a public issue,
discussion, pull request, log, transcript, or test fixture.

Include the affected revision, platform, reproduction steps, impact, and any
known mitigation. Remove API keys, session content, personal data, and other
secrets from the report. Maintainers should acknowledge receipt privately,
validate the report, coordinate a fix, and publish disclosure details only
after affected credentials are revoked and users have a remediation path.

## Secrets and provider access

Never commit provider keys. Keep them in an ignored local `.env` file or the
platform's secret store; `.env.example` contains only an invalid placeholder.
If a key appears in Git history, logs, fixtures, or an issue, revoke and rotate
it immediately. Deleting the visible line is not sufficient because Git
history and caches may retain it.

The default test suite is deterministic and offline. Before collection it uses
fake providers, sanitized credentials, and isolated HOME/cwd directories. The
test bootstrap blocks Python networking, Python children, and common native
network clients, but it is not an OS firewall for arbitrary raw-socket
binaries. Such tests must use fake operations or an isolated runner.
Live-provider tests require an explicit environment opt-in and approval for
that exact run, must not run on pull requests, and must never print secrets.
Dependency auditing and installation are separate CI operations that may access
their public package and vulnerability registries.

## Trust boundaries

Agent tools can read files and execute commands with the permissions of the
process running pi-python. Review tool requests and extension code before use;
Python-native extensions are trusted code, not a security sandbox. Session
files may contain prompts, tool output, paths, and provider metadata and should
be protected like other sensitive local data.

Remote RPC, remote clients and servers, AgentHarness, and SQLite storage are
outside the 1.0 security boundary. Adding any of them requires a separate
threat model and security review.
