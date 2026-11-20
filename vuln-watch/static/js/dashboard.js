/* VulnWatch dashboard */
(function () {
  const { api, esc, fmtDate, relTime, toast, tip } = VW;
  const SEVS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];
  const SEV_LABEL = { CRITICAL: "Critical", HIGH: "High", MEDIUM: "Medium", LOW: "Low", UNKNOWN: "Unscored", NONE: "None" };
  const SEV_RANK = { CRITICAL: 5, HIGH: 4, MEDIUM: 3, LOW: 2, NONE: 1, UNKNOWN: 0 };
  const STATUS_LABEL = { new: "New", investigating: "Investigating", affected: "Affected", mitigated: "Mitigated", resolved: "Resolved", not_affected: "Not affected", ignored: "Ignored" };
  const OPEN = new Set(["new", "investigating", "affected"]);
  const $ = (id) => document.getElementById(id);
  const sevColor = (s) => getComputedStyle(document.documentElement).getPropertyValue(
    { CRITICAL: "--sev-critical", HIGH: "--sev-high", MEDIUM: "--sev-medium", LOW: "--sev-low" }[s] || "--sev-none").trim();

  const saved = (() => { try { return JSON.parse(VW.store.get("vw.filters", "{}")); } catch { return {}; } })();
  const S = {
    all: [], techs: [], techName: {},
    q: "", sev: new Set(saved.sev || []), tech: saved.tech || "", status: saved.status ?? "open",
    kev: !!saved.kev, range: saved.range ?? 90, newSince: null,
    sort: saved.sort || { key: "severity", dir: -1 }, page: 0, size: +(saved.size || 50),
    selected: new Set(), lastRun: null,
  };
  const persist = () => VW.store.set("vw.filters", JSON.stringify({ sev: [...S.sev], tech: S.tech, status: S.status, kev: S.kev, range: S.range, sort: S.sort, size: S.size }));

  /* ------------------------------------------------------------ filtering */
  function inRange(v) {
    if (!S.range) return true;
    const p = v.published ? new Date(v.published) : null;
    return p && Date.now() - p <= S.range * 86400000;
  }
  function matchesQ(v, q) {
    if (!q) return true;
    const hay = [v.id, v.cve, ...(v.aliases || []), v.title, v.description, ...(v.cwes || []),
      ...(v.packages || []).map((p) => `${p.ecosystem} ${p.name}`), ...(v.affected || []),
      ...(v.techs || []).map((t) => S.techName[t] || t), v.notes].join(" ").toLowerCase();
    return q.split(/\s+/).every((w) => hay.includes(w));
  }
  function baseFiltered() { // everything except severity chip filter (charts use this)
    const q = S.q.trim().toLowerCase();
    return S.all.filter((v) => inRange(v) &&
      (!S.tech || (v.techs || []).includes(S.tech)) &&
      (!S.status || (S.status === "open" ? OPEN.has(v.status) : v.status === S.status)) &&
      (!S.kev || v.kev) && (S.newSince ? (v.first_seen || "") >= S.newSince : true) && matchesQ(v, q));
  }
  const sevKey = (v) => (v.severity === "NONE" ? "UNKNOWN" : v.severity || "UNKNOWN");
  function filtered() {
    const base = baseFiltered();
    return S.sev.size ? base.filter((v) => S.sev.has(sevKey(v))) : base;
  }
  function sortRows(rows) {
    const { key, dir } = S.sort;
    const val = (v) => {
      switch (key) {
        case "severity": return SEV_RANK[v.severity] * 100 + (v.cvss || 0) * 5 + (v.kev ? 1 : 0) * 50;
        case "cvss": return v.cvss ?? -1;
        case "epss": return v.epss ? v.epss.score : -1;
        case "published": return v.published || "";
        case "status": return v.status || "";
        case "title": return (v.title || "").toLowerCase();
        default: return v.id || "";
      }
    };
    return rows.sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * dir; });
  }

  /* ------------------------------------------------------------ KPIs */
  function renderKpis() {
    const scope = S.all.filter(inRange);
    const open = scope.filter((v) => OPEN.has(v.status));
    const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString();
    const tiles = [
      { k: "total", label: "Tracked", value: scope.length, sub: `${S.all.length} in store`, color: "var(--accent)" },
      { k: "critical", label: "Critical · open", value: open.filter((v) => v.severity === "CRITICAL").length, sub: `${scope.filter((v) => v.severity === "CRITICAL").length} total`, color: "var(--sev-critical)" },
      { k: "high", label: "High · open", value: open.filter((v) => v.severity === "HIGH").length, sub: `${scope.filter((v) => v.severity === "HIGH").length} total`, color: "var(--sev-high)" },
      { k: "kev", label: "Known exploited", value: scope.filter((v) => v.kev).length, sub: "CISA KEV catalog", color: "var(--sev-critical)" },
      { k: "new", label: "New this week", value: scope.filter((v) => (v.first_seen || "") >= weekAgo).length, sub: "first seen ≤ 7 days", color: "var(--accent-2)" },
      { k: "open", label: "Awaiting triage", value: scope.filter((v) => v.status === "new").length, sub: `${open.length} open overall`, color: "var(--sev-medium)" },
    ];
    $("kpis").innerHTML = tiles.map((t) => `
      <div class="card kpi" data-k="${t.k}" style="--kpi-color:${t.color}" tabindex="0" role="button" aria-label="${t.label}: ${t.value}. Click to filter">
        <div class="label"><span class="dot" style="--c:${t.color}"></span>${t.label}</div>
        <div class="value">${t.value.toLocaleString()}</div>
        <div class="sub">${t.sub}</div>
      </div>`).join("");
    $("kpis").querySelectorAll(".kpi").forEach((el) => {
      const go = () => applyKpi(el.dataset.k);
      el.onclick = go;
      el.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), go());
    });
  }
  function applyKpi(k) {
    resetFilters(false);
    if (k === "total") S.status = "";
    if (k === "critical") S.sev = new Set(["CRITICAL"]);
    if (k === "high") S.sev = new Set(["HIGH"]);
    if (k === "kev") { S.kev = true; S.status = ""; }
    if (k === "new") { S.newSince = new Date(Date.now() - 7 * 86400000).toISOString(); S.status = ""; }
    if (k === "open") S.status = "new";
    syncControls(); render();
    document.querySelector(".table-card").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ------------------------------------------------------------ charts (inline SVG) */
  function svgEl(w, h) { return `<svg viewBox="0 0 ${w} ${h}" role="img" preserveAspectRatio="xMinYMin meet">`; }
  function bindTips(root, getHtml, onClick) {
    root.querySelectorAll("[data-tip]").forEach((el) => {
      el.addEventListener("mouseenter", (e) => tip.show(getHtml(el.dataset.tip), e));
      el.addEventListener("mousemove", (e) => tip.move(e));
      el.addEventListener("mouseleave", () => tip.hide());
      if (onClick) el.addEventListener("click", () => { tip.hide(); onClick(el.dataset.tip); });
    });
  }
  function niceMax(n) {
    if (n <= 5) return 5;
    const p = Math.pow(10, Math.floor(Math.log10(n)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= n) return m * p;
    return 10 * p;
  }
  // rounded top / right only (data end), square at baseline
  function barPath(x, y, w, h, horizontal, r = 4) {
    if (w <= 0 || h <= 0) return "";
    if (horizontal) { r = Math.min(r, w, h / 2); return `M${x},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 -${r},${r}h-${w - r}z`; }
    r = Math.min(r, h, w / 2);
    return `M${x},${y + h}v-${h - r}a${r},${r} 0 0 1 ${r},-${r}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - r}z`;
  }

  function chartSeverity(rows) {
    const counts = Object.fromEntries(SEVS.map((s) => [s, 0]));
    rows.forEach((v) => counts[sevKey(v)]++);
    const total = rows.length || 1;
    const W = 360, rowH = 34, H = SEVS.length * rowH + 4, labelW = 74, valW = 70, max = Math.max(1, ...Object.values(counts));
    let s = svgEl(W, H);
    SEVS.forEach((sev, i) => {
      const y = i * rowH + 6, bw = ((W - labelW - valW) * counts[sev]) / max;
      const active = !S.sev.size || S.sev.has(sev);
      s += `<g data-tip="${sev}" style="cursor:pointer;opacity:${active ? 1 : 0.35}">
        <rect class="hit" x="0" y="${y - 4}" width="${W}" height="${rowH}"></rect>
        <text x="0" y="${y + 15}" class="label-strong">${SEV_LABEL[sev]}</text>
        <rect x="${labelW}" y="${y + 3}" width="${W - labelW - valW}" height="16" rx="4" fill="var(--surface-3)" opacity=".5"></rect>
        <path d="${barPath(labelW, y + 3, Math.max(bw, counts[sev] ? 3 : 0), 16, true)}" fill="${sevColor(sev)}"></path>
        <text x="${W - valW + 10}" y="${y + 15}" class="label-strong">${counts[sev]}</text>
        <text x="${W - valW + 42}" y="${y + 15}">${Math.round((counts[sev] / total) * 100)}%</text>
      </g>`;
    });
    $("chartSev").innerHTML = s + "</svg>";
    bindTips($("chartSev"), (sev) => `<div class="t-title">${SEV_LABEL[sev]}</div>
      <div class="t-row">Vulnerabilities <b>${counts[sev]}</b></div>
      <div class="t-row">Share <b>${Math.round((counts[sev] / total) * 100)}%</b></div>
      <div class="t-row" style="margin-top:4px;color:var(--muted)">Click to toggle filter</div>`,
    (sev) => { S.sev.has(sev) ? S.sev.delete(sev) : S.sev.add(sev); S.page = 0; syncControls(); render(); });
  }

  function stackedLegend(present) {
    return `<div class="legend">${SEVS.filter((s) => present.has(s)).map((s) => `<span><i class="dot" style="--c:${sevColor(s)}"></i>${SEV_LABEL[s]}</span>`).join("")}</div>`;
  }

  function chartTech(rows) {
    const byTech = {};
    const present = new Set();
    S.techs.forEach((t) => (byTech[t.id] = Object.fromEntries(SEVS.map((s) => [s, 0]))));
    rows.forEach((v) => (v.techs || []).forEach((t) => {
      byTech[t] = byTech[t] || Object.fromEntries(SEVS.map((s) => [s, 0]));
      byTech[t][sevKey(v)]++; present.add(sevKey(v));
    }));
    const ids = Object.keys(byTech).sort((a, b) => sum(byTech[b]) - sum(byTech[a]));
    if (!ids.length) { $("chartTech").innerHTML = `<div class="empty" style="padding:30px">No tech stack configured</div>`; return; }
    const W = 460, rowH = 30, labelW = 128, valW = 44, H = ids.length * rowH + 4;
    const max = niceMax(Math.max(1, ...ids.map((t) => sum(byTech[t]))));
    let s = svgEl(W, H);
    ids.forEach((t, i) => {
      const y = i * rowH + 4;
      let x = labelW;
      const active = !S.tech || S.tech === t;
      s += `<g data-tip="${esc(t)}" style="cursor:pointer;opacity:${active ? 1 : 0.35}"><rect class="hit" x="0" y="${y - 3}" width="${W}" height="${rowH}"></rect>
        <text x="0" y="${y + 14}" class="label-strong">${esc(trunc(S.techName[t] || t, 17))}</text>`;
      const segs = SEVS.filter((sv) => byTech[t][sv]);
      segs.forEach((sv, j) => {
        const w = ((W - labelW - valW) * byTech[t][sv]) / max;
        const gap = j < segs.length - 1 ? 2 : 0; // 2px surface gap between stacked segments
        const last = j === segs.length - 1;
        s += last ? `<path d="${barPath(x, y + 2, Math.max(w, 2), 16, true)}" fill="${sevColor(sv)}"></path>`
                  : `<rect x="${x}" y="${y + 2}" width="${Math.max(w - gap, 1)}" height="16" fill="${sevColor(sv)}"></rect>`;
        x += w;
      });
      s += `<text x="${x + 8}" y="${y + 14}" class="label-strong">${sum(byTech[t])}</text></g>`;
    });
    $("chartTech").innerHTML = s + "</svg>" + stackedLegend(present);
    bindTips($("chartTech"), (t) => `<div class="t-title">${esc(S.techName[t] || t)}</div>` +
      SEVS.filter((sv) => byTech[t][sv]).map((sv) => `<div class="t-row"><span><i class="dot" style="--c:${sevColor(sv)}"></i> ${SEV_LABEL[sv]}</span><b>${byTech[t][sv]}</b></div>`).join("") +
      `<div class="t-row" style="border-top:1px solid var(--border);margin-top:4px;padding-top:4px">Total <b>${sum(byTech[t])}</b></div>`,
    (t) => { S.tech = S.tech === t ? "" : t; S.page = 0; syncControls(); render(); });
  }

  function chartTrend(rows) {
    const weeks = 12;
    const start = startOfWeek(new Date(Date.now() - (weeks - 1) * 7 * 86400000));
    const buckets = Array.from({ length: weeks }, (_, i) => ({ d: new Date(start.getTime() + i * 7 * 86400000), c: Object.fromEntries(SEVS.map((s) => [s, 0])) }));
    const present = new Set();
    rows.forEach((v) => {
      if (!v.published) return;
      const i = Math.floor((new Date(v.published) - start) / (7 * 86400000));
      if (i >= 0 && i < weeks) { buckets[i].c[sevKey(v)]++; present.add(sevKey(v)); }
    });
    const W = 560, H = 220, padL = 32, padB = 26, padT = 8, plotW = W - padL, plotH = H - padB - padT;
    const max = niceMax(Math.max(1, ...buckets.map((b) => sum(b.c))));
    const bw = (plotW / weeks) * 0.62, step = plotW / weeks;
    let s = svgEl(W, H);
    for (let i = 0; i <= 4; i++) {
      const y = padT + plotH - (plotH * i) / 4;
      s += `<line class="gridline" x1="${padL}" x2="${W}" y1="${y}" y2="${y}"></line><text x="${padL - 6}" y="${y + 4}" text-anchor="end">${Math.round((max * i) / 4)}</text>`;
    }
    buckets.forEach((b, i) => {
      const x = padL + i * step + (step - bw) / 2;
      let y = padT + plotH;
      s += `<g data-tip="${i}"><rect class="hit" x="${padL + i * step}" y="${padT}" width="${step}" height="${plotH}"></rect>`;
      const segs = [...SEVS].reverse().filter((sv) => b.c[sv]); // most severe on top
      segs.forEach((sv, j) => {
        const h = (plotH * b.c[sv]) / max;
        const top = j === segs.length - 1;
        y -= h;
        s += top ? `<path d="${barPath(x, y, bw, Math.max(h, 2), false)}" fill="${sevColor(sv)}"></path>`
                 : `<rect x="${x}" y="${y + 2}" width="${bw}" height="${Math.max(h - 2, 1)}" fill="${sevColor(sv)}"></rect>`;
      });
      if (i % 2 === (weeks - 1) % 2) s += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${b.d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</text>`;
      s += `</g>`;
    });
    $("chartTrend").innerHTML = s + "</svg>" + stackedLegend(present);
    bindTips($("chartTrend"), (i) => {
      const b = buckets[+i];
      const end = new Date(b.d.getTime() + 6 * 86400000);
      return `<div class="t-title">Week of ${fmtDate(b.d.toISOString())} – ${end.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</div>` +
        SEVS.filter((sv) => b.c[sv]).map((sv) => `<div class="t-row"><span><i class="dot" style="--c:${sevColor(sv)}"></i> ${SEV_LABEL[sv]}</span><b>${b.c[sv]}</b></div>`).join("") +
        `<div class="t-row" style="border-top:1px solid var(--border);margin-top:4px;padding-top:4px">Total <b>${sum(b.c)}</b></div>`;
    });
  }
  const sum = (o) => Object.values(o).reduce((a, b) => a + b, 0);
  const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  function startOfWeek(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; }

  /* ------------------------------------------------------------ table */
  function scoreCell(v) {
    if (v.cvss == null) return `<span style="color:var(--muted)">—</span>`;
    const c = sevColor(v.severity);
    return `<span class="score"><span class="bar"><i style="width:${v.cvss * 10}%;--c:${c}"></i></span><b>${(+v.cvss).toFixed(1)}</b></span>`;
  }
  function epssCell(v) {
    if (!v.epss) return `<span style="color:var(--muted)">—</span>`;
    const pct = v.epss.score * 100;
    return `<span title="Percentile ${(v.epss.percentile * 100).toFixed(0)}">${pct >= 10 ? pct.toFixed(0) : pct.toFixed(pct < 1 ? 2 : 1)}%</span>`;
  }
  function renderTable(rows) {
    const total = rows.length;
    const pages = Math.max(1, Math.ceil(total / S.size));
    S.page = Math.min(S.page, pages - 1);
    const slice = rows.slice(S.page * S.size, (S.page + 1) * S.size);
    if (!total) {
      $("rows").innerHTML = `<tr><td colspan="9"><div class="empty">${S.all.length
        ? `<div class="big">No vulnerabilities match these filters</div>Try widening the date range or resetting filters.`
        : `<div class="big">No data yet</div>Run a scan from the top bar. The first collection looks back over the configured lookback window and can take a few minutes without an NVD API key.`}</div></td></tr>`;
    } else {
      $("rows").innerHTML = slice.map((v) => `
        <tr data-id="${esc(v.id)}" class="${S.selected.has(v.id) ? "selected" : ""}">
          <td onclick="event.stopPropagation()"><input type="checkbox" class="rowSel" ${S.selected.has(v.id) ? "checked" : ""} aria-label="Select ${esc(v.id)}"></td>
          <td><span class="sev ${esc(v.severity)}">${SEV_LABEL[v.severity] || v.severity}</span></td>
          <td class="id">${esc(v.id)}${v.kev ? ` <span class="kev" title="CISA Known Exploited">KEV</span>` : ""}</td>
          <td class="title"><span class="t">${esc(v.title)}</span></td>
          <td>${(v.techs || []).map((t) => `<span class="tag">${esc(S.techName[t] || t)}</span>`).join("")}</td>
          <td class="num">${scoreCell(v)}</td>
          <td class="num">${epssCell(v)}</td>
          <td class="date">${fmtDate(v.published)}</td>
          <td><span class="status ${esc(v.status)}">${STATUS_LABEL[v.status] || v.status}</span></td>
        </tr>`).join("");
    }
    $("pageInfo").textContent = total ? `Showing ${S.page * S.size + 1}–${Math.min(total, (S.page + 1) * S.size)} of ${total.toLocaleString()}` : "0 results";
    $("prevBtn").disabled = S.page === 0;
    $("nextBtn").disabled = S.page >= pages - 1;
    document.querySelectorAll("th[data-sort]").forEach((th) => {
      const on = th.dataset.sort === S.sort.key;
      th.classList.toggle("sorted", on);
      th.querySelector(".arrow").textContent = on ? (S.sort.dir > 0 ? "↑" : "↓") : "↕";
    });
    $("rows").querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.onclick = () => openDrawer(tr.dataset.id);
      const cb = tr.querySelector(".rowSel");
      cb.onchange = () => { cb.checked ? S.selected.add(tr.dataset.id) : S.selected.delete(tr.dataset.id); tr.classList.toggle("selected", cb.checked); updateBulk(); };
    });
    $("selAll").checked = slice.length > 0 && slice.every((v) => S.selected.has(v.id));
    $("selAll").onchange = () => { slice.forEach((v) => ($("selAll").checked ? S.selected.add(v.id) : S.selected.delete(v.id))); renderTable(rows); updateBulk(); };
    updateBulk();
  }
  function updateBulk() {
    $("bulkbar").classList.toggle("show", S.selected.size > 0);
    $("bulkCount").textContent = `${S.selected.size} selected`;
  }

  /* ------------------------------------------------------------ drawer */
  function openDrawer(id) {
    const v = S.all.find((x) => x.id === id);
    if (!v) return;
    $("dBadges").innerHTML = `<span class="sev ${esc(v.severity)}">${SEV_LABEL[v.severity] || v.severity}</span>
      <span class="mono" style="font-weight:600">${esc(v.id)}</span>
      ${(v.aliases || []).map((a) => `<span class="tag mono">${esc(a)}</span>`).join("")}
      ${v.kev ? `<span class="kev">KNOWN EXPLOITED</span>` : ""}`;
    $("dTitle").textContent = v.title;
    const pkgs = v.packages || [];
    $("dBody").innerHTML = `
      ${v.kev ? `<section><div class="alert"><b>Actively exploited in the wild.</b> Added to CISA KEV on ${esc(v.kev.date_added)}${v.kev.due_date ? ` · federal remediation due ${esc(v.kev.due_date)}` : ""}${v.kev.ransomware === "Known" ? " · <b>used in ransomware campaigns</b>" : ""}.<br>${esc(v.kev.action || "")}</div></section>` : ""}
      <section class="facts">
        <div class="fact"><div class="k">CVSS ${esc(v.cvss_version || "")}</div><div class="v">${v.cvss != null ? (+v.cvss).toFixed(1) : "—"}</div></div>
        <div class="fact"><div class="k">EPSS (30-day)</div><div class="v">${v.epss ? (v.epss.score * 100).toFixed(2) + "%" : "—"}</div></div>
        <div class="fact"><div class="k">Tech stack</div><div class="v">${(v.techs || []).map((t) => esc(S.techName[t] || t)).join(", ")}</div></div>
        <div class="fact"><div class="k">Published</div><div class="v">${fmtDate(v.published)}</div></div>
        <div class="fact"><div class="k">Last modified</div><div class="v">${fmtDate(v.modified)}</div></div>
        <div class="fact"><div class="k">First seen here</div><div class="v">${fmtDate(v.first_seen)}</div></div>
      </section>
      <section>
        <h4>Triage</h4>
        <div class="row" style="margin-bottom:8px">
          <select class="select" id="tStatus">${Object.entries(STATUS_LABEL).map(([k, l]) => `<option value="${k}" ${v.status === k ? "selected" : ""}>${l}</option>`).join("")}</select>
          <input class="input" id="tOwner" placeholder="Owner (optional)" value="${esc(v.owner || "")}" style="flex:1">
        </div>
        <textarea class="input" id="tNotes" placeholder="Notes: impact assessment, affected services, ticket link…">${esc(v.notes || "")}</textarea>
        <div class="row" style="margin-top:8px;justify-content:space-between">
          <span style="color:var(--muted);font-size:12px">${v.status_updated ? "Updated " + relTime(v.status_updated) : ""}</span>
          <button class="btn primary" id="tSave">Save triage</button>
        </div>
      </section>
      <section><h4>Description</h4><div class="desc">${esc(v.description || "No description provided.")}</div></section>
      ${v.vector ? `<section><h4>CVSS vector</h4><code>${esc(v.vector)}</code></section>` : ""}
      ${pkgs.length ? `<section><h4>Affected packages</h4><table class="mini-table"><thead><tr><th>Ecosystem</th><th>Package</th><th>Vulnerable</th><th>Fixed in</th></tr></thead><tbody>
        ${pkgs.map((p) => `<tr><td>${esc(p.ecosystem)}</td><td class="mono">${esc(p.name)}</td><td class="mono">${esc(p.vulnerable || "—")}</td><td class="mono" style="color:var(--ok)">${esc(p.patched || "—")}</td></tr>`).join("")}
      </tbody></table></section>` : ""}
      ${(v.affected || []).length ? `<section><h4>Affected products (CPE)</h4><ul class="reflist">${v.affected.map((a) => `<li class="mono">${esc(a)}</li>`).join("")}</ul></section>` : ""}
      ${(v.cwes || []).length ? `<section><h4>Weaknesses</h4>${v.cwes.map((c) => `<a class="tag" target="_blank" rel="noopener" href="https://cwe.mitre.org/data/definitions/${esc(c.replace("CWE-", ""))}.html">${esc(c)}</a>`).join("")}</section>` : ""}
      <section><h4>Sources</h4>${(v.sources || []).map((s) => `<span class="tag">${esc(s)}</span>`).join("")}${v.nvd_status ? `<span class="tag">NVD: ${esc(v.nvd_status)}</span>` : ""}</section>
      <section><h4>References</h4><ul class="reflist">${(v.references || []).filter((r) => /^https?:\/\//.test(r)).map((r) => `<li><a href="${esc(r)}" target="_blank" rel="noopener noreferrer">${esc(r)}</a></li>`).join("")}</ul></section>`;
    $("tSave").onclick = async () => {
      try {
        const r = await api(`/api/vulns/${encodeURIComponent(v.id)}`, { method: "PATCH", body: { status: $("tStatus").value, notes: $("tNotes").value, owner: $("tOwner").value } });
        Object.assign(v, r.vuln);
        toast("Triage saved");
        render();
        openDrawer(v.id);
      } catch (e) { toast("Save failed: " + e.message, true); }
    };
    $("drawer").classList.add("show"); $("drawer").setAttribute("aria-hidden", "false");
    $("scrim").classList.add("show");
  }
  function closeDrawer() { $("drawer").classList.remove("show"); $("drawer").setAttribute("aria-hidden", "true"); $("scrim").classList.remove("show"); }

  /* ------------------------------------------------------------ controls */
  function syncControls() {
    $("q").value = S.q;
    $("techSel").value = S.tech;
    $("statusSel").value = S.status;
    $("kevOnly").checked = S.kev;
    $("rangeSel").value = String(S.range);
    $("pageSize").value = String(S.size);
    $("sevChips").querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", S.sev.has(c.dataset.sev)));
  }
  function resetFilters(doRender = true) {
    Object.assign(S, { q: "", sev: new Set(), tech: "", status: "open", kev: false, newSince: null, page: 0 });
    if (doRender) { syncControls(); render(); }
  }
  function render() {
    persist();
    const base = baseFiltered();
    const rows = sortRows(filtered());
    renderKpis();
    chartSeverity(base);
    chartTech(S.sev.size ? base.filter((v) => S.sev.has(sevKey(v))) : base);
    chartTrend(S.all.filter((v) => (!S.tech || (v.techs || []).includes(S.tech)) && (!S.sev.size || S.sev.has(sevKey(v))) && (!S.kev || v.kev)));
    renderTable(rows);
    S.currentRows = rows;
  }
  function exportCsv() {
    const rows = S.currentRows || [];
    const cols = ["id", "aliases", "severity", "cvss", "epss", "kev", "techs", "title", "published", "status", "owner", "notes", "packages", "url"];
    const q = (x) => `"${String(x ?? "").replace(/"/g, '""')}"`;
    const lines = [cols.join(",")].concat(rows.map((v) => [v.id, (v.aliases || []).join(" "), v.severity, v.cvss ?? "", v.epss ? v.epss.score : "",
      v.kev ? "yes" : "", (v.techs || []).map((t) => S.techName[t] || t).join("; "), v.title, v.published, v.status, v.owner || "", v.notes || "",
      (v.packages || []).map((p) => `${p.ecosystem}:${p.name} ${p.vulnerable || ""} -> ${p.patched || "?"}`).join("; "),
      (v.references || [])[0] || ""].map(q).join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `vulnwatch-${new Date().toISOString().slice(0, 10)}.csv` });
    a.click(); URL.revokeObjectURL(a.href);
  }

  async function load(quiet) {
    try {
      const [data, cfg] = await Promise.all([api("/api/vulns"), api("/api/config")]);
      S.all = data.vulns || [];
      S.techs = cfg.tech_stack || [];
      S.techName = Object.fromEntries(S.techs.map((t) => [t.id, t.name]));
      const cur = S.tech;
      $("techSel").innerHTML = `<option value="">All tech</option>` + S.techs.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}${t.enabled === false ? " (disabled)" : ""}</option>`).join("");
      $("techSel").value = cur;
      $("subtitle").textContent = `Vulnerabilities published worldwide that affect ${S.techs.filter((t) => t.enabled !== false).map((t) => t.name).join(", ")}.`;
      render();
      if (!quiet) syncControls();
    } catch (e) { toast("Failed to load data: " + e.message, true); }
  }

  function init() {
    VW.mountPrefs($("prefs"));
    document.addEventListener("themechange", () => S.all.length && render());
    $("sevChips").innerHTML = SEVS.map((s) => `<button class="chip" data-sev="${s}" aria-pressed="false"><i class="dot" style="--c:${sevColor(s)}"></i>${SEV_LABEL[s]}</button>`).join("");
    $("sevChips").querySelectorAll(".chip").forEach((c) => (c.onclick = () => { S.sev.has(c.dataset.sev) ? S.sev.delete(c.dataset.sev) : S.sev.add(c.dataset.sev); S.page = 0; syncControls(); render(); }));
    let t; $("q").oninput = () => { clearTimeout(t); t = setTimeout(() => { S.q = $("q").value; S.page = 0; render(); }, 150); };
    $("techSel").onchange = () => { S.tech = $("techSel").value; S.page = 0; render(); };
    $("statusSel").onchange = () => { S.status = $("statusSel").value; S.newSince = null; S.page = 0; render(); };
    $("kevOnly").onchange = () => { S.kev = $("kevOnly").checked; S.page = 0; render(); };
    $("rangeSel").onchange = () => { S.range = +$("rangeSel").value; S.page = 0; render(); };
    $("pageSize").onchange = () => { S.size = +$("pageSize").value; S.page = 0; render(); };
    $("prevBtn").onclick = () => { S.page--; renderTable(S.currentRows); };
    $("nextBtn").onclick = () => { S.page++; renderTable(S.currentRows); };
    $("resetBtn").onclick = () => resetFilters();
    $("exportBtn").onclick = exportCsv;
    $("scanBtn").onclick = () => VW.scanNow($("scanBtn"));
    $("dClose").onclick = closeDrawer; $("scrim").onclick = closeDrawer;
    $("bulkClear").onclick = () => { S.selected.clear(); renderTable(S.currentRows); };
    $("bulkApply").onclick = async () => {
      try {
        const ids = [...S.selected];
        await api("/api/vulns", { method: "PATCH", body: { ids, status: $("bulkStatus").value } });
        S.all.forEach((v) => S.selected.has(v.id) && (v.status = $("bulkStatus").value));
        toast(`Updated ${ids.length} vulnerabilities`);
        S.selected.clear(); render();
      } catch (e) { toast("Bulk update failed: " + e.message, true); }
    };
    document.querySelectorAll("th[data-sort]").forEach((th) => (th.onclick = () => {
      const k = th.dataset.sort;
      S.sort = { key: k, dir: S.sort.key === k ? -S.sort.dir : (k === "id" || k === "title" || k === "status" ? 1 : -1) };
      render();
    }));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeDrawer();
      if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") { e.preventDefault(); $("q").focus(); }
    });
    syncControls();
    VW.mountScanPill($("scanPill"), (s) => {
      if (S.lastRun && s.last_run !== S.lastRun && !s.running) { load(true); toast("Scan complete — data refreshed"); }
      S.lastRun = s.last_run;
    });
    load();
  }
  init();
})();
