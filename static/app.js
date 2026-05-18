"use strict";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const INTEREST_LEVELS = ["", "Rush the Hall", "Likely to Buy", "Check it Out", "Not Interested"];
const INTEREST_ORDER  = { "Rush the Hall": 1, "Likely to Buy": 2, "Check it Out": 3, "Not Interested": 4, "": 5 };

// Reset functions for custom multi-select filter dropdowns (called by Clear Filters)
const _filterResetFns = [];

// ---------------------------------------------------------------------------
// Multi-select checkbox dropdown header-filter builder.
// "select" is not a built-in headerFilter type in Tabulator 6, so we build
// the DOM ourselves.  The panel is appended to <body> with position:fixed so
// it clears the table header's overflow boundary.
// ---------------------------------------------------------------------------
function makeMultiSelectFilter(pairs) {
  return (cell, onRendered, success) => {
    const selected = new Set();
    const checkboxes = [];

    const wrap = document.createElement("div");
    wrap.style.cssText = "position:relative;width:100%";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.style.cssText =
      "width:100%;background:#0a1628;color:#ccc;border:1px solid #2a5a8a;" +
      "border-radius:3px;font-size:11px;padding:2px 6px;text-align:left;cursor:pointer";
    btn.textContent = "All ▾";
    wrap.appendChild(btn);

    const panel = document.createElement("div");
    panel.style.cssText =
      "display:none;position:fixed;z-index:10000;background:#1a2545;" +
      "border:1px solid #2a5a8a;border-radius:4px;padding:4px 0;" +
      "min-width:175px;box-shadow:0 4px 14px #0009";
    document.body.appendChild(panel);

    pairs.forEach(([val, label]) => {
      const lbl = document.createElement("label");
      lbl.style.cssText =
        "display:flex;align-items:center;gap:7px;padding:4px 12px;" +
        "cursor:pointer;color:#e0e0e0;font-size:12px;white-space:nowrap";
      lbl.addEventListener("mouseenter", () => lbl.style.background = "#1e3a5f");
      lbl.addEventListener("mouseleave", () => lbl.style.background = "");

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = val;
      cb.addEventListener("change", () => {
        if (cb.checked) selected.add(val);
        else selected.delete(val);
        const arr = [...selected];
        btn.textContent = arr.length === 0 ? "All ▾" : `${arr.length} selected ▾`;
        success(arr.length === 0 ? "" : arr);
      });
      checkboxes.push(cb);

      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(" " + label));
      panel.appendChild(lbl);
    });

    // Open / close
    btn.addEventListener("click", e => {
      e.stopPropagation();
      if (panel.style.display === "none") {
        const r = btn.getBoundingClientRect();
        panel.style.top  = (r.bottom + 2) + "px";
        panel.style.left = r.left + "px";
        panel.style.display = "block";
      } else {
        panel.style.display = "none";
      }
    });
    panel.addEventListener("click", e => e.stopPropagation());
    document.addEventListener("click", () => { panel.style.display = "none"; });

    _filterResetFns.push(() => {
      selected.clear();
      checkboxes.forEach(cb => { cb.checked = false; });
      btn.textContent = "All ▾";
      success("");
    });

    return wrap;
  };
}

