# Woow_ha_odoo — WoowTech Odoo Home Assistant Add-on Repository

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWOOWTECH%2FWoow_ha_odoo)

Home Assistant add-on repository for [Odoo 18](https://www.odoo.com) Community
Edition — a single-container SME deployment with PostgreSQL 16 bundled inside.

Odoo 18 Community Edition 的 Home Assistant add-on 倉庫,
單一容器 SME 部署,PostgreSQL 16 已內建。

## Add-ons in this repository | 本倉庫的 add-on

| Add-on | Description |
|---|---|
| [Odoo 18 CE](odoo18ce/) | Odoo 18 CE + PostgreSQL 16 all-in-one (amd64/aarch64) |

## Installation | 安裝

1. Click the badge above (or **Settings → Add-ons → Add-on Store → ⋮ →
   Repositories**) and add:
   `https://github.com/WOOWTECH/Woow_ha_odoo`
2. Find **Odoo 18 CE** in the store and click **INSTALL**.
3. Details, options and troubleshooting: [odoo18ce/README.md](odoo18ce/README.md)
   and [odoo18ce/DOCS.md](odoo18ce/DOCS.md)

> **Migrated from `Woow_odoo_docker_compose_all` (branch `ha`)** — if you added
> the old repository URL, remove it and add this one to keep receiving updates.
> 若你先前加入的是舊倉庫網址,請移除並改加本倉庫,才能繼續收到更新。

## Other deployment platforms | 其他部署平台

- Docker/Podman Compose → [Woow_podman_odoo](https://github.com/WOOWTECH/Woow_podman_odoo)
- K3s/Kubernetes Helm chart → [Woow_k3s_odoo](https://github.com/WOOWTECH/Woow_k3s_odoo)
