# WebAuthn / Passkey Authentication for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/release/Anrolosia/ha-webauthn-mfa.svg)](https://github.com/Anrolosia/ha-webauthn-mfa/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Passkey authentication for Home Assistant — sign in with a fingerprint, face scan, or security key. No password required.

## Motivation

Passwords are the weakest link in home automation security. WebAuthn / FIDO2 passkeys solve this — they are phishing-resistant, bound cryptographically to your domain, and supported natively by every modern browser, password manager, and device.

This integration injects a WebAuthn auth provider into Home Assistant at startup. Users register their passkeys once via a dedicated sidebar panel, and can then sign in with a single tap — no password, no TOTP code, no SMS.

## Features

- **Passwordless login** — replace passwords entirely with FIDO2 passkeys.
- **Phishing-resistant** — credentials are cryptographically bound to your domain; they cannot be stolen by a fake login page.
- **Multi-user** — each Home Assistant user registers and manages their own passkeys independently.
- **Broad authenticator support** — works with Bitwarden, 1Password, YubiKey, Face ID, Touch ID, Windows Hello, and any FIDO2-compatible authenticator.
- **Dedicated sidebar panel** — register, rename, and delete passkeys without leaving Home Assistant.
- **Persistent sessions** — the "Stay signed in" option works correctly alongside the native HA Service Worker token flow.
- **Cross-platform** — any modern browser (Chrome, Firefox, Safari, Edge) on desktop or mobile.
- **Fully multilingual frontend** — the login overlay, the passkey prompt page, and the sidebar panel all follow the Home Assistant UI language (English, French, German, Spanish, Dutch).

## Requirements

- Home Assistant **2026.4** or later
- [HACS](https://hacs.xyz/) (recommended for installation)
- HTTPS access to Home Assistant (`localhost` also works for development)
- A WebAuthn-capable authenticator (hardware key, biometric sensor, or a supported password manager)

---

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Anrolosia&repository=ha-webauthn-mfa&category=integration)

1. Open HACS in your Home Assistant UI.
2. Search for **WebAuthn / Passkey Authentication**.
3. Click **Download** and follow the prompts.
4. Restart Home Assistant.
5. Go to **Settings** → **Devices & services** → **Add integration** and pick **WebAuthn / Passkey Authentication**.

### Manual

