const STATUS_OPTIONS = ["new", "reviewed", "applied", "rejected", "likely_closed"];
const TIER_CLASS = { A: "tier-a", B: "tier-b", C: "tier-c" };

// null until the first response tells us what's actually in the data —
// mirrors app.py's `tiers = sorted(df["tier"].dropna().unique())` /
// `orgs = sorted(df["org"].unique())`, discovered from the data itself
// rather than hardcoded, then pre-selected like app.py's `default=tiers`.
let knownTiers = null;
let knownOrgs = null;

// Full unfiltered dataset, fetched once (page load / "Refresh from DB").
// All filter-widget changes re-filter this in memory instead of re-fetching
// — live-measured 2026-08-04: server-side processing is ~0.15s, but the
// per-request payload (full description text for every posting) took
// 2-15s to transfer, and the old code re-fetched it on every filter click.
let allPostings = [];

function debounce(fn, delayMs) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}

function currentFilters() {
  const filters = {
    hide_closed: document.getElementById("hide-closed").checked,
    remote_only: document.getElementById("remote-only").checked,
    query: document.getElementById("search-input").value,
  };
  // Omit tier/org entirely until the checkboxes/select exist (bootstrap:
  // first call has no filter UI yet) — an omitted param means "no filter
  // on this axis" server-side, an explicit-but-empty list means "filter to
  // nothing" (see web/api/_logic.py). Once populated, always send the
  // explicit checked/selected set, even if that set is empty.
  if (knownTiers) {
    filters.tier = Array.from(
      document.querySelectorAll("#tier-filter input[type=checkbox]:checked")
    ).map((el) => el.value);
  }
  if (knownOrgs) {
    filters.org = Array.from(document.getElementById("org-filter").selectedOptions).map(
      (o) => o.value
    );
  }
  return filters;
}

class AuthRequiredError extends Error {}

// Always fetches the complete table (hide_closed=false overrides the
// server's default) — filtering happens client-side in applyFilters, so
// this is the only network call any filter interaction needs.
async function fetchAllPostings() {
  const resp = await fetch("/api/postings?hide_closed=false");
  if (resp.status === 401) {
    showLoginOverlay();
    throw new AuthRequiredError();
  }
  if (!resp.ok) throw new Error(`GET /api/postings failed: ${resp.status}`);
  return resp.json();
}

// Mirrors web/api/_logic.py's list_postings filter logic 1:1, operating on
// the already-fetched array instead of a SQL query.
function applyFilters(postings, filters) {
  let result = postings;
  if (filters.tier) result = result.filter((p) => filters.tier.includes(p.tier));
  if (filters.org) result = result.filter((p) => filters.org.includes(p.org));
  if (filters.hide_closed) {
    result = result.filter((p) => !["likely_closed", "rejected"].includes(p.status));
  }
  if (filters.remote_only) {
    result = result.filter((p) => (p.workplace_type || "").toLowerCase() === "remote");
  }
  const query = (filters.query || "").trim().toLowerCase();
  if (query) {
    result = result.filter(
      (p) =>
        (p.title || "").toLowerCase().includes(query) ||
        (p.description || "").toLowerCase().includes(query)
    );
  }
  return result;
}

function populateTierFilter(postings) {
  const tiers = Array.from(new Set(postings.map((p) => p.tier).filter(Boolean))).sort();
  knownTiers = tiers;

  const fieldset = document.getElementById("tier-filter");
  fieldset.querySelectorAll(".tier-check-row").forEach((el) => el.remove());
  tiers.forEach((tier) => {
    const label = document.createElement("label");
    label.className = "tier-check-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = tier;
    input.checked = true;
    input.addEventListener("change", renderFromCache);
    label.appendChild(input);
    label.append(` Tier ${tier}`);
    fieldset.appendChild(label);
  });
}

function populateOrgFilter(postings) {
  const orgs = Array.from(new Set(postings.map((p) => p.org).filter(Boolean))).sort();
  knownOrgs = orgs;

  const select = document.getElementById("org-filter");
  select.innerHTML = "";
  orgs.forEach((org) => {
    const option = document.createElement("option");
    option.value = org;
    option.textContent = org;
    option.selected = true;
    select.appendChild(option);
  });
}

function renderCards(postings) {
  const grid = document.getElementById("card-grid");
  const emptyMessage = document.getElementById("empty-message");
  document.getElementById("vacancy-counter").textContent = `Current vacancies: ${postings.length}`;

  grid.innerHTML = "";
  emptyMessage.hidden = postings.length > 0;
  postings.forEach((p) => grid.appendChild(renderCard(p)));
}

