const STATUS_OPTIONS = ["new", "reviewed", "applied", "rejected", "likely_closed"];
const TIER_CLASS = { A: "tier-a", B: "tier-b", C: "tier-c" };
const PAGE_SIZE = 60;

// null until the first response tells us what's actually in the data —
// mirrors app.py's `tiers = sorted(df["tier"].dropna().unique())` /
// `orgs = sorted(df["org"].unique())`, discovered from the data itself
// rather than hardcoded, then pre-selected like app.py's `default=tiers`.
let knownTiers = null;
let knownOrgs = null;

// Pagination state for the currently-loaded filter set — reset to page 1
// whenever a filter changes, advanced by "Load more".
let currentPage = 1;
let currentTotal = 0;
let loadedCount = 0;

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
  // nothing" (see web/api/_repo.py). Once populated, always send the
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

function buildQueryString(filters, page, size) {
  const params = new URLSearchParams();
  if (filters.tier) filters.tier.forEach((t) => params.append("tier", t));
  if (filters.org) filters.org.forEach((o) => params.append("org", o));
  params.set("hide_closed", String(filters.hide_closed));
  params.set("remote_only", String(filters.remote_only));
  if (filters.query) params.set("query", filters.query);
  params.set("page", String(page));
  params.set("size", String(size));
  return params.toString();
}

class AuthRequiredError extends Error {}

async function fetchPostings(filters, page, size) {
  const resp = await fetch(`/api/postings?${buildQueryString(filters, page, size)}`);
  if (resp.status === 401) {
    showLoginOverlay();
    throw new AuthRequiredError();
  }
  if (!resp.ok) throw new Error(`GET /api/postings failed: ${resp.status}`);
  return resp.json();
}

function populateTierFilter(tiers) {
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
    input.addEventListener("change", () => loadPage(1, { append: false }));
    label.appendChild(input);
    label.append(` Tier ${tier}`);
    fieldset.appendChild(label);
  });
}

function populateOrgFilter(orgs) {
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

// One-time fetch of distinct tier/org values to populate the filter
// widgets — a dedicated DISTINCT query (/api/facets), not a large page of
// /api/postings: the latter has an inherent row-count ceiling that
// silently truncates once postings outgrows it (live-caught 2026-08-04 —
// see web/api/_repo.py's get_facets docstring). Runs once per page load /
// "Refresh from DB" click, not per filter interaction.
async function loadFacets() {
  const resp = await fetch("/api/facets");
  if (resp.status === 401) {
    showLoginOverlay();
    throw new AuthRequiredError();
  }
  if (!resp.ok) throw new Error(`GET /api/facets failed: ${resp.status}`);
  const { tiers, orgs } = await resp.json();
  populateTierFilter(tiers);
  populateOrgFilter(orgs);
}

function updateVacancyCounter() {
  document.getElementById("vacancy-counter").textContent =
    loadedCount < currentTotal
      ? `Showing ${loadedCount} of ${currentTotal} vacancies`
      : `Current vacancies: ${currentTotal}`;
}

function renderCards(postings, { append }) {
  const grid = document.getElementById("card-grid");
  const emptyMessage = document.getElementById("empty-message");

  if (!append) {
    grid.innerHTML = "";
    emptyMessage.hidden = postings.length > 0;
  }
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
    // already succeeded, and Vercel Blob's read path used to be CDN-cached
    // with a real propagation delay under the old storage backend — kept
    // as the safer default now that Postgres is the backend too, since it
    // avoids one extra round trip either way.
    posting.status = newStatus;
  } finally {
    selectEl.disabled = false;
  }
}

// Fetches one page for the current filter set and either replaces the
// grid (append: false — a filter changed, or this is the first load) or
// appends to it ("Load more").
async function loadPage(page, { append }) {
  const filters = currentFilters();
  const { items, total } = await fetchPostings(filters, page, PAGE_SIZE);

  renderCards(items, { append });
  currentPage = page;
  currentTotal = total;
  loadedCount = append ? loadedCount + items.length : items.length;
  updateVacancyCounter();

  const loadMoreBtn = document.getElementById("load-more-btn");
  loadMoreBtn.hidden = loadedCount >= currentTotal;

  hideLoginOverlay();
}

async function refresh() {
  await loadFacets();
  await loadPage(1, { append: false });
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

  document.getElementById("refresh-btn").addEventListener("click", refreshOrReportError);
  document.getElementById("load-more-btn").addEventListener("click", () => loadPage(currentPage + 1, { append: true }));
  document.getElementById("hide-closed").addEventListener("change", () => loadPage(1, { append: false }));
  document.getElementById("remote-only").addEventListener("change", () => loadPage(1, { append: false }));
  document.getElementById("org-filter").addEventListener("change", () => loadPage(1, { append: false }));
  document
    .getElementById("search-input")
    .addEventListener("input", debounce(() => loadPage(1, { append: false }), 300));

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
