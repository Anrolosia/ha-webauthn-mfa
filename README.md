# WebAuthn / Passkey Authentication for Home Assistant

> Passkey authentication for Home Assistant — sign in with a fingerprint, face scan, or security key. No password required.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/release/anrolosia/ha-webauthn-mfa.svg)](https://github.com/anrolosia/ha-webauthn-mfa/releases)
[![License](https://img.shields.io/github/license/anrolosia/ha-webauthn-mfa.svg)](LICENSE)

Sign in to Home Assistant with a **passkey** — no password required.

Supports **Bitwarden**, **1Password**, **YubiKey**, **Face ID**, **Touch ID**, **Windows Hello**, and any FIDO2-compatible authenticator.

---

## Features

- 🔑 **Passwordless login** via passkey (WebAuthn / FIDO2)
- 🔒 **Phishing-resistant** — credentials are bound to your domain
- 👥 **Multi-user** — each user registers their own passkeys
- 📱 **Cross-platform** — works in any modern browser
- 🗂️ **Passkey manager panel** — register, list, and delete passkeys from the HA sidebar

---

## Requirements

- Home Assistant **2024.1** or later
- A modern browser with WebAuthn support
- HTTPS (required for WebAuthn in production; `localhost` also works)

---

## Installation

### HACS (recommended)

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/anrolosia/ha-webauthn-mfa` with category **Integration**
3. Install **WebAuthn / Passkey Authentication**
4. Restart Home Assistant

### Manual

Copy the `custom_components/webauthn_mfa/` directory into your HA `config/custom_components/` directory and restart.

---

## Configuration

Add the following to your `configuration.yaml`:

```yaml
webauthn_mfa:
  rp_id: "homeassistant.local"          # Your HA domain (no scheme, no port)
  rp_name: "Home Assistant"             # Label shown in passkey prompts
  expected_origin: "https://homeassistant.local"  # Full URL used to access HA
```

Restart Home Assistant after saving.

---

## Usage

### Registering a passkey

1. Log in to Home Assistant with your username and password
2. Open the **Passkeys** panel in the sidebar (key icon 🔑)
3. Enter a name for your passkey (e.g. *Bitwarden*, *iPhone*)
4. Click **+ Add passkey** and follow your browser's prompt

### Logging in with a passkey

1. Navigate to your Home Assistant login page
2. Click **Passkey / Security Key** (below the login form)
3. Follow your browser's / authenticator's prompt

---

## Enabling debug logs

```yaml
logger:
  logs:
    custom_components.webauthn_mfa: debug
```

---

## License

[MIT](LICENSE)