// ---------------------------------------------------------------------------
// Toast helper
// ---------------------------------------------------------------------------
function toast(msg, variant = "success") {
  const area = document.getElementById("toast-area");
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${variant} border-0 show mb-2`;
  el.setAttribute("role", "alert");
  el.innerHTML = `<div class="d-flex">
    <div class="toast-body">${msg}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
  </div>`;
  area.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
async function apiGet(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

async function apiPut(path, body) {
  const r = await fetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`PUT ${path} → ${r.status}`);
  return r.json();
}

async function apiPost(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} → ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Rank recomputation
// ---------------------------------------------------------------------------
// After any row move or interest-level change, recompute ranks within each
// interest-level group based on the current table row order.
function recomputeRanks(table) {
  const rows = table.getRows();
  const groups = {};
  rows.forEach(row => {
    const d = row.getData();
    const grp = d.interest_level || "";
    if (!groups[grp]) groups[grp] = [];
    groups[grp].push(row);
  });

  const updates = [];
  Object.entries(groups).forEach(([grp, grpRows]) => {
    grpRows.forEach((row, i) => {
      const newRank = grp ? i + 1 : null;
      if (row.getData().rank !== newRank) {
        row.update({ rank: newRank });
        updates.push({ id: row.getData().id, rank: newRank });
      }
    });
  });

  if (updates.length) {
    apiPost("/api/games/bulk-update", updates).catch(err => toast(err.message, "danger"));
  }
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------
function nameFormatter(cell) {
  const d = cell.getRow().getData();
  return `<a class="game-link" href="https://boardgamegeek.com/boardgame/${d.id}" target="_blank" rel="noopener">${cell.getValue() || ""}</a>`;
}

function rankFormatter(cell) {
  const v = cell.getValue();
  return v != null ? `<span>${v}</span>` : `<span style="color:#444">—</span>`;
}

function bggStatusFormatter(cell) {
  const v = cell.getValue() || "";
  if (!v) return `<span class="bgg-status-empty">—</span>`;
  if (v.includes("Own"))      return `<span class="bgg-status-Own">${v}</span>`;
  if (v.includes("Want"))     return `<span class="bgg-status-Want">${v}</span>`;
  if (v.includes("Wishlist")) return `<span class="bgg-status-Wish">${v}</span>`;
  return `<span>${v}</span>`;
}

function interestFormatter(cell) {
  const v = cell.getValue() || "";
  const colors = {
    "Rush the Hall":  "#e63946",
    "Likely to Buy":  "#f4a261",
    "Check it Out":   "#2a9d8f",
    "Not Interested": "#888",
  };
  const c = colors[v] || "#aaa";
  return v ? `<span style="color:${c};font-weight:600">${v}</span>` : `<span style="color:#444">—</span>`;
}

function rowFormatter(row) {
  const el = row.getElement();
  const interest = row.getData().interest_level || "";
  el.setAttribute("data-interest", interest);
}

// ---------------------------------------------------------------------------
// Save a single cell edit
// ---------------------------------------------------------------------------
function onCellEdited(cell, table) {
  const field = cell.getField();
  const id    = cell.getRow().getData().id;
  const value = cell.getValue();

  // If interest level changed, persist it then recompute ranks for the new group
  if (field === "interest_level") {
    apiPut(`/api/games/${id}`, { interest_level: value })
      .then(() => { toast("Saved", "success"); recomputeRanks(table); })
      .catch(err => toast(err.message, "danger"));
    return;
  }

  // If rank manually edited, resequence the whole group to keep ranks unique
  if (field === "rank") {
    const interestLevel = cell.getRow().getData().interest_level || "";
    if (!interestLevel) {
      apiPut(`/api/games/${id}`, { rank: value }).catch(err => toast(err.message, "danger"));
      return;
    }
    const target = parseInt(value) || 1;
    const groupRows = table.getRows()
      .filter(r => (r.getData().interest_level || "") === interestLevel)
      .sort((a, b) => {
        const aR = a.getData().id === id ? target : (a.getData().rank ?? 9999);
        const bR = b.getData().id === id ? target : (b.getData().rank ?? 9999);
        if (aR !== bR) return aR - bR;
        return a.getData().id === id ? -1 : 1; // edited row wins ties
      });
    const updates = groupRows.map((row, i) => {
      const rid = row.getData().id;
      row.update({ rank: i + 1 });
      return { id: rid, rank: i + 1 };
    });
    apiPost("/api/games/bulk-update", updates).catch(err => toast(err.message, "danger"));
    return;
  }

  apiPut(`/api/games/${id}`, { [field]: value })
    .then(() => toast(`Saved`, "success"))
    .catch(err => toast(err.message, "danger"));
}

// ---------------------------------------------------------------------------
// Build the table
// ---------------------------------------------------------------------------
function buildTable(games) {
  const table = new Tabulator("#game-table", {
    data: games,
    height: "calc(100vh - 72px)",
    layout: "fitColumns",
    movableRows: true,

    // Default sort: interest level order, then rank
    initialSort: [
      { column: "interest_sort", dir: "asc" },
      { column: "rank",          dir: "asc" },
    ],

    rowFormatter,

    columns: [
      // Drag handle
      { rowHandle: true, formatter: "handle", headerSort: false, frozen: true, width: 30, minWidth: 30 },

      // Rank
      {
        title: "Rank", field: "rank", width: 60, minWidth: 50,
        formatter: rankFormatter,
        editor: "number", editorParams: { min: 1, step: 1 },
        headerFilter: false,
        sorter: (a, b) => (a ?? 9999) - (b ?? 9999),
      },

      // Name (link to BGG)
      {
        title: "Name", field: "name", minWidth: 200,
        formatter: nameFormatter,
        headerFilter: "input",
        sorter: "string",
      },

      // Year
      {
        title: "Year", field: "year", width: 65, minWidth: 55,
        headerFilter: "input",
        sorter: "number",
      },

      // GenCon Publisher
      {
        title: "Publisher", field: "gencon_publisher", minWidth: 150,
        headerFilter: "input",
        sorter: "string",
      },

      // Booth
      {
        title: "Booth", field: "booth", width: 100, minWidth: 80,
        headerFilter: "input",
        sorter: "string",
      },

      // BGG Status (from collection)
      {
        title: "BGG Status", field: "bgg_status", width: 155, minWidth: 120,
        formatter: bggStatusFormatter,
        headerFilter: makeMultiSelectFilter([
          ["Own",              "Own"],
          ["Preordered",       "Preordered"],
          ["Want to Buy",      "Want to Buy"],
          ["Wishlist",         "Wishlist"],
          ["Want to Play",     "Want to Play"],
          ["For Trade",        "For Trade"],
          ["Previously Owned", "Previously Owned"],
        ]),
        // Statuses can be combined ("Own, Want to Play") — match any selected token
        headerFilterFunc: (headerValue, rowValue) => {
          const vals = Array.isArray(headerValue) ? headerValue : (headerValue ? [headerValue] : []);
          if (!vals.length) return true;
          const v = rowValue != null ? String(rowValue) : "";
          return vals.some(hv => v.split(", ").some(token => token === hv));
        },
        headerFilterEmptyCheck: v => !v || (Array.isArray(v) && !v.length),
        sorter: "string",
      },

      // Interest Level (editable dropdown — custom popup, bypasses cellEdited)
      {
        title: "Interest Level", field: "interest_level", width: 160, minWidth: 130,
        formatter: interestFormatter,
        cellClick: (e, cell) => {
          document.querySelectorAll(".__il-popup").forEach(p => p.remove());
          const r = cell.getElement().getBoundingClientRect();
          const pop = document.createElement("div");
          pop.className = "__il-popup";
          pop.style.cssText =
            `position:fixed;top:${r.bottom + 1}px;left:${r.left}px;z-index:10000;` +
            "background:#1a2545;border:1px solid #2a5a8a;border-radius:4px;" +
            "min-width:170px;padding:4px 0;box-shadow:0 4px 14px #0009";
          document.body.appendChild(pop);
          const cur = cell.getValue() || "";
          [["", "— none —"], ["Rush the Hall", "Rush the Hall"], ["Likely to Buy", "Likely to Buy"],
           ["Check it Out", "Check it Out"], ["Not Interested", "Not Interested"]].forEach(([val, label]) => {
            const item = document.createElement("div");
            item.style.cssText =
              "padding:6px 14px;cursor:pointer;color:#e0e0e0;font-size:13px;white-space:nowrap";
            if (val === cur) { item.style.background = "#1e3a5f"; item.style.fontWeight = "bold"; }
            item.textContent = label;
            item.addEventListener("mouseenter", () => { item.style.background = "#1e3a5f"; });
            item.addEventListener("mouseleave", () => { item.style.background = val === cur ? "#1e3a5f" : ""; });
            item.addEventListener("mousedown", ev => {
              ev.preventDefault(); ev.stopPropagation();
              pop.remove();
              if (val === cur) return;
              const id = cell.getRow().getData().id;
              cell.getRow().update({ interest_level: val });
              rowFormatter(cell.getRow());
              apiPut(`/api/games/${id}`, { interest_level: val })
                .then(() => { toast("Saved", "success"); recomputeRanks(table); })
                .catch(err => toast(err.message, "danger"));
            });
            pop.appendChild(item);
          });
          pop.addEventListener("click", ev => ev.stopPropagation());
          setTimeout(() => {
            document.addEventListener("click", () => pop.remove(), { once: true });
          }, 10);
        },
        headerFilter: makeMultiSelectFilter([
          ["Rush the Hall",  "Rush the Hall"],
          ["Likely to Buy",  "Likely to Buy"],
          ["Check it Out",   "Check it Out"],
          ["Not Interested", "Not Interested"],
        ]),
        headerFilterFunc: (headerValue, rowValue) => {
          const vals = Array.isArray(headerValue) ? headerValue : (headerValue ? [headerValue] : []);
          if (!vals.length) return true;
          return vals.includes(rowValue || "");
        },
        headerFilterEmptyCheck: v => !v || (Array.isArray(v) && !v.length),
        sorter: (a, b) => (INTEREST_ORDER[a] ?? 5) - (INTEREST_ORDER[b] ?? 5),
      },

      // Hot Games Room checkbox (direct toggle, bypasses cellEdited)
      {
        title: "Hot 🎲", field: "hot_games_room", width: 75, minWidth: 65,
        formatter: "tickCross",
        formatterParams: { crossElement: "✗", tickElement: "🔥" },
        headerFilter: "tickCross",
        headerFilterParams: { tristate: true },
        headerFilterEmptyCheck: v => v === null,
        sorter: "boolean",
        cellClick: (e, cell) => {
          const newVal = !cell.getValue();
          const id = cell.getRow().getData().id;
          cell.getRow().update({ hot_games_room: newVal });
          apiPut(`/api/games/${id}`, { hot_games_room: newVal })
            .then(() => toast("Saved", "success"))
            .catch(err => toast(err.message, "danger"));
        },
      },

      // Hidden sort-key column for interest level ordering
      {
        field: "interest_sort", visible: false,
        mutator: (value, data) => INTEREST_ORDER[data.interest_level] ?? 5,
        sorter: "number",
      },
    ],

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------
    rowMoved: row => recomputeRanks(table),

    cellEdited: cell => onCellEdited(cell, table),
  });

  return table;
}

// ---------------------------------------------------------------------------
// Meta / refresh display
// ---------------------------------------------------------------------------
async function loadMeta() {
  try {
    const m = await apiGet("/api/meta");
    const el = document.getElementById("meta-info");
    const refresh = m.last_bgg_refresh ? `BGG: ${m.last_bgg_refresh}` : "BGG: not synced";
    el.textContent = `${m.total} games · ${refresh}`;
  } catch (_) {}
}

// ---------------------------------------------------------------------------
// Bootstrap the app
// ---------------------------------------------------------------------------
async function init() {
  let games;
  try {
    games = await apiGet("/api/games");
  } catch (err) {
    document.getElementById("game-table").innerHTML =
      `<div class="alert alert-danger m-3">Failed to load games: ${err.message}</div>`;
    return;
  }

  const table = buildTable(games);
  loadMeta();

  // ---- Refresh BGG button ----
  document.getElementById("btn-refresh-bgg").addEventListener("click", async () => {
    const btn = document.getElementById("btn-refresh-bgg");
    btn.disabled = true;
    btn.textContent = "Refreshing…";
    try {
      const res = await apiGet("/api/bgg/refresh");
      toast(`BGG refreshed — ${res.updated} statuses updated`, "success");
      // Reload data into table
      const newGames = await apiGet("/api/games");
      table.setData(newGames);
      loadMeta();
    } catch (err) {
      toast(`BGG refresh failed: ${err.message}`, "danger");
    } finally {
      btn.disabled = false;
      btn.textContent = "↻ Refresh BGG Status";
    }
  });

  // ---- Export button ----
  document.getElementById("btn-export").addEventListener("click", () => {
    window.location.href = "/api/export";
  });

  // ---- Import file input ----
  document.getElementById("import-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/import", { method: "POST", body: fd });
      const res = await r.json();
      if (!r.ok) throw new Error(res.detail || r.status);
      toast(`Imported — ${res.merged} games merged`, "success");
      const newGames = await apiGet("/api/games");
      table.setData(newGames);
      loadMeta();
    } catch (err) {
      toast(`Import failed: ${err.message}`, "danger");
    }
    e.target.value = "";
  });

  // ---- Clear Filters button ----
  document.getElementById("btn-clear-filters").addEventListener("click", () => {
    table.clearHeaderFilter();
    _filterResetFns.forEach(fn => fn());
  });
}

document.addEventListener("DOMContentLoaded", init);
