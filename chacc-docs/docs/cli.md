# CLI

The `chacc` command manages module development, packaging, installation, and
server startup. Every command has its own `--help`:

```bash
chacc --help
chacc <command> --help
```

## Create a module

```bash
chacc create my_module
```

Creates a module scaffold in `plugins/my_module/`.

Options:

| Option | Description |
| --- | --- |
| `--output-dir` | Output directory. Defaults to `plugins`. |
| `--force` | Overwrite an existing module directory. |

## Build a module

```bash
chacc build plugins/my_module
```

Builds `my_module.chacc` from the source directory. The archive is written to
the **current working directory**, not next to the source — `cd` into the
target directory first if you want it to land somewhere specific.

Options:

| Option | Description |
| --- | --- |
| `--output-filename` | Custom output archive name. |

The source directory must contain `module_meta.json`.

## Install a module

Install a module from a Git URL or a local directory. The CLI does the
clone, validates the module, and lands it in the right place.

```bash
chacc install <source>
```

The simplest form: install an official module straight from GitHub.

```bash
chacc install TNet-Tech/chacc_authentication
```

### Source forms

| Form | Example | Resolves to |
| --- | --- | --- |
| Local path | `./my_module`, `/abs/path/to/my_module` | the directory itself |
| HTTPS URL | `https://github.com/TNet-Tech/chacc_outbound.git` | the URL |
| SSH URL | `git@github.com:TNet-Tech/chacc_outbound.git` | the URL (uses your SSH key) |
| Short form | `TNet-Tech/chacc_outbound` | `https://github.com/TNet-Tech/chacc_outbound.git` |

### Choose a mode

| Goal | Flag | Lands in |
| --- | --- | --- |
| Develop locally with hot-reload | `--dev` | `plugins/<name>/` (keeps `.git`) |
| Ship to a running server | _(default)_ | `.modules_installed/<name>.chacc` |

In dev mode the source is copied; your local working copy is never modified
and the module's `.git/` is preserved so you can keep developing and pushing
from inside the plugin. In production the CLI builds a `.chacc` archive from
a staging copy (`.git/` stripped) and atomically places it in
`.modules_installed/`.

Restart the ChaCC server after install to activate the module.

### Pick a ref

```bash
chacc install TNet-Tech/chacc_outbound@v1.2.0
chacc install TNet-Tech/chacc_outbound --ref main
```

Both forms pick a specific branch, tag, or commit. SSH and HTTPS-with-creds
URLs are left as-is — only bare URLs and short forms split on `@`.

### Common options

| Option | Description |
| --- | --- |
| `--ref <ref>` | Git ref to install. Alternative to `source@ref` syntax. |
| `--dev` | Install into the plugins directory. Default is production. |
| `--force` | Overwrite an existing module with the same name. |
| `--depth N` | Git clone depth. Default `1`. Use `0` or `--full` for full history. |
| `--full` | Equivalent to `--depth 0` (full clone). |
| `--token-env NAME` | Override the env var name used for token lookup (e.g. `MY_CI_TOKEN`). |
| `--quiet` | Suppress per-step progress output. The final result is always shown. |

### Credentials

| Source | What happens |
| --- | --- |
| SSH (`git@github.com:...` or `ssh://...`) | Pass through. Uses your SSH key. |
| HTTPS with embedded creds (`https://user:token@host/...`) | Pass through. Token used for this clone only. |
| Plain HTTPS without creds | Token is read from `--token-env`, then `GITHUB_TOKEN` (github.com), `GITLAB_TOKEN` (gitlab.com), `BITBUCKET_TOKEN` (bitbucket.org), or `CHACC_GIT_TOKEN` (other hosts). |

Tokens are rewritten into the URL in-memory only and never persisted. In
non-interactive environments (CI, scripts) the CLI fails with a clear
message instead of prompting, so a missing token is always caught up front.

### Examples

```bash
# Install an official module (production)
chacc install TNet-Tech/chacc_outbound

# Install in dev mode (copies into plugins/, keeps .git)
chacc install TNet-Tech/chacc_outbound --dev

# Install a specific tag
chacc install TNet-Tech/chacc_outbound@v1.0.0

# Install a private repo via GITHUB_TOKEN
GITHUB_TOKEN=ghp_xxx chacc install TNet-Tech/private_module --dev

# Install from a local directory
chacc install ./plugins/my_module --dev --force

# Install from a full URL
chacc install https://github.com/TNet-Tech/chacc_outbound.git

# Quiet mode (CI-friendly)
chacc install TNet-Tech/chacc_outbound --quiet
```

After a successful install the CLI prints each step (`->` then `[OK]`) and
ends with `Module '<name>' installed. Restart the ChaCC server to activate it.`
If the module ships a `requirements.txt`, a warning is shown at the end:
dependencies install on server startup, and any model changes trigger
automatic migrations on restart.

### Official modules

Every official module lives at `https://github.com/TNet-Tech/<repo>`. Pick the
one you want and copy the install line.

| Module | Install (dev) | Install (prod) |
| --- | --- | --- |
| Chacc Authentication | `chacc install TNet-Tech/chacc_authentication --dev` | `chacc install TNet-Tech/chacc_authentication` |
| Chacc File Manager | `chacc install TNet-Tech/chacc_file_manager --dev` | `chacc install TNet-Tech/chacc_file_manager` |
| Chacc Outbound | `chacc install TNet-Tech/chacc_outbound --dev` | `chacc install TNet-Tech/chacc_outbound` |

Each module has its own documentation page with the full configuration,
REST API, and usage examples — see the "Available Modules" section of the
docs.

## Deploy a module

```bash
chacc deploy my_module.chacc
```

Uploads the module to a running ChaCC API instance over HTTP. This is the
remote-server equivalent of `chacc install` — use it when the target server
is reachable over the network. For local filesystem installs use
`chacc install` instead.

Required environment variable:

```bash
CHACC_DEPLOY_URL=http://localhost:8085
```

Optional environment variables (still under development):

```bash
CHACC_DEPLOY_API_KEY=optional-token
CHACC_DEPLOY_TIMEOUT=30
```

## Run the server

Development server:

```bash
chacc run server --dev
```

Production server:

```bash
chacc run server
```

Options:

| Option | Description |
| --- | --- |
| `--dev` | Run in development mode with auto-reload. |
| `--host` | Host to bind. Defaults to `0.0.0.0`. |
| `--port` | Port to bind. Defaults to `8085`. |
| `-v` / `--verbose` | Enable verbose logging (`CHACC_VERBOSE=true`). The flag is passed to the server subprocess, so startup logs and application logs use `INFO` level. |
| `--debug` | Enable debug logging (`CHACC_DEBUG=true` in development mode). |

## Legacy server command

```bash
chacc server --host 0.0.0.0 --port 8085
```

This command is retained for compatibility. Prefer `chacc run server`.

## Typical workflow

```bash
# Scaffold and develop
chacc create billing
cd plugins/billing
# edit module_meta.json, models.py, routes.py, and tests
chacc run server --dev

# Install locally (dev)
chacc install TNet-Tech/billing --dev
# ...or install from a local checkout
chacc install ./plugins/billing --dev --force

# Package for remote deploy
chacc build plugins/billing
chacc deploy billing.chacc
```

## Module name rules

Module names:

- Cannot be empty.
- Cannot start with a number.
- May contain letters, numbers, underscores, hyphens, and spaces.
- Are normalized to lowercase with underscores.
