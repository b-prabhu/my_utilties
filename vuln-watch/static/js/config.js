/* VulnWatch configuration page */
(function () {
  const { api, esc, fmtDate, toast } = VW;
  const $ = (id) => document.getElementById(id);
  let cfg = null, saved = "", defaults = null;

  const PRESETS = [
    { id: "nextjs", name: "Next.js", cpes: ["cpe:2.3:a:vercel:next.js"], keywords: [], packages: [{ ecosystem: "npm", name: "next", severity: "" }] },
    { id: "typescript", name: "TypeScript", cpes: ["cpe:2.3:a:microsoft:typescript"], keywords: [], packages: [{ ecosystem: "npm", name: "typescript", severity: "" }] },
    { id: "django", name: "Django", cpes: ["cpe:2.3:a:djangoproject:django"], keywords: [], packages: [{ ecosystem: "pip", name: "django", severity: "" }] },
    { id: "fastapi", name: "FastAPI", cpes: [], keywords: [], packages: [{ ecosystem: "pip", name: "fastapi", severity: "" }, { ecosystem: "pip", name: "starlette", severity: "" }] },
    { id: "flask", name: "Flask", cpes: ["cpe:2.3:a:palletsprojects:flask"], keywords: [], packages: [{ ecosystem: "pip", name: "flask", severity: "" }, { ecosystem: "pip", name: "werkzeug", severity: "" }] },
    { id: "redis", name: "Redis", cpes: ["cpe:2.3:a:redis:redis"], keywords: [], packages: [] },
    { id: "nginx", name: "NGINX", cpes: ["cpe:2.3:a:f5:nginx"], keywords: [], packages: [] },
    { id: "docker", name: "Docker", cpes: ["cpe:2.3:a:docker:docker", "cpe:2.3:a:linuxfoundation:runc"], keywords: [], packages: [] },
    { id: "helm", name: "Helm", cpes: ["cpe:2.3:a:helm:helm"], keywords: [], packages: [{ ecosystem: "go", name: "helm.sh/helm/v3", severity: "" }] },
    { id: "openssl", name: "OpenSSL", cpes: ["cpe:2.3:a:openssl:openssl"], keywords: [], packages: [] },
    { id: "java", name: "Java / Spring", cpes: ["cpe:2.3:a:vmware:spring_framework", "cpe:2.3:a:oracle:jdk"], keywords: [], packages: [{ ecosystem: "maven", name: "org.springframework:spring-core", severity: "" }] },
    { id: "dotnet", name: ".NET", cpes: ["cpe:2.3:a:microsoft:.net"], keywords: [], packages: [] },
    { id: "mongodb", name: "MongoDB", cpes: ["cpe:2.3:a:mongodb:mongodb"], keywords: [], packages: [{ ecosystem: "npm", name: "mongodb", severity: "" }] },
    { id: "elasticsearch", name: "Elasticsearch", cpes: ["cpe:2.3:a:elastic:elasticsearch"], keywords: [], packages: [] },
    { id: "entra", name: "Microsoft Entra ID", cpes: [], keywords: ["Entra ID", "Azure Active Directory"], packages: [{ ecosystem: "npm", name: "@azure/msal-node", severity: "" }] },
    { id: "terraform", name: "Terraform", cpes: ["cpe:2.3:a:hashicorp:terraform"], keywords: [], packages: [] },
  ];
  const ECOS = ["npm", "pip", "maven", "nuget", "go", "rubygems", "composer", "rust", "erlang", "actions", "pub", "swift"];

  const get = (o, path) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
  const set = (o, path, v) => { const ks = path.split("."); const last = ks.pop(); ks.reduce((a, k) => (a[k] ??= {}), o)[last] = v; };
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "tech";

  function markDirty() {
    const dirty = JSON.stringify(cfg) !== saved;
    $("savebar").classList.toggle("dirty", dirty);
    $("saveMsg").textContent = dirty ? "Unsaved changes" : "All changes saved.";
  }

  /* ---------------- simple fields bound with data-k */
  function bindFields() {
    document.querySelectorAll("[data-k]").forEach((el) => {
      const k = el.dataset.k;
      const v = get(cfg, k);
      if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? "";
      el.oninput = el.onchange = () => {
        let val = el.type === "checkbox" ? el.checked : el.value;
        if (el.dataset.num !== undefined) val = val === "" ? 0 : Number(val);
        set(cfg, k, val);
        markDirty();
      };
    });
    document.querySelectorAll("[data-iv]").forEach((b) => (b.onclick = () => {
      const [v, u] = b.dataset.iv.split(",");
      cfg.schedule.interval_value = +v; cfg.schedule.interval_unit = u;
      bindFields(); markDirty();
    }));
  }

  /* ---------------- tech stack editor */
  function listEditor(values, placeholder, onChange) {
    const wrap = document.createElement("div");
    wrap.className = "list-edit";
    const draw = () => {
      wrap.innerHTML = values.map((v, i) => `<span class="item">${esc(v)}<button type="button" data-i="${i}" aria-label="Remove ${esc(v)}">×</button></span>`).join("") +
        `<input placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}">`;
      wrap.querySelectorAll("button").forEach((b) => (b.onclick = () => { values.splice(+b.dataset.i, 1); onChange(); draw(); }));
      const inp = wrap.querySelector("input");
      const commit = () => {
        const parts = inp.value.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
        if (!parts.length) return;
        parts.forEach((p) => !values.includes(p) && values.push(p));
        onChange(); draw(); wrap.querySelector("input").focus();
      };
      inp.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(); }
        if (e.key === "Backspace" && !inp.value && values.length) { values.pop(); onChange(); draw(); wrap.querySelector("input").focus(); }
      };
      inp.onblur = commit;
    };
    draw();
    return wrap;
  }

  function techCard(t, idx) {
    const el = document.createElement("div");
    el.className = "tech" + (t.enabled === false ? " disabled" : "");
    el.innerHTML = `
      <div class="tech-head">
        <label class="toggle" title="Enable / disable"><input type="checkbox" class="en" ${t.enabled !== false ? "checked" : ""}></label>
        <input class="input name" value="${esc(t.name)}" placeholder="Display name" aria-label="Technology name">
        <input class="input mono tid" value="${esc(t.id)}" style="width:120px" placeholder="id" aria-label="Technology id" title="Unique id (lowercase). Changing it starts a fresh lookback.">
        <button class="icon-btn del" style="width:34px;height:34px" title="Remove technology" aria-label="Remove ${esc(t.name)}">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"/></svg>
        </button>
      </div>
      <div class="field"><label>NVD CPE match strings <span class="help">e.g. cpe:2.3:a:apache:kafka</span></label><div class="cpes"></div></div>
      <div class="field"><label>NVD keywords <span class="help">broad; multi-word phrases match exactly</span></label><div class="kws"></div></div>
      <div class="field"><label>Packages (GitHub Advisories)</label><div class="pkgs"></div>
        <button class="btn sm addpkg" style="align-self:flex-start">+ Package</button></div>`;
    const ch = () => markDirty();
    t.cpes ??= []; t.keywords ??= []; t.packages ??= [];
    el.querySelector(".cpes").appendChild(listEditor(t.cpes, "cpe:2.3:a:vendor:product — Enter to add", ch));
    el.querySelector(".kws").appendChild(listEditor(t.keywords, "keyword — Enter to add", ch));
    const drawPkgs = () => {
      const box = el.querySelector(".pkgs");
      box.innerHTML = t.packages.length ? t.packages.map((p, i) => `
        <div class="pkg-row" data-i="${i}">
          <select class="select eco">${ECOS.map((e) => `<option ${p.ecosystem === e ? "selected" : ""}>${e}</option>`).join("")}</select>
          <input class="input mono pname" value="${esc(p.name)}" placeholder="package (blank = whole ecosystem)">
          <select class="select psev">${["", "critical", "high", "medium", "low"].map((s) => `<option value="${s}" ${p.severity === s ? "selected" : ""}>${s || "any severity"}</option>`).join("")}</select>
          <button class="icon-btn" aria-label="Remove package">×</button>
        </div>`).join("") : `<div class="help" style="color:var(--muted);font-size:12px">No packages — NVD only.</div>`;
      box.querySelectorAll(".pkg-row").forEach((row) => {
        const p = t.packages[+row.dataset.i];
        row.querySelector(".eco").onchange = (e) => { p.ecosystem = e.target.value; ch(); };
        row.querySelector(".pname").oninput = (e) => { p.name = e.target.value.trim(); ch(); };
        row.querySelector(".psev").onchange = (e) => { p.severity = e.target.value; ch(); };
        row.querySelector(".icon-btn").onclick = () => { t.packages.splice(+row.dataset.i, 1); ch(); drawPkgs(); };
      });
    };
    drawPkgs();
    el.querySelector(".addpkg").onclick = () => { t.packages.push({ ecosystem: "npm", name: "", severity: "" }); ch(); drawPkgs(); el.querySelectorAll(".pname")[t.packages.length - 1].focus(); };
    el.querySelector(".en").onchange = (e) => { t.enabled = e.target.checked; el.classList.toggle("disabled", !t.enabled); ch(); };
    const idInput = el.querySelector(".tid");
    let idTouched = false;
    el.querySelector(".name").oninput = (e) => {
      t.name = e.target.value;
      if (t._new && !idTouched) { t.id = uniqueId(slug(t.name), t); idInput.value = t.id; }
      ch();
    };
    idInput.oninput = (e) => { idTouched = true; t.id = e.target.value.trim().toLowerCase(); ch(); };
    el.querySelector(".del").onclick = () => {
      if (!confirm(`Remove "${t.name}" from the tech stack? Existing findings stay in the store.`)) return;
      cfg.tech_stack.splice(idx, 1); drawTechs(); ch();
    };
    return el;
  }
  function uniqueId(base, self) {
    let id = base, n = 2;
    while (cfg.tech_stack.some((x) => x !== self && x.id === id)) id = `${base}-${n++}`;
    return id;
  }
  function drawTechs() {
    const list = $("techList");
    list.innerHTML = "";
    cfg.tech_stack.forEach((t, i) => list.appendChild(techCard(t, i)));
  }
  function addTech(preset) {
    const t = preset ? JSON.parse(JSON.stringify(preset)) : { id: "", name: "", cpes: [], keywords: [], packages: [] };
    t.enabled = true; t.color = "";
    t.id = uniqueId(t.id || "new-tech", t);
    if (!preset) t._new = true;
    cfg.tech_stack.push(t);
    drawTechs(); markDirty();
    const cards = $("techList").querySelectorAll(".tech");
    const last = cards[cards.length - 1];
    last.scrollIntoView({ behavior: "smooth", block: "center" });
    if (!preset) last.querySelector(".name").focus();
  }
  function presetMenu() {
    const avail = PRESETS.filter((p) => !cfg.tech_stack.some((t) => t.id === p.id));
    if (!avail.length) return toast("All presets are already added");
    const dlg = document.createElement("dialog");
    dlg.style.cssText = "border:1px solid var(--border);border-radius:14px;background:var(--surface-2);color:var(--text);padding:18px;max-width:520px;box-shadow:var(--shadow)";
    dlg.innerHTML = `<h3 style="margin-bottom:10px">Add from preset</h3><div class="row" style="gap:8px">${avail.map((p) => `<button class="chip" data-id="${p.id}">${esc(p.name)}</button>`).join("")}</div>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" value="cancel">Close</button></div>`;
    document.body.appendChild(dlg);
    dlg.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => { addTech(PRESETS.find((p) => p.id === b.dataset.id)); dlg.close(); }));
    dlg.querySelector("[value=cancel]").onclick = () => dlg.close();
    dlg.addEventListener("close", () => dlg.remove());
    dlg.showModal();
  }

  /* ---------------- appearance */
  function drawAppearance() {
    const cur = document.documentElement.dataset.themeChoice;
    $("swatches").innerHTML = VW.THEMES.map((t) => `
      <button class="swatch ${t.id === cur ? "active" : ""}" data-t="${t.id}" style="--sw-bg:${t.bg};--sw-text:${t.text}" aria-pressed="${t.id === cur}">
        ${esc(t.name)}<span class="bars"><i style="background:${t.a}"></i><i style="background:${t.b}"></i><i style="background:#d03b3b"></i><i style="background:#fab219"></i></span>
      </button>`).join("");
    $("swatches").querySelectorAll(".swatch").forEach((b) => (b.onclick = () => { VW.applyTheme(b.dataset.t); drawAppearance(); }));
    $("fontSel2").innerHTML = VW.FONTS.map((f) => `<option>${f.id}</option>`).join("");
    $("fontSel2").value = VW.store.get("vw.font", "Inter");
    $("fontSel2").onchange = () => { VW.applyFont($("fontSel2").value); const fs = document.getElementById("fontSel"); if (fs) fs.value = $("fontSel2").value; };
  }

  /* ---------------- history */
  function drawHistory(s) {
    $("cancelScan").disabled = !s.running;
    const runs = s.runs || [];
    $("histLead").textContent = runs.length ? `Last ${runs.length} runs. Next scheduled run: ${s.schedule_enabled ? fmtDate(s.next_run, true) : "paused"}.` : "No scans have run yet.";
    $("runRows").innerHTML = runs.map((r) => `<tr>
      <td>${fmtDate(r.started, true)}</td>
      <td><span class="status ${r.status === "success" ? "resolved" : r.status === "partial" ? "investigating" : r.status === "running" ? "new" : "affected"}">${esc(r.status)}</span></td>
      <td>${r.duration_s != null ? r.duration_s + " s" : "—"}</td>
      <td>${r.fetched ?? 0}</td><td><b>${r.new ?? 0}</b></td><td>${r.updated ?? 0}</td>
      <td style="max-width:420px;color:${(r.errors || []).length ? "var(--sev-critical)" : "var(--muted)"};font-size:12px">${(r.errors || []).map(esc).join("<br>") || "—"}</td>
    </tr>`).join("") || `<tr><td colspan="7" class="empty">No runs yet</td></tr>`;
  }

  /* ---------------- save / load */
  function clean(c) {
    const out = JSON.parse(JSON.stringify(c));
    out.tech_stack.forEach((t) => { delete t._new; t.packages = (t.packages || []).filter((p) => p.ecosystem); });
    return out;
  }
  async function save() {
    try {
      const r = await api("/api/config", { method: "PUT", body: clean(cfg) });
      cfg = r.config; saved = JSON.stringify(cfg);
      drawTechs(); bindFields(); markDirty();
      toast("Configuration saved");
    } catch (e) { toast(e.message, true); }
  }
  async function load() {
    cfg = await api("/api/config");
    saved = JSON.stringify(cfg);
    drawTechs(); bindFields(); markDirty();
  }

  async function init() {
    VW.mountPrefs($("prefs"));
    document.addEventListener("themechange", drawAppearance);
    drawAppearance();
    $("scanBtn").onclick = () => VW.scanNow($("scanBtn"));
    $("addTech").onclick = () => addTech(null);
    $("presetBtn").onclick = presetMenu;
    $("saveBtn").onclick = save;
    $("discardBtn").onclick = () => { cfg = JSON.parse(saved); drawTechs(); bindFields(); markDirty(); };
    $("resetDefaults").onclick = async () => {
      if (!confirm("Replace the current configuration with the defaults? API keys are kept. You still need to Save.")) return;
      defaults ??= await api("/api/config/default");
      const keep = { nvd: cfg.sources?.nvd?.api_key, gh: cfg.sources?.github?.token, hook: cfg.notifications?.webhook_url };
      cfg = JSON.parse(JSON.stringify(defaults));
      cfg.sources.nvd.api_key = keep.nvd || ""; cfg.sources.github.token = keep.gh || ""; cfg.notifications.webhook_url = keep.hook || "";
      drawTechs(); bindFields(); markDirty();
    };
    $("exportBtn").onclick = () => {
      const blob = new Blob([JSON.stringify(clean(cfg), null, 2)], { type: "application/json" });
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "vulnwatch-config.json" });
      a.click(); URL.revokeObjectURL(a.href);
      toast("Exported (secrets are masked)");
    };
    $("importBtn").onclick = () => $("importFile").click();
    $("importFile").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try {
        const data = JSON.parse(await f.text());
        if (!Array.isArray(data.tech_stack)) throw new Error("file has no tech_stack array");
        cfg = { ...cfg, ...data };
        drawTechs(); bindFields(); markDirty();
        toast("Imported — review and Save");
      } catch (err) { toast("Import failed: " + err.message, true); }
      e.target.value = "";
    };
    $("cancelScan").onclick = async () => { await api("/api/scan/cancel", { method: "POST" }); toast("Cancelling after the current request…"); };
    window.addEventListener("beforeunload", (e) => { if (JSON.stringify(cfg) !== saved) { e.preventDefault(); e.returnValue = ""; } });
    document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); } });
    VW.mountScanPill($("scanPill"), drawHistory);
    try { await load(); } catch (e) { toast("Failed to load configuration: " + e.message, true); }
  }
  init();
})();
