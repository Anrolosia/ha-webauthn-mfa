# Contributing

Thanks for taking the time to contribute!

## Getting started

```bash
git clone https://github.com/Anrolosia/ha-webauthn-mfa.git
cd ha-webauthn-mfa
cp .env.example .env
make dev-init
docker compose up
```

Home Assistant is served at `https://ha.test` through Caddy. Add `ha.test` to your hosts file pointing at `127.0.0.1`, because WebAuthn refuses to run over plain HTTP on a non-local host.

The `custom_components/webauthn_mfa` directory is mounted into the container. Python changes need a Home Assistant restart, and so do translation changes, because the loader caches files at module level.

## Before opening a pull request

```bash
make format   # ruff format + ruff check --fix
make lint     # must pass, CI runs the same checks
make test     # pytest
```

## Commit messages

One line, conventional commit, written in the past tense:

```
type: Description
```

Lowercase type, no scope in parentheses, description starting with a capital letter. Valid types are `feat`, `fix`, `chore`, `refactor`, `docs`, `ci`, `build`, `style`, `test`.

```
feat: Added Polish translation
fix: Removed the duplicate language assignment
```

Release notes are generated from these subjects, so a commit that does not match the format disappears from the changelog. If your pull request is squash merged, the squash subject is what counts.

## Translations

There are two translation directories, and they are not interchangeable.

| Directory | What it covers | Rendered by |
|-----------|----------------|-------------|
| `custom_components/webauthn_mfa/translations/` | The setup and options dialogs | The Home Assistant translation system |
| `custom_components/webauthn_mfa/www/translations/` | The login overlay, the passkey prompt page, and the sidebar panel | The integration itself |

They are split for two reasons. Home Assistant validates `translations/en.json` against a strict schema in CI and rejects any unknown top level key, so custom frontend strings cannot be stored there. And two of the three frontend surfaces run before the user is authenticated, with no session and no websocket available, so their strings have to be resolved server side and inlined into the page.
One extra rule applies to `translations/` only, because Home Assistant validates those files in CI: values must not contain a URL. Writing `https://ha.example.com` in a description fails the build with "the string should not contain URLs". Describe the value in prose instead. This rule does not apply to `www/translations/`, which the integration reads itself.

### Adding a language

Use the bare two letter code as the filename. Regional variants are not supported: `pt-BR` is resolved as `pt`.

1. Copy `custom_components/webauthn_mfa/translations/en.json` to `translations/<xx>.json` and translate the values.
2. Copy `custom_components/webauthn_mfa/www/translations/en.json` to `www/translations/<xx>.json` and translate the values.
3. Add the language to the multilingual line in the Features section of `README.md`.
4. Restart Home Assistant and check both the setup dialog and the sidebar panel.

Rules that apply to both files:

- Never rename or remove a key, only the values are translated.
- Keep the `webauthn_mfa` top level key in `www/translations/<xx>.json`.
- Leave placeholders such as `{name}` exactly as they are, including the braces.
- A partial translation is fine. Missing keys fall back to English one by one, so a half finished file is still worth submitting.

Only `strings.json` and `translations/en.json` are schema checked in CI. A structurally broken `fr.json` or `pl.json` will not be caught automatically, so please compare your file against `en.json` before submitting.

## Testing a change to the login flow

The passkey login is a handshake between the injected script, the ceremony page, and the native Home Assistant form. The detour through the native form submit is what lets the Service Worker persist session tokens, which is what makes "Stay signed in" work. Any change to that path must preserve it.

Test the full path end to end after touching any of it: register a passkey from the sidebar panel, sign out, sign back in with the passkey, and confirm that the session survives a browser restart.