function renderCard(posting) {
  const card = document.createElement("div");
  card.className = "card";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = posting.title;
  card.appendChild(title);

  const org = document.createElement("div");
  org.className = "card-org";
  org.textContent = posting.org;
  card.appendChild(org);

  const chips = document.createElement("div");
  chips.className = "card-chips";
  if (posting.tier) {
    const tierChip = document.createElement("span");
    const cls = TIER_CLASS[String(posting.tier).trim().toUpperCase()] || "";
    tierChip.className = `chip ${cls}`.trim();
    tierChip.textContent = `Tier ${posting.tier}`;
    chips.appendChild(tierChip);
  }
  if (posting.workplace_type) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = posting.workplace_type;
    chips.appendChild(chip);
  }
  if (posting.location) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = posting.location;
    chips.appendChild(chip);
  }
  card.appendChild(chips);

  const link = document.createElement("a");
  link.className = "open-posting";
  link.href = posting.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Open posting ↗";
  card.appendChild(link);

  const select = document.createElement("select");
  select.className = "status-select";
  select.setAttribute("aria-label", "Status");
  STATUS_OPTIONS.forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    option.selected = status === posting.status;
    select.appendChild(option);
  });
  select.addEventListener("change", () => updateStatus(posting, select, select.value));
  card.appendChild(select);

  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Description";
  details.appendChild(summary);
  const desc = document.createElement("p");
  desc.textContent = posting.description || "(no description)";
  details.appendChild(desc);
  card.appendChild(details);

  return card;
}

async function updateStatus(posting, selectEl, newStatus) {
  const previousStatus = posting.status;
  selectEl.disabled = true;
  try {
    const resp = await fetch("/api/status", {
      method: "POST",
      headers: { "Content-type": "application/json" },
      body: JSON.stringify({ source: posting.source, ats_id: posting.ats_id, status: newStatus }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      alert(body.error || `Failed to update status (${resp.status})`);
      selectEl.value = previousStatus; // snap back to the last known-good value
      return;
    }
    // Update in-memory state directly instead of re-fetching: the write
    // already succeeded, and Vercel Blob's read path is CDN-cached with a
    // real propagation delay (live-verified 2026-08-04 — a GET fired
    // immediately after a successful write still returned the pre-write
    // status for close to a minute). Re-fetching here would show the user
    // a stale value right after their own change appeared to do nothing.
    posting.status = newStatus;
  } finally {
    selectEl.disabled = false;
  }
}

// Re-filters the already-fetched dataset and re-renders — no network call.
// Bound to every filter widget's change/input event.
function renderFromCache() {
  renderCards(applyFilters(allPostings, currentFilters()));
}

// The only function that hits the network. Runs on page load and on
// "Refresh from DB" — everything else re-filters the cached result.
async function refresh() {
  allPostings = await fetchAllPostings();
  if (knownTiers === null) populateTierFilter(allPostings);
  if (knownOrgs === null) populateOrgFilter(allPostings);
  renderFromCache();
  hideLoginOverlay();
}

function showLoginOverlay() {
  document.getElementById("app").hidden = true;
  document.getElementById("login-overlay").hidden = false;
}

function hideLoginOverlay() {
  document.getElementById("login-overlay").hidden = true;
  document.getElementById("app").hidden = false;
}

function applyTheme(value) {
  if (value === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", value);
  }
}

function initTheme() {
  const saved = localStorage.getItem("theme") || "system";
  document.getElementById("theme-select").value = saved;
  applyTheme(saved);
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  document.getElementById("theme-select").addEventListener("change", (e) => {
    localStorage.setItem("theme", e.target.value);
    applyTheme(e.target.value);
  });

  document.getElementById("refresh-btn").addEventListener("click", refresh);
  document.getElementById("hide-closed").addEventListener("change", renderFromCache);
  document.getElementById("remote-only").addEventListener("change", renderFromCache);
  document.getElementById("org-filter").addEventListener("change", renderFromCache);
  document.getElementById("search-input").addEventListener("input", debounce(renderFromCache, 300));

  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const password = document.getElementById("login-password").value;
    const errorEl = document.getElementById("login-error");

    const resp = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!resp.ok) {
      errorEl.hidden = false;
      return;
    }
    errorEl.hidden = true;
    refreshOrReportError();
  });

  refreshOrReportError();
});

function refreshOrReportError() {
  refresh().catch((err) => {
    if (err instanceof AuthRequiredError) return; // login overlay already shown
    console.error(err);
    document.getElementById("card-grid").textContent = "Failed to load postings.";
  });
}
