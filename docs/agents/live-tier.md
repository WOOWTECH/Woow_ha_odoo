# Live tier: the test host

The Live tier is the only tier that answers whether Ingress and the Public
origin behave the same on a real machine. This file is how an agent runs it —
including an unattended Sweep Iteration, which has nobody to answer a
permission prompt.

**What is authorised, and what is not:
[ADR 0012](../adr/0012-sweeps-verify-on-the-test-host.md).** Read the boundary
there before the first command. In short: this one test host, its two Odoo
add-ons and their databases, writes included; no customer or production Odoo,
including the instances behind the `woowtech_odoo` MCP server.

## Credentials

They live in the **git-ignored `.env` of the main checkout**, at the absolute
path `/projects/Woow_ha_odoo/.env`. A Sweep Iteration works in a worktree, and
an untracked file is not in a worktree — so always pass the absolute path, never
`./.env`:

```sh
~/venvs/woow/bin/python odoo18ce/tests/e2e_parity_shared_layers_live.py \
  pcheck --env-file /projects/Woow_ha_odoo/.env --db odoo_parity
```

It holds the names the e2e scripts read: `HA_BASE_URL`, `HA_TOKEN`,
`ADDON_SLUG`, `ODOO_PUBLIC_URL`, `ODOO_TEST_LOGIN`, `ODOO_TEST_PASSWORD`,
`ODOO_DB`, `PARITY_TARGET`, `IGNORE_HTTPS_ERRORS`, `E2E_ARTIFACT_DIR`.

- **Never print the file or a value from it** — no `cat`, no `echo $HA_TOKEN`,
  nothing that puts one in a transcript, an Issue, a pull request or a commit.
  To check a name is set: `awk -F= '/^HA_TOKEN=/{print ($2==""?"empty":"set")}'
  /projects/Woow_ha_odoo/.env`.
- A name that is missing or empty is a **stop**: say which one, and do not
  guess a replacement.
- A script without `--env-file` gets the values from the environment of the
  shell that starts it. Load them without echoing:
  `set -a; . /projects/Woow_ha_odoo/.env; set +a`.

## The host

Reached as **`ssh ha`** — the alias, the address and the key live in the agent
container's own SSH configuration, not in this repository (ADR 0003). The host
runs HA OS; the Supervisor CLI is `ha` (`ha apps …`, with `ha addons …` as the
older alias).

Two add-ons are installed:

| Slug | What it is |
| --- | --- |
| `1b7b4ce7_odoo18ce` | the Released add-on from the store; it owns the Public origin, and `.env` targets it |
| `local_odoo18ce` | a local build for verifying a branch; **no `public_url`**, so it cannot be diffed on both surfaces |

`default_db` on the Released add-on is `odoo_parity` (the 29 modules of #144),
so the Public origin serves that database. Create databases inside the
container with `-c /data/odoo.conf`: `/etc/odoo/odoo.conf` has a
non-persistent `data_dir` and loses the filestore on restart.

## The spellings that are pre-approved

`.claude/settings.json` pre-approves the forms below so an unattended process
does not stall. Use them as written — a different spelling of the same command
may still prompt, and a prompt in a Sweep is a dead Iteration.

```json
{
  "permissions": {
    "allow": [
      "Bash(ssh ha:*)",
      "Bash(~/venvs/woow/bin/python odoo18ce/tests/:*)",
      "Bash(~/venvs/woow/bin/python -m pytest:*)"
    ]
  }
}
```

That file is written by a human: an agent may not grant itself permissions, and
the classifier refuses the edit. If it is missing, say so and stop rather than
running the Live tier through a prompt nobody will answer.

```sh
ssh ha '<command on the host>'
~/venvs/woow/bin/python odoo18ce/tests/<script>.py <args>
PATH=/usr/sbin:$PATH ~/venvs/woow/bin/python -m pytest -q odoo18ce/tests
```

Do not wrap `ssh` in `timeout` — the wrapper is not the approved prefix. Give
the Bash tool its own timeout instead, and keep the call in the foreground.

## A parity run

Three steps, in the same shape every recorded run used:

```sh
~/venvs/woow/bin/python odoo18ce/tests/e2e_parity_shared_layers_live.py pcheck \
  --env-file /projects/Woow_ha_odoo/.env --db odoo_parity
~/venvs/woow/bin/python odoo18ce/tests/e2e_parity_shared_layers_live.py fixtures \
  --env-file /projects/Woow_ha_odoo/.env --db odoo_parity --run-id WOOW-PARITY-<UTC timestamp>
~/venvs/woow/bin/python odoo18ce/tests/e2e_parity_shared_layers_live.py run \
  --env-file /projects/Woow_ha_odoo/.env --db odoo_parity \
  --run-id WOOW-PARITY-<UTC timestamp> --only U-C23 --out checks.jsonl
~/venvs/woow/bin/python odoo18ce/tests/e2e_parity_shared_layers_live.py report checks.jsonl
```

Write the interpreter path out in full, as above. A permission rule matches the
**command as written**, so `$P odoo18ce/tests/…` with `P=~/venvs/woow/bin/python`
is a different string from the approved prefix and prompts.

- **`pcheck` first, always.** P-1 to P-5 are what the checks are measured
  against; P-5 (`website.domain` = the Canonical URL) in particular decides
  what the head links and `robots.txt` are supposed to say. A run on a failing
  P-Check records the wrong verdicts.
- **`--run-id` on every writing step.** Fixtures are named after the marker, so
  the host stays readable and the next run can tell whose records are whose.
- **`--only`** keeps a rerun to the items the Issue asks for. The planned set
  knows every item, so `report` reconciles a partial run against it.

`e2e_parity_outbound_live.py`, `e2e_pos_offline_live.py`,
`e2e_menu_action_adapter.py` (`crawl` / `open` / `diff`),
`e2e_settings_ingress.py` and `e2e_collab_peer_snapshot_live.py`
take the same `--env-file`, and the same `--run-id` discipline where they take
a marker at all — the menu/action adapter mints its own run id and prints it,
so the id goes in the evidence README rather than on the command line.

Browsers come from Playwright's shared install (`PLAYWRIGHT_BROWSERS_PATH` is
set in the image). Run headless; `--headed` needs a display nobody has.

