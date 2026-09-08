# List of available modules

Official modules maintained by the ChaCC API team. These modules are still under active development.

## Available Modules

| Module | Description | Install (dev) |
|---|---|---|
| [Chacc Authentication](authentication.md) | User authentication, JWT, and RBAC | `chacc install TNet-Tech/chacc_authentication --dev` |
| [Chacc File Manager](file-manager.md) | Secure, UUID-addressed file management with adapter-based storage | `chacc install TNet-Tech/chacc_file_manager --dev` |
| [Chacc Outbound](outbound.md) | Outbound messaging (email, SMS, custom channels) with retries, status tracking, and an admin API | `chacc install TNet-Tech/chacc_outbound --dev` |

For production installs, drop the `--dev` flag. See the [CLI install guide](../cli.md#install-a-module) for source forms, credentials, and ref handling.
