## What changed

<!-- One or two sentences. Link the issue or plan document if there is one. -->

## Checklist

Tick what applies. CI enforces the version, CHANGELOG and translation rules;
the rest is on you.

- [ ] `config.yaml` changed → version bumped and a matching `## <version> — <date>` section added to `odoo18ce/CHANGELOG.md`
- [ ] Option schema changed → both `translations/en.yaml` and `translations/zh-Hant.yaml` updated
- [ ] `nginx.conf.template` or `10-odoo-config.sh` changed → static tier run locally (`pytest odoo18ce/tests`) with nginx and node installed
- [ ] Network or gate behaviour changed → verified from outside the LAN after Deploy, not only from the office
- [ ] Odoo nightly or base image bumped → noted under `## Unreleased` in the CHANGELOG
- [ ] No secrets, ingress tokens, LAN addresses or database names in the diff
