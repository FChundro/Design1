# Composio automations

Optional, event-driven automations that connect this project's GitHub, chat, and
inbox activity to small handlers through [Composio](https://composio.dev)'s
managed triggers and tool calls. Composio owns the OAuth/token storage for each
connected app, so this package only deals with trigger events and action slugs —
never raw credentials.

> These automations are **off by default** and are not imported by the FCC
> server. Nothing here runs unless you install the extra and start the runner.

## What's included

| Automation      | Trigger                          | What it does |
|-----------------|----------------------------------|--------------|
| `issue_triage`  | new GitHub issue                 | Heuristically labels the issue and posts a summary to your chat channel. |
| `ci_failure`    | GitHub workflow run completed    | Alerts the channel when a run ends in failure / timeout. |
| `release_notes` | GitHub release published         | Announces the release, and emails the notes if `COMPOSIO_DIGEST_EMAIL` is set. |
| `inbox_to_issue`| new Gmail message                | Files emails carrying a chosen label as GitHub issues. |

## Setup

1. **Install the Composio SDK** (kept out of the project lockfile, since these
   automations are optional)

   ```bash
   uv pip install composio   # or: pip install composio
   ```

2. **Connect the apps in Composio.** In the Composio dashboard, connect the
   GitHub, Gmail, and Discord/Slack toolkits for the user id you'll run as
   (default entity id: `default`).

3. **Configure the environment.** Copy the `COMPOSIO_*` block from
   [`.env.example`](../../../../.env.example) into your env file and fill it in.
   At minimum you need `COMPOSIO_API_KEY`, `COMPOSIO_GITHUB_REPO`, and a
   notification target.

4. **Verify the slugs resolve against your account** (recommended — action and
   trigger slugs are server-side and can change between toolkit versions):

   ```bash
   python -m free_claude_code.automations.composio verify
   ```

5. **Run it** (arms the triggers, then blocks and dispatches events):

   ```bash
   python -m free_claude_code.automations.composio run
   ```

   `list` prints the enabled automations without connecting.

## How it fits together

```
triggers.subscribe() ──► AutomationEvent ──► dispatch() ──► handler(event, Actions, settings)
                                                              └► Actions ──► tools.execute(slug, …)
```

- **`config.py`** — `ComposioSettings`, validated from `COMPOSIO_*` env vars.
- **`slugs.py`** — every Composio trigger/action slug in one place (the one thing
  `verify` checks against the live account).
- **`client.py`** — lazy client construction (`composio` stays an optional
  import) plus `verify` and response-unwrapping helpers.
- **`actions.py`** — `Actions`, product-level operations mapped onto single tool
  calls (`create_issue`, `notify`, `send_email`, …).
- **`handlers.py`** — pure handler functions and the trigger→handler registry.
- **`runner.py`** / **`__main__.py`** — arm triggers, subscribe, and the CLI.

The handlers are pure with respect to Composio, so they're unit-tested with a
recording fake in [`tests/automations/`](../../../../tests/automations/) — no
network or API key required.

## Extending

Add an action wrapper in `actions.py`, write a `handle_*` function in
`handlers.py`, register it in `_REGISTRY` with its trigger slug, and add the name
to `ALL_AUTOMATIONS` in `config.py`. Add the new slugs to `slugs.py` so `verify`
covers them, and a test in `tests/automations/`.
