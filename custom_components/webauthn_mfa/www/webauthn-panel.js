/**
 * WebAuthn MFA — Sidebar panel for passkey management.
 */

// ── i18n ──────────────────────────────────────────────────────────────────────
const STRINGS = {
  en: {
    title:          "My Passkeys",
    subtitle:       "Sign in to Home Assistant without a password.",
    registered:     "Registered passkeys",
    empty:          "No passkeys registered yet.",
    loading:        "Loading...",
    add:            "Add a passkey",
    addBtn:         "+ Add passkey",
    placeholder:    "Name (e.g. My iPhone, Bitwarden)",
    delete:         "Delete",
    confirmDelete:  "Delete this passkey?",
    deleted:        "✓ Passkey deleted.",
    deleteError:    "❌ Failed to delete passkey.",
    registering:    "Registering...",
    waiting:        "⏳ Waiting for your passkey...",
    registered_ok:  (name) => `✓ Passkey "${name}" registered!`,
    cancelled:      "❌ Cancelled.",
    noSupport:      "❌ Your browser does not support passkeys.",
    serverError:    "Server error",
    regError:       "Registration error",
  },
  fr: {
    title:          "Mes Passkeys",
    subtitle:       "Connectez-vous à Home Assistant sans mot de passe.",
    registered:     "Passkeys enregistrées",
    empty:          "Aucune passkey enregistrée.",
    loading:        "Chargement...",
    add:            "Ajouter une passkey",
    addBtn:         "+ Ajouter une passkey",
    placeholder:    "Nom (ex : Mon iPhone, Bitwarden)",
    delete:         "Supprimer",
    confirmDelete:  "Supprimer cette passkey ?",
    deleted:        "✓ Passkey supprimée.",
    deleteError:    "❌ Erreur lors de la suppression.",
    registering:    "Enregistrement...",
    waiting:        "⏳ En attente de votre passkey...",
    registered_ok:  (name) => `✓ Passkey « ${name} » enregistrée !`,
    cancelled:      "❌ Annulé.",
    noSupport:      "❌ Votre navigateur ne supporte pas les passkeys.",
    serverError:    "Erreur serveur",
    regError:       "Erreur d'enregistrement",
  },
  de: {
    title:          "Meine Passkeys",
    subtitle:       "Melden Sie sich ohne Passwort bei Home Assistant an.",
    registered:     "Registrierte Passkeys",
    empty:          "Noch keine Passkeys registriert.",
    loading:        "Laden...",
    add:            "Passkey hinzufügen",
    addBtn:         "+ Passkey hinzufügen",
    placeholder:    "Name (z. B. Mein iPhone, Bitwarden)",
    delete:         "Löschen",
    confirmDelete:  "Diesen Passkey löschen?",
    deleted:        "✓ Passkey gelöscht.",
    deleteError:    "❌ Löschen fehlgeschlagen.",
    registering:    "Registrierung...",
    waiting:        "⏳ Warten auf Ihren Passkey...",
    registered_ok:  (name) => `✓ Passkey „${name}" registriert!`,
    cancelled:      "❌ Abgebrochen.",
    noSupport:      "❌ Ihr Browser unterstützt keine Passkeys.",
    serverError:    "Serverfehler",
    regError:       "Registrierungsfehler",
  },
  es: {
    title:          "Mis Passkeys",
    subtitle:       "Inicia sesión en Home Assistant sin contraseña.",
    registered:     "Passkeys registradas",
    empty:          "No hay passkeys registradas.",
    loading:        "Cargando...",
    add:            "Agregar passkey",
    addBtn:         "+ Agregar passkey",
    placeholder:    "Nombre (ej: Mi iPhone, Bitwarden)",
    delete:         "Eliminar",
    confirmDelete:  "¿Eliminar esta passkey?",
    deleted:        "✓ Passkey eliminada.",
    deleteError:    "❌ Error al eliminar la passkey.",
    registering:    "Registrando...",
    waiting:        "⏳ Esperando tu passkey...",
    registered_ok:  (name) => `✓ Passkey "${name}" registrada!`,
    cancelled:      "❌ Cancelado.",
    noSupport:      "❌ Tu navegador no admite passkeys.",
    serverError:    "Error del servidor",
    regError:       "Error de registro",
  },
  nl: {
    title:          "Mijn Passkeys",
    subtitle:       "Log in bij Home Assistant zonder wachtwoord.",
    registered:     "Geregistreerde passkeys",
    empty:          "Nog geen passkeys geregistreerd.",
    loading:        "Laden...",
    add:            "Passkey toevoegen",
    addBtn:         "+ Passkey toevoegen",
    placeholder:    "Naam (bijv. Mijn iPhone, Bitwarden)",
    delete:         "Verwijderen",
    confirmDelete:  "Deze passkey verwijderen?",
    deleted:        "✓ Passkey verwijderd.",
    deleteError:    "❌ Verwijderen mislukt.",
    registering:    "Registreren...",
    waiting:        "⏳ Wachten op uw passkey...",
    registered_ok:  (name) => `✓ Passkey "${name}" geregistreerd!`,
    cancelled:      "❌ Geannuleerd.",
    noSupport:      "❌ Uw browser ondersteunt geen passkeys.",
    serverError:    "Serverfout",
    regError:       "Registratiefout",
  },
};