1. Download the [latest release](https://github.com/Anrolosia/ha-webauthn-mfa/releases/latest).
2. Copy the `custom_components/webauthn_mfa` folder into your HA `config/custom_components/` directory (create it if it does not exist).
3. Restart Home Assistant.

---

## Configuration

The integration is configured from the UI. Go to **Settings** → **Devices & services** → **Add integration** → **WebAuthn / Passkey Authentication**.

| Field | Description |
|-------|-------------|
| `rp_id` | Your HA domain name, without scheme or port. `homeassistant.local` or `ha.example.com` |
| `rp_name` | Label shown in passkey prompts, such as `Home Assistant` |
| `expected_origin` | Full URL used to reach HA, including scheme and port if it is not the default |

The host in `expected_origin` must be `rp_id` itself or a subdomain of it. The setup form rejects any other combination, because WebAuthn would otherwise fail silently in the browser.

Settings can be changed later from the **Configure** button on the integration card. **A restart is required** for changes to take effect, and changing `rp_id` invalidates every passkey already registered.

<details>
<summary>Migrating from YAML</summary>

Earlier versions were configured through `configuration.yaml`:

```yaml
webauthn_mfa:
  rp_id: "homeassistant.local"
  rp_name: "Home Assistant"
  expected_origin: "https://homeassistant.local"
```

This block is still read once at startup and imported into a config entry automatically. A deprecation warning is logged, and the block can be removed from `configuration.yaml` afterwards. No passkeys are lost as long as `rp_id` stays the same.

</details>

---

## Usage

### Registering a passkey

![Register a passkey](docs/webauthn_mfa_register_1280.gif)

1. Log in to Home Assistant with your existing username and password.
2. Open the **Passkeys** panel in the sidebar (🔑 key icon).
3. Enter a name for your passkey (e.g. *Bitwarden*, *My iPhone*, *YubiKey 5*).
4. Click **+ Add passkey** and follow your browser or authenticator prompt.

The passkey is immediately available for login on all devices that share the same authenticator (e.g. a password manager synced across devices).

![Register a passkey](docs/passkey_definition.gif)

### Signing in with a passkey

1. Navigate to your Home Assistant login page.
2. Click **Passkey / Security Key** below the login form.
3. Follow your browser's or authenticator's prompt.
4. You are signed in — no password typed.

![Sign in with a passkey](docs/passkey_usage.gif)

### Managing passkeys

From the **Passkeys** sidebar panel you can:

- See all passkeys registered for your account
- Delete any passkey individually

---

## Development

### Prerequisites

#### 1. Update your local hosts file
You must map the dummy domain `ha.test` to your local machine loopback.

Add the following line to your operating system's `hosts` file (located at `/etc/hosts` on macOS/Linux or `C:\Windows\System32\drivers\etc\hosts` on Windows):

```text
127.0.0.1 ha.test
```

### 2. Docker and Docker Compose

```bash
git clone https://github.com/Anrolosia/ha-webauthn-mfa.git
cd ha-webauthn-mfa
cp .env.example .env
make dev-init
docker compose up
```

Home Assistant will be available at `https://ha.test`. Since Caddy uses an internal certificate authority, your browser will display an unverified certificate warning, you can bypass the SSL Warning.

### Running tests

The test suite pins `pytest-homeassistant-custom-component`, which tracks Home Assistant and therefore needs **Python 3.14 or newer**. On an older interpreter, `pip` filters the newer releases out of the index and fails with a misleading `no matching distribution found` error listing hundreds of older versions.

The simplest option needs no local Python at all, since it builds in Docker:

```bash
make test
```

To install the dependencies locally instead, create a virtual environment first:

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
make test
```

If `python3` is not your 3.14 interpreter, point `make` at the right one:

```bash
make install PYTHON=/path/to/python3.14
```

`make install` checks the interpreter version before touching `pip` and tells you which one it found, so a wrong version fails immediately with a readable message rather than a wall of package versions.

<details>
<summary>Windows (Git Bash)</summary>

The `py` launcher is not on the `PATH` inside Git Bash, so use the full path the installer created. After `winget install Python.Python.3.14`:

```bash
"/c/Users/$USERNAME/AppData/Local/Programs/Python/Python314/python.exe" -m venv .venv
source .venv/Scripts/activate
make install
```

Note that the activate script lives under `Scripts/` rather than `bin/`. Without activating the virtual environment, `make` falls back to whichever `python3` is on the `PATH`, which is usually the Microsoft Store build.

</details>

`make lint` and `make format` only need `ruff` and run on any Python version.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| "Passkey / Security Key" option does not appear | The integration is not set up, or it failed to load. Check **Settings** → **Devices & services** and the HA logs for errors on startup. |
| Browser shows "Security key not supported" | Your browser or device does not support WebAuthn. Use Chrome, Firefox, Safari ≥ 16, or Edge. |
| Passkey prompt appears but fails with "Not allowed" | The `expected_origin` in your settings does not match the URL you are accessing HA from. |
| Wrong user is signed in after passkey authentication | Re-register the passkey — a previous partial registration may have created an orphaned credential. |
| Passkey works on one device but not another | Passkeys are tied to the authenticator. Use a sync-capable password manager (Bitwarden, 1Password) to share them across devices. |
| Registration fails with "The object is in an invalid state" | This authenticator already holds a passkey for your account, usually one synced from another device through iCloud Keychain or a password manager. Delete the existing passkey from the Passkeys panel first, or register from a different authenticator. |
| Registration is immediately cancelled inside the Home Assistant Companion App | The Companion App webview does not expose WebAuthn. Register and sign in from a regular browser instead. |
| `make install` fails with `no matching distribution found` for `pytest-homeassistant-custom-component` | Your local Python is older than 3.14. See [Running tests](#running-tests). |

### Enabling debug logs

```yaml
logger:
  logs:
    custom_components.webauthn_mfa: debug
```

---

## Contributing

Pull requests and issues are welcome! Please open an issue before submitting a large change.

Adding a language is a great first contribution and does not require any Python. See [CONTRIBUTING.md](CONTRIBUTING.md) for the two translation directories and what belongs in each.

## License

This project is licensed under the [MIT License](LICENSE).