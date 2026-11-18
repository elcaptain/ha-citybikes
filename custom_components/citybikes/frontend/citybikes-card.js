/**
 * CityBikes Card for Home Assistant.
 *
 * Shows bike-share stations set up with the CityBikes integration:
 * available bikes, e-bikes and empty docks, with a dock occupancy bar.
 */

const VERSION = "1.2.1";
const PLATFORM = "citybikes";
const KEYS = ["free_bikes", "free_ebikes", "empty_slots", "last_reported"];
// Stations up to this many docks get one bar segment per dock. Bigger stations
// (some have hundreds) and placeholder counts for dockless networks get a
// continuous bar, because the segments would be too thin to see.
const MAX_SEGMENTS = 40;

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; height: 100%; box-sizing: border-box; }
  .header {
    padding: 16px 16px 0;
    font-size: var(--ha-card-header-font-size, 1.25rem);
    font-weight: var(--ha-font-weight-normal, 400);
    color: var(--ha-card-header-color, var(--primary-text-color));
  }
  .stations { padding: 8px 0; }
  .station {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 6px 12px;
    padding: 10px 16px;
    cursor: pointer;
    outline: none;
  }
  .station:focus-visible { background: var(--secondary-background-color); }
  .station + .station { border-top: 1px solid var(--divider-color); }
  .name {
    font-weight: var(--ha-font-weight-medium, 500);
    color: var(--primary-text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta {
    font-size: 0.85em;
    color: var(--secondary-text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .count {
    grid-row: span 2;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 1.75em;
    font-weight: var(--ha-font-weight-medium, 500);
    font-variant-numeric: tabular-nums;
    color: var(--primary-text-color);
  }
  .count ha-icon { --mdc-icon-size: 26px; color: var(--state-icon-color, var(--secondary-text-color)); }
  .count img { height: 32px; width: auto; max-width: 64px; object-fit: contain; }
  .count.low { color: var(--warning-color, #ffa600); }
  .count.empty { color: var(--error-color, #db4437); }
  .bar {
    grid-column: 1 / -1;
    display: flex;
    height: 8px;
    border-radius: 4px;
    overflow: hidden;
    background: var(--divider-color);
  }
  .bar span { display: block; height: 100%; }
  .bar .bikes { background: var(--primary-color); }
  .bar .ebikes { background: var(--success-color, #43a047); }
  .bar.docks { gap: 2px; background: none; border-radius: 0; }
  .bar.docks span { flex: 1; min-width: 0; border-radius: 2px; }
  .bar.docks .free { background: var(--divider-color); }
  .legend {
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    font-size: 0.85em;
    color: var(--secondary-text-color);
  }
  .legend span { display: inline-flex; align-items: center; gap: 4px; }
  .legend ha-icon { --mdc-icon-size: 16px; }
  .legend .ebikes ha-icon { color: var(--success-color, #43a047); }
  .unavailable .count, .unavailable .bar { opacity: 0.4; }
  .empty-state { padding: 16px; color: var(--secondary-text-color); }
`;

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function numeric(stateObj) {
  if (!stateObj) return null;
  const value = Number(stateObj.state);
  return Number.isFinite(value) && stateObj.state !== "" ? value : null;
}

function relativeTime(hass, date) {
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const units = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const rtf = new Intl.RelativeTimeFormat(hass.locale?.language || hass.language, {
    numeric: "auto",
  });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(0, "minute");
}

/** Return every CityBikes station device, with its sensors keyed by translation key. */
function findStations(hass) {
  const stations = new Map();
  for (const entity of Object.values(hass.entities || {})) {
    if (entity.platform !== PLATFORM || !entity.device_id) continue;
    if (!KEYS.includes(entity.translation_key)) continue;
    if (!stations.has(entity.device_id)) stations.set(entity.device_id, {});
    stations.get(entity.device_id)[entity.translation_key] = entity.entity_id;
  }
  return stations;
}

class CityBikesCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("citybikes-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._renderKey = null;
  }

  setConfig(config) {
    if (config.devices !== undefined && !Array.isArray(config.devices)) {
      throw new Error("`devices` must be a list of CityBikes station device IDs");
    }
    this._config = { ...config };
    this._renderKey = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 1 + 2 * Math.max(this._stations().length, 1);
  }

  getGridOptions() {
    const rows = Math.max(this._stations().length, 1) * 2 + (this._config.title ? 1 : 0);
    return { columns: 6, min_columns: 3, rows, min_rows: 2 };
  }

  _stations() {
    if (!this._hass) return [];
    const all = findStations(this._hass);
    const ids = this._config.devices?.length
      ? this._config.devices.filter((id) => all.has(id))
      : [...all.keys()].sort((a, b) =>
          this._deviceName(a).localeCompare(this._deviceName(b))
        );
    return ids.map((id) => ({ deviceId: id, entities: all.get(id) }));
  }

  _deviceName(deviceId) {
    const device = this._hass.devices?.[deviceId];
    return device?.name_by_user || device?.name || deviceId;
  }

  _render() {
    if (!this._hass) return;
    const stations = this._stations();

    // Only redraw when one of the shown sensors changed.
    const key = JSON.stringify([
      this._config,
      stations.map(({ deviceId, entities }) => [
        this._deviceName(deviceId),
        Object.values(entities).map((id) => {
          const s = this._hass.states[id];
          return s && [s.state, s.last_changed];
        }),
      ]),
      Math.floor(Date.now() / 60000),
    ]);
    if (key === this._renderKey) return;
    this._renderKey = key;

    const title = this._config.title
      ? `<div class="header">${escapeHtml(this._config.title)}</div>`
      : "";
    const body = stations.length
      ? `<div class="stations">${stations.map((s) => this._renderStation(s)).join("")}</div>`
      : `<div class="empty-state">${
          this._config.devices?.length
            ? "The selected stations no longer exist. Edit the card to pick other stations."
            : "No CityBikes stations found. Add a station to the CityBikes integration first."
        }</div>`;

    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${title}${body}</ha-card>`;
    // A broken image link falls back to the bike icon, and is not retried.
    this.shadowRoot.querySelectorAll(".count img").forEach((img) => {
      img.addEventListener("error", () => {
        this._failedImage = this._config.image;
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", "mdi:bike");
        img.replaceWith(icon);
      });
    });
    this.shadowRoot.querySelectorAll(".station").forEach((el) => {
      const open = () => this._moreInfo(el.dataset.entity);
      el.addEventListener("click", open);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          open();
        }
      });
    });
  }

  _bikeImage() {
    const image = this._config.image;
    const url = image && image !== this._failedImage ? this._imageUrl(image) : null;
    return url
      ? `<img src="${escapeHtml(url)}" alt="">`
      : `<ha-icon icon="mdi:bike"></ha-icon>`;
  }

  /** Return the address of the image, resolving media from the media browser. */
  _imageUrl(image) {
    if (!image.startsWith("media-source://")) return image;
    if (this._resolving !== image) {
      this._resolving = image;
      this._resolvedUrl = null;
      this._hass
        .callWS({ type: "media_source/resolve_media", media_content_id: image })
        .then((result) => {
          if (this._resolving === image) this._resolvedUrl = result.url;
        })
        .catch(() => {
          this._failedImage = image;
        })
        .finally(() => {
          this._renderKey = null;
          this._render();
        });
    }
    return this._resolvedUrl;
  }

  _renderStation({ deviceId, entities }) {
    const hass = this._hass;
    const states = Object.fromEntries(
      Object.entries(entities).map(([k, id]) => [k, hass.states[id]])
    );
    const bikes = numeric(states.free_bikes);
    const ebikes = numeric(states.free_ebikes);
    const docks = numeric(states.empty_slots);
    const unavailable = bikes === null;
    const device = hass.devices?.[deviceId];

    // The station's own report time; only shown when that sensor is enabled.
    const reported = states.last_reported ? new Date(states.last_reported.state) : null;
    const meta = [
      device?.manufacturer,
      unavailable
        ? "Unavailable"
        : reported && !isNaN(reported)
          ? `Reported ${relativeTime(hass, reported)}`
          : null,
    ]
      .filter(Boolean)
      .map(escapeHtml)
      .join(" · ");

    let countClass = "";
    if (bikes === 0) countClass = "empty";
    else if (bikes !== null && bikes <= 2) countClass = "low";

    const bar = this._renderBar(bikes, ebikes, docks);

    const legend = [
      ebikes !== null
        ? `<span class="ebikes"><ha-icon icon="mdi:bicycle-electric"></ha-icon>${ebikes} e-bikes</span>`
        : "",
      docks !== null ? `<span><ha-icon icon="mdi:parking"></ha-icon>${docks} empty docks</span>` : "",
    ].join("");

    return `
      <div class="station ${unavailable ? "unavailable" : ""}" role="button" tabindex="0"
           data-entity="${escapeHtml(entities.free_bikes || "")}">
        <div class="name">${escapeHtml(this._deviceName(deviceId))}</div>
        <div class="count ${countClass}" title="Available bikes">
          ${this._bikeImage()}${unavailable ? "–" : bikes}
        </div>
        <div class="meta">${meta}</div>
        ${bar}
        ${legend ? `<div class="legend">${legend}</div>` : ""}
      </div>`;
  }

  _renderBar(bikes, ebikes, docks) {
    // Virtual and dockless stations report no empty docks: there is nothing to fill.
    if (bikes === null || docks === null) return "";
    const total = bikes + docks;
    if (!total) return "";
    const eb = Math.min(ebikes ?? 0, bikes);
    const parts = [
      ["bikes", bikes - eb],
      ["ebikes", eb],
      ["free", docks],
    ];
    const label = `${bikes} bikes, ${docks} empty docks`;

    if (total <= MAX_SEGMENTS) {
      const segments = parts
        .map(([cls, n]) => `<span class="${cls}"></span>`.repeat(n))
        .join("");
      return `<div class="bar docks" role="img" aria-label="${label}">${segments}</div>`;
    }
    const segments = parts
      .filter(([cls, n]) => cls !== "free" && n)
      .map(([cls, n]) => `<span class="${cls}" style="width:${(100 * n) / total}%"></span>`)
      .join("");
    return `<div class="bar" role="img" aria-label="${label}">${segments}</div>`;
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }
}

const UPLOAD_TYPES = ["image/png", "image/jpeg", "image/gif"];

const EDITOR_STYLE = `
  .citybikes-image { margin-bottom: 24px; }
  .citybikes-image .label { margin-bottom: 8px; color: var(--primary-text-color); }
  .citybikes-image .row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .citybikes-image img {
    height: 48px; width: auto; max-width: 96px; object-fit: contain;
    padding: 4px; border-radius: 8px; border: 1px solid var(--divider-color);
  }
  .citybikes-image button {
    font: inherit; cursor: pointer; padding: 8px 16px; border-radius: 18px;
    border: 1px solid var(--primary-color); background: none; color: var(--primary-color);
  }
  .citybikes-image button.remove { border-color: transparent; color: var(--secondary-text-color); }
  .citybikes-image button:disabled { opacity: 0.5; cursor: default; }
  .citybikes-image .status { font-size: 0.9em; color: var(--secondary-text-color); }
  .citybikes-image .status.error { color: var(--error-color, #db4437); }
`;

class CityBikesCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    else this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) this._build();

    // The image part is our own markup, so it does not depend on Home Assistant
    // internals that may not be loaded in the card editor.
    const image = this._config.image;
    this._thumb.hidden = !image;
    if (image) this._thumb.src = image;
    this._removeButton.hidden = !image;
    this._uploadButton.textContent = image ? "Replace image" : "Upload image";

    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      { name: "title", selector: { text: {} } },
      { name: "image", selector: { text: {} } },
      {
        name: "devices",
        selector: { device: { multiple: true, filter: { integration: PLATFORM } } },
      },
    ];
  }

  _build() {
    const style = document.createElement("style");
    style.textContent = EDITOR_STYLE;

    const section = document.createElement("div");
    section.className = "citybikes-image";
    section.innerHTML = `
      <div class="label">Bike image</div>
      <div class="row">
        <img alt="" hidden>
        <button type="button" class="upload">Upload image</button>
        <button type="button" class="remove" hidden>Remove</button>
        <span class="status" role="status"></span>
      </div>
      <input type="file" accept="${UPLOAD_TYPES.join(",")}" hidden>`;
    this._thumb = section.querySelector("img");
    this._uploadButton = section.querySelector(".upload");
    this._removeButton = section.querySelector(".remove");
    this._status = section.querySelector(".status");
    const input = section.querySelector("input");

    this._thumb.addEventListener("error", () => (this._thumb.hidden = true));
    this._uploadButton.addEventListener("click", () => input.click());
    this._removeButton.addEventListener("click", () => this._setImage(undefined));
    input.addEventListener("change", () => {
      const [file] = input.files;
      input.value = "";
      if (file) this._upload(file);
    });

    this._form = document.createElement("ha-form");
    this._form.computeLabel = (schema) =>
      ({
        title: "Title",
        image: "Image URL (filled in when you upload; leave empty for the bike icon)",
        devices: "Stations (leave empty to show all)",
      })[schema.name];
    this._form.addEventListener("value-changed", (ev) => this._update(ev.detail.value));

    this.append(style, section, this._form);
  }

  async _upload(file) {
    if (!UPLOAD_TYPES.includes(file.type)) {
      this._showStatus("Use a PNG, JPEG or GIF image.", true);
      return;
    }
    this._uploadButton.disabled = true;
    this._showStatus("Uploading…");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await this._hass.fetchWithAuth("/api/image/upload", {
        method: "POST",
        body,
      });
      if (response.status === 413) throw new Error("The image is too large (10 MB at most).");
      if (!response.ok) throw new Error(`Upload failed (${response.status}).`);
      const { id } = await response.json();
      this._showStatus("");
      this._setImage(`/api/image/serve/${id}/original`);
    } catch (err) {
      this._showStatus(err.message || "Upload failed.", true);
    } finally {
      this._uploadButton.disabled = false;
    }
  }

  _showStatus(text, error = false) {
    this._status.textContent = text;
    this._status.classList.toggle("error", error);
  }

  _setImage(image) {
    this._update({ ...this._config, image });
  }

  _update(value) {
    const config = { ...value };
    if (!config.title) delete config.title;
    if (!config.image) delete config.image;
    if (!config.devices?.length) delete config.devices;
    this._config = config;
    this._render();
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true })
    );
  }
}

customElements.define("citybikes-card", CityBikesCard);
customElements.define("citybikes-card-editor", CityBikesCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "citybikes-card",
  name: "CityBikes",
  description: "Available bikes, e-bikes and empty docks at your bike-share stations.",
  preview: true,
  documentationURL: "https://github.com/elcaptain/ha-citybikes#dashboard-card",
});

console.info(`%c CITYBIKES-CARD %c ${VERSION} `, "color:white;background:#2b7a3d;font-weight:700", "");