**Two sessions on one record** (`e2e_collab_peer_snapshot_live.py`, #234) is the
one run that is not one browser session. `probe` opens both, says whether the
collaboration transport delivered and **writes nothing**; `run` saves on the
receiving session and reads the field back. Run `probe` first: the browser steps
have never been executed against this host, so it is also how a failure is
attributed. `--pair ingress-public` drives one session on each surface, which is
the pair that can carry a foreign Ingress prefix. Its record is a
`woow.peer-snapshot.v1` and does not feed `conservation` (parity plan §12).

## Deploying

Three ways, in order of preference:

1. **A Release the store has.** `ssh ha 'ha apps update 1b7b4ce7_odoo18ce'`,
   then `ssh ha 'ha apps info 1b7b4ce7_odoo18ce --raw-json'` to confirm the
   version. This is the path a user takes, so it is the one that proves a
   Release.

   **A completed Sync is not enough: reload the Supervisor's own copy first.**
   `ha apps update` offers the newest version the Supervisor knows, and it
   learns that from its cached copy of the **App Store mirror**, which it does
   not refetch on demand. On 2026-10-01 (#235) the Sync had finished and the
   mirror carried `0.4.9`, while `info --raw-json` still reported
   `version_latest: 0.4.8` — so the update would have been a no-op against the
   version already installed. `ssh ha 'ha store reload'` fixes it; read
   `version_latest` and only then update.
2. **A branch, without a Release.** `docs/testing/LOCAL_BUILD_ON_HOST.md` — the
   local add-on, its four traps, and the restore step at the end. It has no
   `public_url`, so it verifies Ingress only.
3. **A slow or unstable link.** `docs/runbooks/SLOW_LINK_DEPLOY.md` and
   `docs/runbooks/slow-link-pull.sh` pull the image resumably and hand back the
   `ha apps update` command.

Restarting the add-on is inside the boundary and is sometimes the point — the
maintenance bootstrap writes `web.base.url`, `web.base.url.freeze` and
`website.domain` on every start.

## What a run leaves behind

- **Evidence**, under `docs/testing/evidence/<date>-issue-<n>/`: `README.md`
  (what ran, against what, and the P-Check table), `checks.jsonl`,
  `conservation.json`, `reconciled.jsonl`. Follow
  `2026-09-27-issue-172/` — it is the smallest complete example.
- **The parity plan updated to what the run recorded**, not the other way
  round: the item's row, the `G-`/`AD-` list, and the §10.6 tally.
- **Earlier evidence left alone.** A past run's records are what it recorded;
  when a decision changes their meaning, annotate them, do not rewrite them.
- **A sentence about the host's state** in the pull request, when the run
  leaves fixtures behind or changes a setting.
- **Rows no run asked for, on any run that opens a website page.** Serving a
  tracked page writes a `website.visitor` and a `website.track` row, and the
  page's own markup and JavaScript write too — so "read-only" here means **no
  business writes**, not zero rows. Which writes, where they were read, and why
  no targets file can bound them:
  [ADR 0012, postscript 2026-10-01 (#227)](../adr/0012-sweeps-verify-on-the-test-host.md#postscript-2026-10-01-227).
  Quote the guarantee that way in an evidence README; do not promise zero rows,
  and do not delete the rows to make it true — #235's run exported the ones it
  cleared and said why.

## When it cannot run

- **The host is unreachable.** The container's route to it is one firewall rule
  that does not survive a reboot. Say so in the record, fall back to the Static
  tier, and leave the Issue's Live box unticked with the reason — never try to
  widen the network yourself.
- **The host is busy.** One Live run at a time; a second Sweep driving the same
  database invalidates both. If a run cannot be sure the host is free, say so
  rather than starting.
- **The work needs a card, a phone or a real person** — an ECPay stage payment,
  the Companion app, a mobile device. Still a human's, and still recorded as
  such.