function getLang(hass) {
  const raw = hass?.language || hass?.locale?.language || navigator.language || "en";
  const code = raw.split("-")[0].toLowerCase();
  return STRINGS[code] ? code : "en";
}

// ── Web component ─────────────────────────────────────────────────────────────

class WebAuthnPanel extends HTMLElement {
  constructor() {
    super();
    this._credentials = [];
    this._mounted = false;
    this._isAttached = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._menuBtn) this._menuBtn.hass = hass;
    if (this._isAttached && !this._mounted) this._mount();
  }

  set narrow(value) {
    this._narrow = value;
    if (this._menuBtn) this._menuBtn.narrow = value;
  }

  connectedCallback() {
    this._isAttached = true;
    if (this._hass && !this._mounted) this._mount();
  }

  disconnectedCallback() {
    this._mounted = false;
    this._isAttached = false;
  }

  // ── Layout ────────────────────────────────────────────────────────────────

  _mount() {
    if (this._mounted) return;
    this._mounted = true;

    const T = STRINGS[getLang(this._hass)];

    this.style.cssText = `
      display: grid;
      grid-template-rows: 56px minmax(0, 1fr);
      height: 100%;
      width: 100%;
      background: var(--primary-background-color);
      overflow: hidden;
    `;

    // ── Header (matches HA native panels) ──────────────────────────────────
    const header = document.createElement("div");
    header.style.cssText = `
      display: flex;
      align-items: center;
      padding: 0 16px;
      background-color: var(--app-header-background-color, var(--primary-color));
      color: var(--app-header-text-color, var(--text-primary-color));
      z-index: 2;
    `;

    this._menuBtn = document.createElement("ha-menu-button");
    this._menuBtn.hass = this._hass;
    this._menuBtn.narrow = this._narrow;
    header.appendChild(this._menuBtn);

    const titleEl = document.createElement("div");
    titleEl.textContent = T.title;
    titleEl.style.cssText = `
      margin-left: 24px;
      font-size: 20px;
      font-weight: 500;
      line-height: normal;
      flex: 1;
      letter-spacing: 0.15px;
      font-family: var(--paper-font-title_-_font-family, -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif);
      -webkit-font-smoothing: antialiased;
    `;
    header.appendChild(titleEl);
    this.appendChild(header);

    // ── Content area ───────────────────────────────────────────────────────
    const content = document.createElement("div");
    content.style.cssText = `
      overflow-y: auto;
      padding: 16px;
    `;
    content.innerHTML = this._buildHTML(T);
    this.appendChild(content);

    // Bind events
    this._bindEvents(content, T);

    // Load credentials
    this._loadCredentials(content, T);
  }

  // ── HTML template ─────────────────────────────────────────────────────────

  _buildHTML(T) {
    return `
      <style>
        .card {
          background: var(--card-background-color);
          border-radius: 12px; padding: 24px; max-width: 600px;
          margin: 0 auto; box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.1));
        }
        .subtitle { color: var(--secondary-text-color); margin: 0 0 20px; font-size: 0.9rem; }
        h2 { font-size: 1rem; font-weight: 600; margin: 20px 0 8px; color: var(--primary-text-color); }
        .credential-row {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 12px; border-radius: 8px; margin-bottom: 6px;
          background: var(--secondary-background-color);
        }
        .credential-info { display: flex; flex-direction: column; gap: 2px; }
        .credential-name { font-weight: 500; color: var(--primary-text-color); font-size: 0.9rem; }
        .credential-id { font-size: 0.75rem; color: var(--secondary-text-color); font-family: monospace; }
        .empty { color: var(--secondary-text-color); font-size: 0.875rem; margin: 0; }
        .btn-delete {
          padding: 6px 12px; border-radius: 6px; border: 1px solid var(--error-color, #ef4444);
          background: transparent; color: var(--error-color, #ef4444);
          cursor: pointer; font-size: 0.8rem; white-space: nowrap;
        }
        .btn-delete:hover { background: var(--error-color, #ef4444); color: white; }
        .divider { border: none; border-top: 1px solid var(--divider-color); margin: 20px 0; }
        .form-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
        input {
          flex: 1; min-width: 200px; padding: 10px 14px; border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--input-fill-color, var(--secondary-background-color));
          color: var(--primary-text-color); font-size: 0.9rem;
        }
        .btn-add {
          padding: 10px 20px; border-radius: 8px; border: none;
          background: var(--primary-color); color: white;
          font-weight: 600; cursor: pointer; font-size: 0.9rem; white-space: nowrap;
        }
        .btn-add:disabled { opacity: 0.5; cursor: not-allowed; }
        .status { padding: 10px 14px; border-radius: 8px; font-size: 0.875rem; display: none; margin-top: 8px; }
        .status.info    { display: block; background: #1e3a5f; color: #93c5fd; }
        .status.success { display: block; background: #052e16; color: #86efac; }
        .status.error   { display: block; background: #450a0a; color: #fca5a5; }
      </style>
      <div class="card">
        <p class="subtitle">${T.subtitle}</p>

        <h2>${T.registered}</h2>
        <div id="credentials-list"><p class="empty">${T.loading}</p></div>

        <hr class="divider">

        <h2>${T.add}</h2>
        <div class="form-row">
          <input id="passkey-name" type="text" placeholder="${T.placeholder}" />
          <button id="register-btn" class="btn-add">${T.addBtn}</button>
        </div>
        <div id="status" class="status"></div>
      </div>
    `;
  }

  // ── Event binding ─────────────────────────────────────────────────────────

  _bindEvents(root, T) {
    const btn = root.querySelector("#register-btn");
    btn.addEventListener("click", () => {
      if (!window.PublicKeyCredential) {
        this._setStatus(root, T.noSupport, "error");
        return;
      }
      const name = root.querySelector("#passkey-name").value.trim() || "My Passkey";
      this._registerPasskey(root, T, name, btn);
    });
  }

  // ── Auth helpers ──────────────────────────────────────────────────────────

  _authHeaders() {
    try {
      const token = this._hass?.auth?.data?.access_token;
      if (token) return { Authorization: `Bearer ${token}` };
    } catch { /* ignore */ }
    return {};
  }

  _bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let str = "";
    for (const b of bytes) str += String.fromCharCode(b);
    return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
  }

  _base64urlToBuffer(b64) {
    b64 = b64.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const bin = atob(b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }

  // ── Credentials ───────────────────────────────────────────────────────────

  async _loadCredentials(root, T) {
    try {
      const res = await fetch("/api/webauthn_mfa/list", {
        headers: this._authHeaders(),
        credentials: "same-origin",
      });
      if (res.ok) {
        this._credentials = await res.json();
        this._renderCredentials(root, T);
      }
    } catch (e) {
      console.error("[WebAuthn] loadCredentials error:", e);
    }
  }

  _renderCredentials(root, T) {
    const container = root.querySelector("#credentials-list");
    if (!container) return;

    if (this._credentials.length === 0) {
      container.innerHTML = `<p class="empty">${T.empty}</p>`;
      return;
    }

    container.innerHTML = this._credentials.map(c => `
      <div class="credential-row">
        <div class="credential-info">
          <span class="credential-name">🔑 ${c.name}</span>
          <span class="credential-id">${c.credential_id}</span>
        </div>
        <button class="btn-delete" data-id="${c.credential_id}">${T.delete}</button>
      </div>
    `).join("");

    container.querySelectorAll(".btn-delete").forEach(btn => {
      btn.addEventListener("click", () => this._deleteCredential(root, T, btn.dataset.id));
    });
  }

  async _deleteCredential(root, T, credentialId) {
    if (!confirm(T.confirmDelete)) return;
    try {
      const res = await fetch(`/api/webauthn_mfa/delete/${credentialId}`, {
        method: "DELETE",
        headers: this._authHeaders(),
        credentials: "same-origin",
      });
      if (res.ok) {
        this._credentials = this._credentials.filter(c => c.credential_id !== credentialId);
        this._renderCredentials(root, T);
        this._setStatus(root, T.deleted, "success");
      }
    } catch {
      this._setStatus(root, T.deleteError, "error");
    }
  }

  async _registerPasskey(root, T, name, btn) {
    btn.disabled = true;
    btn.textContent = T.registering;
    this._setStatus(root, T.waiting, "info");

    try {
      const chalRes = await fetch("/api/webauthn_mfa/register/challenge", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this._authHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({}),
      });
      if (!chalRes.ok) throw new Error((await chalRes.json()).message || T.serverError);

      const options = await chalRes.json();
      options.challenge = this._base64urlToBuffer(options.challenge);
      options.user.id = this._base64urlToBuffer(options.user.id);
      if (options.excludeCredentials) {
        options.excludeCredentials = options.excludeCredentials.map(c => ({
          ...c, id: this._base64urlToBuffer(c.id),
        }));
      }

      const credential = await navigator.credentials.create({ publicKey: options });

      const regRes = await fetch("/api/webauthn_mfa/register/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this._authHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({
          name,
          response: {
            id: credential.id,
            rawId: this._bufferToBase64url(credential.rawId),
            type: credential.type,
            response: {
              attestationObject: this._bufferToBase64url(credential.response.attestationObject),
              clientDataJSON: this._bufferToBase64url(credential.response.clientDataJSON),
            },
          },
        }),
      });
      if (!regRes.ok) throw new Error((await regRes.json()).message || T.regError);

      this._setStatus(root, T.registered_ok(name), "success");
      root.querySelector("#passkey-name").value = "";
      await this._loadCredentials(root, T);
    } catch (err) {
      this._setStatus(root, err.name === "NotAllowedError" ? T.cancelled : `❌ ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = T.addBtn;
    }
  }

  _setStatus(root, msg, type) {
    const el = root.querySelector("#status");
    if (!el) return;
    el.className = `status ${type}`;
    el.textContent = msg;
  }
}

customElements.define("webauthn-panel", WebAuthnPanel);