# WoowTech Home Assistant Add-ons

[![Add Repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWOOWTECH%2FWoow_odoo_docker_compose_all)

## Add-ons

### [Odoo 18 CE](./odoo18ce)

[![Show Add-on](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=0af40a62_odoo18ce&repository_url=https%3A%2F%2Fgithub.com%2FWOOWTECH%2FWoow_odoo_docker_compose_all)

Odoo 18 Community Edition + PostgreSQL 16 — bundled all-in-one add-on for SME.

**Features:**

- Odoo 18 CE + PostgreSQL 16 in a single container
- Multi-arch: amd64 + aarch64 (Raspberry Pi 5)
- Auto-create database on first startup
- WOOWTECH custom Odoo modules pre-installed
- CJK fonts + wkhtmltopdf for PDF reports
- Traditional Chinese / English translations
- Cold backup with automatic exclusions

## Installation

### One-Click Install

1. Click the badge below to add this repository to your Home Assistant:

   [![Add Repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWOOWTECH%2FWoow_odoo_docker_compose_all)

2. Navigate to **Settings** -> **Add-ons** -> **Add-on Store**
3. Find **"Odoo 18 CE"** and click **INSTALL**
4. Configure the add-on options
5. Start the add-on

### Manual Installation

1. Add this repository to your Home Assistant:
   - Go to **Settings** -> **Add-ons** -> **Add-on Store**
   - Click the **&#8942;** menu -> **Repositories**
   - Add: `https://github.com/WOOWTECH/Woow_odoo_docker_compose_all`
   - Click **Add** -> **Close**
2. Navigate to **Settings** -> **Add-ons** -> **Add-on Store**
3. Find **"Odoo 18 CE"** and click **INSTALL**
4. Configure the add-on options
5. Start the add-on

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `TZ` | Timezone | `Asia/Taipei` |
| `db_password` | PostgreSQL password | _(required)_ |
| `admin_passwd` | Odoo master password | _(required)_ |
| `default_db` | Auto-create database name | _(empty)_ |
| `workers` | Number of workers (0 = single-process) | `0` |
| `max_cron_threads` | Cron worker threads | `1` |
| `log_level` | Log level | `info` |
| `proxy_mode` | Enable reverse proxy mode | `true` |

See the add-on's **Documentation** tab for the full configuration reference.

## Other Deployment Methods

This repository also provides deployment configurations for other platforms:

| Branch | Platform | Description |
|--------|----------|-------------|
| [`main`](https://github.com/WOOWTECH/Woow_odoo_docker_compose_all/tree/main) | Docker Compose | Standard deployment with PostgreSQL 16 |
| [`podman`](https://github.com/WOOWTECH/Woow_odoo_docker_compose_all/tree/podman) | Podman | Rootless container deployment |
| [`k3s`](https://github.com/WOOWTECH/Woow_odoo_docker_compose_all/tree/k3s) | Kubernetes | K3s manifests with Kustomize |
| **`ha`** | **Home Assistant** | **HA add-on (this branch)** |

## License

LGPL-3.0
