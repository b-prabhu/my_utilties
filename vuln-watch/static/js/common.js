/* Shared helpers: theme + font selectors, API wrapper, formatting, toast, tooltip. */
(function () {
  const THEMES = [
    { id: "midnight", name: "Midnight", bg: "#0b1020", text: "#e8ecf8", a: "#7c8cff", b: "#4fd1c5" },
    { id: "light", name: "Light", bg: "#f4f6fb", text: "#121826", a: "#4f5bd5", b: "#0f9488" },
    { id: "dark", name: "Dark", bg: "#111113", text: "#f0efec", a: "#3987e5", b: "#1baf7a" },
    { id: "dracula", name: "Dracula", bg: "#1e1f29", text: "#f8f8f2", a: "#bd93f9", b: "#8be9fd" },
    { id: "nord", name: "Nord", bg: "#242933", text: "#eceff4", a: "#88c0d0", b: "#a3be8c" },
    { id: "ocean", name: "Ocean", bg: "#04161f", text: "#e3f6fb", a: "#22d3ee", b: "#34d399" },
    { id: "forest", name: "Forest", bg: "#0c1510", text: "#e6f2e9", a: "#4ade80", b: "#facc15" },
    { id: "sunset", name: "Sunset", bg: "#1a0f1a", text: "#fbeef2", a: "#fb7185", b: "#fbbf24" },
    { id: "solarized", name: "Solarized", bg: "#fdf6e3", text: "#073642", a: "#268bd2", b: "#2aa198" },
    { id: "system", name: "System (auto)", bg: "linear-gradient(135deg,#f4f6fb 50%,#0b1020 50%)", text: "#7e88ab", a: "#7c8cff", b: "#4f5bd5" },
  ];
  const FONTS = [
    { id: "Inter", gf: "Inter:wght@400;500;600;700" },
    { id: "Plus Jakarta Sans", gf: "Plus+Jakarta+Sans:wght@400;500;600;700" },
    { id: "Poppins", gf: "Poppins:wght@400;500;600;700" },
    { id: "Roboto", gf: "Roboto:wght@400;500;700" },
    { id: "IBM Plex Sans", gf: "IBM+Plex+Sans:wght@400;500;600;700" },
    { id: "Source Sans 3", gf: "Source+Sans+3:wght@400;500;600;700" },
    { id: "Nunito", gf: "Nunito:wght@400;600;700" },
    { id: "JetBrains Mono", gf: "JetBrains+Mono:wght@400;500;600;700" },
    { id: "System", gf: null },
  ];
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  function resolveTheme(id) {
    if (id !== "system") return id;
    return matchMedia("(prefers-color-scheme: light)").matches ? "light" : "midnight";
  }
  function applyTheme(id) {
    document.documentElement.dataset.theme = resolveTheme(id);
    document.documentElement.dataset.themeChoice = id;
    store.set("vw.theme", id);
    document.dispatchEvent(new CustomEvent("themechange"));
  }
  const loadedFonts = new Set();
  function applyFont(id) {
    const f = FONTS.find((x) => x.id === id) || FONTS[0];
    if (f.gf && !loadedFonts.has(f.id)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `https://fonts.googleapis.com/css2?family=${f.gf}&display=swap`;
      document.head.appendChild(link);
      loadedFonts.add(f.id);
    }
    const stack = f.gf ? `"${f.id}", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`
                       : `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`;
    document.documentElement.style.setProperty("--font", stack);
    store.set("vw.font", f.id);
  }

  // apply before first paint
  applyTheme(store.get("vw.theme", "midnight"));
  applyFont(store.get("vw.font", "Inter"));
  if (!loadedFonts.has("JetBrains Mono")) {
    const l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap";
    document.head.appendChild(l);
  }
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
    if (store.get("vw.theme", "midnight") === "system") applyTheme("system");
  });

  function mountPrefs(container) {
    container.innerHTML = `
      <label for="themeSel">Theme</label>
      <select id="themeSel" class="select sm" aria-label="Color theme">
        ${THEMES.map((t) => `<option value="${t.id}">${t.name}</option>`).join("")}
      </select>
      <label for="fontSel">Font</label>
      <select id="fontSel" class="select sm" aria-label="Font">
        ${FONTS.map((f) => `<option value="${f.id}">${f.id}</option>`).join("")}
      </select>`;
    const ts = container.querySelector("#themeSel");
    const fs = container.querySelector("#fontSel");
    ts.value = store.get("vw.theme", "midnight");
    fs.value = store.get("vw.font", "Inter");
    ts.onchange = () => applyTheme(ts.value);
    fs.onchange = () => applyFont(fs.value);
    document.addEventListener("themechange", () => { ts.value = document.documentElement.dataset.themeChoice; });
  }

  async function api(path, opts = {}) {
    const init = { method: opts.method || "GET", headers: {} };
    if (opts.body !== undefined || init.method !== "GET") {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body ?? {});
    }
    const res = await fetch(path, init);
    let data = null;
    try { data = await res.json(); } catch { /* empty */ }
    if (!res.ok) {
      const err = new Error((data && (data.error + (data.details ? ": " + data.details.join("; ") : ""))) || res.statusText);
      err.status = res.status; err.data = data;
      throw err;
    }
    return data;
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function fmtDate(iso, withTime = false) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return "—";
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) });
  }
  function relTime(iso) {
    if (!iso) return "never";
    const diff = (new Date(iso) - Date.now()) / 1000;
    const abs = Math.abs(diff);
    const units = [["day", 86400], ["hour", 3600], ["minute", 60]];
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    for (const [u, s] of units) if (abs >= s) return rtf.format(Math.round(diff / s), u);
    return diff > 0 ? "in a moment" : "just now";
  }
  function fmtDuration(sec) {
    if (sec >= 604800 && sec % 604800 === 0) return `${sec / 604800}w`;
    if (sec >= 86400) return `${+(sec / 86400).toFixed(1)}d`;
    if (sec >= 3600) return `${+(sec / 3600).toFixed(1)}h`;
    return `${Math.round(sec / 60)}m`;
  }

  let toastTimer;
  function toast(msg, isError = false) {
    let el = document.querySelector(".toast");
    if (!el) { el = document.createElement("div"); el.className = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.textContent = msg;
    el.classList.toggle("error", isError);
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  const tip = {
    el: null,
    show(html, ev) {
      if (!this.el) { this.el = document.createElement("div"); this.el.className = "tooltip"; document.body.appendChild(this.el); }
      this.el.innerHTML = html;
      this.el.classList.add("show");
      this.move(ev);
    },
    move(ev) {
      if (!this.el) return;
      const pad = 14, r = this.el.getBoundingClientRect();
      let x = ev.clientX + pad, y = ev.clientY + pad;
      if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
      if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
      this.el.style.left = x + "px"; this.el.style.top = y + "px";
    },
    hide() { this.el && this.el.classList.remove("show"); },
  };

  function mountScanPill(el, onUpdate) {
    async function refresh() {
      try {
        const s = await api("/api/status");
        el.classList.toggle("running", s.running);
        el.classList.toggle("off", !s.schedule_enabled && !s.running);
        const txt = s.running
          ? `Scanning… ${esc(s.progress || "")}`
          : `Last scan ${relTime(s.last_run)} · ${!s.scheduler_active ? "scheduled externally (cron)" : s.schedule_enabled ? `next ${relTime(s.next_run)} · every ${fmtDuration(s.interval_seconds)}` : "schedule paused"}`;
        el.innerHTML = `<span class="pulse"></span><span>${txt}</span>`;
        el.title = s.running ? s.progress : `Last: ${fmtDate(s.last_run, true)}\nNext: ${fmtDate(s.next_run, true)}`;
        onUpdate && onUpdate(s);
        setTimeout(refresh, s.running ? 2500 : 20000);
      } catch {
        el.innerHTML = `<span class="pulse" style="background:var(--sev-critical)"></span><span>Server unreachable</span>`;
        setTimeout(refresh, 10000);
      }
    }
    refresh();
  }

  async function scanNow(btn) {
    btn && (btn.disabled = true);
    try {
      const r = await api("/api/scan", { method: "POST" });
      toast(r.message || "Scan started");
    } catch (e) {
      toast(e.status === 409 ? "A scan is already running" : "Could not start scan: " + e.message, e.status !== 409);
    } finally {
      setTimeout(() => btn && (btn.disabled = false), 1500);
    }
  }

  window.VW = { THEMES, FONTS, applyTheme, applyFont, mountPrefs, api, esc, fmtDate, relTime, fmtDuration, toast, tip, mountScanPill, scanNow, store };
})();
