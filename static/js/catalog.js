// Catalog: search (on the server), filter what's loaded (in the browser), borrow and reserve.
// Which button each book shows comes from item.actions, decided in Python.

import { api } from "./api.js";
import { bookHandlers } from "./actions.js";
import { itemForm } from "./item-form.js";
import { h, boot, startPage, bookTile, plural, loadingState, emptyState, errorState } from "./ui.js";

const TYPES = [
  ["book", "Books"], ["reference", "Reference books"], ["ebook", "E-books"],
  ["magazine", "Magazines"], ["thesis", "Theses"],
];

const main = document.getElementById("main");
const searchInput = document.getElementById("search");
const typeBox = document.getElementById("type-filters");
const results = document.getElementById("results");
const resultCount = document.getElementById("result-count");
const noticeSlot = document.getElementById("notice-slot");

const params = new URLSearchParams(window.location.search);
const state = {
  me: null,
  items: [],
  query: params.get("q") || "",
  types: new Set(TYPES.some(([k]) => k === params.get("type"))
    ? [params.get("type")] : TYPES.map(([k]) => k)),
  nowOnly: params.get("available") === "1",
};
let requestNumber = 0; // ignore answers to searches the user has already replaced

// ---------- filters ----------

function syncUrl() {
  const next = new URLSearchParams();
  if (state.query) next.set("q", state.query);
  if (state.types.size === 1) next.set("type", [...state.types][0]);
  if (state.nowOnly) next.set("available", "1");
  const qs = next.toString();
  history.replaceState(null, "", qs ? `/catalog?${qs}` : "/catalog");
}

function renderTypeFilters() {
  typeBox.append(...TYPES.map(([key, label]) => {
    const box = h("input", { type: "checkbox", value: key, checked: state.types.has(key) });
    box.addEventListener("change", () => {
      if (box.checked) state.types.add(key); else state.types.delete(key);
      syncUrl();
      renderResults();
    });
    return h("label", { class: "check" }, box, label);
  }));
}

/** "I can borrow now" uses the API's per-member answer; librarians see "on the shelf". */
function availableNow(item) {
  return item.actions ? item.actions.can_borrow : item.available_now;
}

function visibleItems() {
  return state.items.filter((item) =>
    state.types.has(item.type) && (!state.nowOnly || availableNow(item)));
}

// ---------- results ----------

function renderNotice() {
  const me = state.me;
  noticeSlot.replaceChildren(me.can_manage_library || me.can_borrow ? "" :
    h("div", { class: "notice warn", role: "status" },
      h("strong", {}, "Borrowing is paused. "), me.borrow_block_reason));
}

function renderResults() {
  const items = visibleItems();
  resultCount.textContent = state.items.length ? plural(items.length, "result") : "";

  if (state.items.length === 0) {
    results.replaceChildren(state.query
      ? emptyState(`No books found for "${state.query}"`,
          "Try a shorter search, or check the spelling of the title or author.",
          h("button", { class: "btn btn-quiet", type: "button", onclick: clearSearch }, "Clear search"),
          false)
      : emptyState("The catalog is empty", "No items have been added yet.", null, false));
    return;
  }
  if (items.length === 0) {
    results.replaceChildren(emptyState("Nothing matches these filters",
      `${plural(state.items.length, "item")} found, but none with the filters you picked.`,
      h("button", { class: "btn btn-quiet", type: "button", onclick: clearFilters }, "Clear filters"),
      false));
    return;
  }
  const handlers = bookHandlers(refresh);
  results.replaceChildren(h("div", { class: "book-grid" },
    items.map((item, i) => bookTile(item, handlers, i))));
}

async function search({ quiet = false } = {}) {
  const mine = ++requestNumber;
  if (!quiet) {
    resultCount.textContent = "";
    results.replaceChildren(loadingState("covers", 8));
  }
  try {
    const items = await api.get(`/api/items?q=${encodeURIComponent(state.query)}`);
    if (mine !== requestNumber) return; // a newer search has started
    state.items = items;
    renderResults();
  } catch (error) {
    if (mine !== requestNumber) return;
    results.replaceChildren(errorState(error, () => search()));
  }
}

/** After borrowing or reserving: reload the member (for the notice) and the results, in place. */
async function refresh() {
  try {
    state.me = await api.get("/api/me");
    renderNotice();
  } catch { /* the search below shows any error */ }
  search({ quiet: true });
}

function clearSearch() {
  searchInput.value = "";
  state.query = "";
  syncUrl();
  search();
  searchInput.focus();
}

function clearFilters() {
  state.types = new Set(TYPES.map(([k]) => k));
  state.nowOnly = false;
  typeBox.querySelectorAll("input").forEach((box) => { box.checked = true; });
  document.querySelector('input[name="avail"][value="all"]').checked = true;
  syncUrl();
  renderResults();
}

// ---------- librarian: add an item ----------

function setUpStaffTools() {
  const slot = document.getElementById("add-slot");
  const toggle = h("button", { class: "btn btn-primary", type: "button", "aria-expanded": "false" },
    "Add an item");
  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    slot.replaceChildren(open ? "" : itemForm({
      onAdded: () => { slot.replaceChildren(); toggle.setAttribute("aria-expanded", "false"); search(); },
      onCancel: () => { slot.replaceChildren(); toggle.setAttribute("aria-expanded", "false"); },
    }));
  });
  document.getElementById("staff-slot").append(toggle);
  document.getElementById("avail-now-label").textContent = "On the shelf now";
}

// ---------- start ----------

let debounce;
searchInput.addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    state.query = searchInput.value.trim();
    syncUrl();
    search();
  }, 250);
});
document.querySelectorAll('input[name="avail"]').forEach((radio) => {
  radio.checked = (radio.value === "now") === state.nowOnly;
  radio.addEventListener("change", () => {
    state.nowOnly = radio.value === "now" && radio.checked;
    syncUrl();
    renderResults();
  });
});

boot(main, async () => {
  state.me = await startPage("any"); // the catalog is shared by members and librarians
  if (state.me.can_manage_library) setUpStaffTools();
  renderNotice();
  searchInput.value = state.query;
  renderTypeFilters();
  search();
});
