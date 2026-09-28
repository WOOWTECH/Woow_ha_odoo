# Survey sample pictures under Ingress, before and after the action-help rewrite (#158)

Two menu/action crawls on the test host on 2026-09-28, against the **local**
add-on `local_odoo18ce` built from `agent/issue-158`
(`0.4.4-202609281444`, image `local/amd64-addon-odoo18ce:0.4.4-202609281444`,
so the branch and not a pulled Release), database **`catchup164b`**, with the
`survey` module installed for the run. Driver:

```
e2e_menu_action_adapter.py crawl --surface ha_ingress --apps survey --out <file>
```

The local add-on has **no `public_url`**, so it cannot be diffed on both
surfaces. This is therefore an **Ingress-only** pair of crawls and not a
two-surface parity run: there is no `PARITY`/`GAP` verdict here, and the
parity plan's tally is untouched. The Issue's Live box asks for the crawler's
`PARITY` for the survey action on both surfaces as well; that needs the
Released add-on, so it needs a Release, and it is left for the run that has
one. What these two crawls settle is the half that does not: whether the
escape is gone under Ingress on a real host.

The action is `ir.actions.act_window` **220** here, not the **930** of the
#144 run — the id is per database, and both are `survey.action_survey_form`
reached from `survey.menu_surveys` and `survey.menu_survey_form`.

## Control — `crawl-control.jsonl`

Run `WOOW-PARITY-20260928T140831Z`. Same container, same database, minutes
apart, with the Issue's `location` block cut out of the rendered
`/etc/nginx/nginx.conf` and nginx reloaded, so the only difference from the
run below is this Issue's rules. (The control ran against the first shape of
the fix, before the routes it covers were narrowed to `/web/action/load`
alone. What the control measures — the escape with no rule at all — is the
same either way, and the Surveys screen reaches its action through
`/web/action/load` in every shape.)

| Control identity | `route_escape` | `http_4xx_5xx` | `console_error` |
|---|---|---|---|
| `menu:survey.menu_surveys\|ir.actions.act_window:220` | **8** | **8** | **8** |
| `menu:survey.menu_survey_form\|ir.actions.act_window:220` | **8** | **8** | **8** |
| the four other survey actions (221–224) | 0 | 0 | 0 |

The escaping literals are the four sample-survey pictures, root-relative and
unprefixed, exactly as the #144 run recorded them for action 930:

```
/survey/static/src/img/survey_sample_survey.png
/survey/static/src/img/survey_sample_assessment.png
/survey/static/src/img/survey_sample_custom.png
/survey/static/src/img/survey_sample_live_session.png
```

## With the rules — `crawl-fixed.jsonl`

Run `WOOW-PARITY-20260928T144539Z`. Every one of the six survey actions is
`CLEAN`: `route_escape`, `http_4xx_5xx`, `console_error`, `failed_requests`
and `pageerror` are all **0**, and `url_violations` is empty. On action 220
the same four pictures are now recorded as
`<INGRESS_PREFIX>/survey/static/src/img/survey_sample_*.png`, and each of them
is **HTTP 200** in the add-on's access log — four requests rather than eight,
because the second survey menu takes them from the browser cache.

## What the run left on the host

- `local_odoo18ce` is running the branch build, not the 6edf781 build it held
  before; `/addons/odoo18ce` holds this branch's source with `image:` removed
  and `version: 0.4.4-202609281444`, per `LOCAL_BUILD_ON_HOST.md`.
- `catchup164b` has the `survey` module **installed** (it did not before) and
  its `admin` password **reset** to a value generated on the host, because the
  `.env` password does not open that database. It is a scratch database left
  by the #164 catch-up run; nothing in the repository depends on either.
- A database `issue158` was created and then dropped again, on the way to
  finding that `db_name = catchup164b` in `/data/odoo.conf` makes that database
  the only one reachable over HTTP, whatever `?db=` the login page is given.
- The first crawl attempt recorded one HTTP 500 per screen on
  `/web/assets/…/web.assets_web.min.css`. That was collateral from installing
  `survey` with the `odoo` CLI **as root**, which left 48 root-owned entries in
  `/data/odoo/filestore/catchup164b`; the server, running as `odoo`, then could
  not write the regenerated bundle (`PermissionError` on the filestore's
  `checklist` directory). `chown -R odoo:odoo` on that filestore fixed it, and
  both crawls above are from after the fix. The 500 reproduces on Odoo's own
  port 8070, with nginx out of the path, so it was never about this Issue's
  rules — it is recorded here because it is a trap for the next run that
  installs a module this way.
- The Released add-on `1b7b4ce7_odoo18ce` was not touched.
