# WebAuthn / Passkey Authentication for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
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
- **Multilingual authentication page** — the passkey prompt page automatically matches the Home Assistant UI language (English, French, German, Spanish, Dutch).

## Requirements

- Home Assistant **2024.1** or later
- [HACS](https://hacs.xyz/) (recommended for installation)
- HTTPS access to Home Assistant (`localhost` also works for development)
- A WebAuthn-capable authenticator (hardware key, biometric sensor, or a supported password manager)

---

## Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant UI.
2. Go to **Integrations** → click the three-dot menu (⋮) → **Custom repositories**.
3. Paste `https://github.com/Anrolosia/ha-webauthn-mfa`, choose category **Integration**, then click **Add**.
4. Close the dialog. **WebAuthn / Passkey Authentication** will now appear in the integration list.
5. Click **Download** and follow the prompts.
6. Restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/Anrolosia/ha-webauthn-mfa/releases/latest).
2. Copy the `custom_components/webauthn_mfa` folder into your HA `config/custom_components/` directory (create it if it does not exist).
3. Restart Home Assistant.

---

## Configuration

Add the following to your `configuration.yaml`:

```yaml
webauthn_mfa:
  rp_id: "homeassistant.local"
  rp_name: "Home Assistant"
  expected_origin: "https://homeassistant.local"
```

| Field | Description |
|-------|-------------|
| `rp_id` | Your HA domain name — no scheme, no port (e.g. `homeassistant.local` or `ha.example.com`) |
| `rp_name` | Label shown in passkey prompts (e.g. `Home Assistant`) |
| `expected_origin` | Full URL used to access HA, including scheme and port if non-standard |

Restart Home Assistant after saving.

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

- Docker and Docker Compose

### Quick start

```bash
git clone https://github.com/Anrolosia/ha-webauthn-mfa.git
cd ha-webauthn-mfa
cp .env.example .env
docker compose up
```

Home Assistant will be available at `http://localhost:8123`. The `custom_components/webauthn_mfa` directory is mounted directly into the container — changes are picked up after a HA restart from **Developer Tools → YAML → Restart**.

### Running tests

```bash
make install
make test
```

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| "Passkey / Security Key" option does not appear | The integration is not loaded — check `configuration.yaml` and the HA logs for errors on startup. |
| Browser shows "Security key not supported" | Your browser or device does not support WebAuthn. Use Chrome, Firefox, Safari ≥ 16, or Edge. |
| Passkey prompt appears but fails with "Not allowed" | The `expected_origin` in your config does not match the URL you are accessing HA from. |
| Wrong user is signed in after passkey authentication | Re-register the passkey — a previous partial registration may have created an orphaned credential. |
| Passkey works on one device but not another | Passkeys are tied to the authenticator. Use a sync-capable password manager (Bitwarden, 1Password) to share them across devices. |

### Enabling debug logs

```yaml
logger:
  logs:
    custom_components.webauthn_mfa: debug
```

---

## Contributing

Pull requests and issues are welcome! Please open an issue before submitting a large change.

## License

This project is licensed under the [MIT License](LICENSE).
