# Codex plugin acceptance gate

A plugin is not operational merely because its package exists or the CLI says
`installed, enabled`. Every Codex-owned plugin integration must pass all four
gates before anyone reports it as working:

1. **Installed** — `codex plugin list` reports the expected marketplace plugin.
2. **Enabled** — the current Codex configuration enables that exact selector.
3. **Authenticated** — the Codex app reports a connected account without
   exposing tokens or OAuth callback data.
4. **Live API** — a new Codex thread exposes the plugin tools and completes the
   smallest non-mutating API read.

Run the secret-free installation check with:

```bash
python -m voice_suite.codex_plugin_health google-calendar
```

Exit `3` means installation is present but functional readiness is deliberately
unverified. Authentication and a live read cannot be inferred from files or
from marketplace cache state.

## Google Calendar acceptance

- Install `google-calendar@openai-curated` through the Codex plugin CLI or app.
- Start a new Codex thread so its tool inventory is rebuilt.
- Complete the Google connection in the Codex app; do not copy Hermes tokens.
- Confirm the thread actually has Google Calendar tools.
- Perform one read-only request, such as listing calendar names or the number of
  events in a short window. Do not create, update, or delete an event for smoke
  testing.
- Record plugin selector, installed version, test time, command/tool outcome,
  and next action. Never record event content, account identifiers, or tokens.

If any gate lacks evidence, report `INCOMPLETE`, not `READY`. Re-run the live
read after upgrades, reauthentication, configuration changes, or unexplained
tool disappearance.

## Ownership

Codex owns plugin selection, installation, authentication health, live checks,
and cross-system knowledge integrations. Hermes may submit requirements and use
an exposed contract, but it does not certify Codex plugin readiness.

## Recorded verification

As of 2026-09-10 12:19:30 +09:00:

- Selector: `google-calendar@openai-curated`
- Installed and enabled: yes, version `1e285826`
- Authentication: confirmed by the connected read-only Calendar tool
- Live API: passed; a calendar-list read completed without reading event contents
- Remaining local-adapter setup: `client_secret.json` is still required only for
  the repository's standalone OAuth CLI (`google_calendar_cli`)
