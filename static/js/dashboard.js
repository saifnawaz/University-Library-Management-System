// Member dashboard (Student and Faculty). Shows what the API says; decides no rules.

import { api } from "./api.js";
import { bookHandlers } from "./actions.js";
import {
  h, boot, startPage, cover, stat, bookTile, dueText, formatMoney, todayLong,
  loadingState, emptyState, errorState,
} from "./ui.js";

const main = document.getElementById("main");
let me = null;

function firstName(name) {
  return name.replace(/^Dr\.?\s+/, "").split(" ")[0];
}

// ---------- pieces ----------

function head() {
  return h("div", { class: "page-head" },
    h("div", {},
      h("p", { class: "eyebrow" }, todayLong()),
      h("h1", {}, `Welcome back, ${firstName(me.name)}.`)),
    h("form", { class: "field quiet", action: "/catalog", method: "get", role: "search",
                style: { flex: "1 1 280px", maxWidth: "360px" } },
      h("label", { for: "dash-search" }, "Search the stacks"),
      h("input", { class: "input", id: "dash-search", type: "search", name: "q",
                   placeholder: "Title, author or subject", autocomplete: "off" })));
}

function notices(reservations) {
  const list = [];
  if (!me.can_borrow) {
    list.push(h("div", { class: "notice warn", role: "status" },
      h("strong", {}, "Borrowing is paused. "), me.borrow_block_reason));
  }
  for (const r of reservations.filter((r) => r.ready)) {
    list.push(h("div", { class: "notice ok" },
      h("strong", {}, "Ready to collect. "),
      `A copy of "${r.item_title}" is being held for you at the desk.`));
  }
  return list;
}

function statStrip(loans, reservations) {
  const overdue = loans.current.filter((l) => l.overdue).length;
  const dueThisWeek = loans.current.filter((l) => !l.overdue && l.days_left <= 7).length;
  const bestPlace = reservations.length ? Math.min(...reservations.map((r) => r.position)) : null;
  return h("div", { class: "stats" },
    stat(h("span", {}, String(loans.current.length), h("small", {}, ` / ${me.borrow_limit}`)),
      "Books borrowed"),
    overdue
      ? stat(String(overdue), "Overdue", "warn")
      : stat(String(dueThisWeek), "Due this week", dueThisWeek ? "warn" : ""),
    stat(formatMoney(me.fines), "Outstanding fines", me.fines > 0 ? "warn" : ""),
    stat(bestPlace ? `#${bestPlace}` : "—", "On the waitlist"));
}

function deskRow(loan) {
  const soon = loan.overdue || loan.days_left <= 3;
  return h("div", { class: "row-card" },
    cover(loan.item_type_key, loan.item_title, { size: "small" }),
    h("div", { class: "grow" },
      h("div", { class: "title" },
        h("a", { href: `/catalog/${encodeURIComponent(loan.item_id)}` }, loan.item_title)),
      h("div", { class: "sub" }, loan.item_author)),
    h("div", { class: "side" },
      h("span", { class: `status ${soon ? "tone-warn" : "tone-muted"}` }, dueText(loan)),
      loan.overdue ? h("span", { class: "muted" }, `${formatMoney(loan.fine)} so far`) : null));
}

function deskSection(loans) {
  return h("section", { class: "section" },
    h("div", { class: "section-head" }, h("h2", {}, "On your desk"), h("a", { href: "/loans" }, "All loans")),
    loans.current.length
      ? h("div", { class: "stack" }, loans.current.map(deskRow))
      : emptyState("Nothing on your desk", "Find something to read in the catalog.",
          h("a", { class: "btn btn-outline", href: "/catalog" }, "Browse the catalog")));
}

/** Until the recommender exists (Phase 8), suggest things this member can borrow now. */
function picksSection(items) {
  const faculty = me.role === "Faculty";
  const pool = items.filter((i) => !i.actions.has_loan && !i.actions.queue_position);
  // Faculty see theses first; then anything the API says they can borrow; then the rest.
  const first = faculty ? pool.filter((i) => i.type === "thesis") : [];
  const rest = pool.filter((i) => !first.includes(i));
  const ordered = [...first, ...rest.filter((i) => i.actions.can_borrow),
                   ...rest.filter((i) => !i.actions.can_borrow)];
  const picks = ordered.slice(0, 3);
  const body = picks.length
    ? h("div", { class: "picks" },
        picks.map((item, i) => bookTile(item, bookHandlers(reload), i, { compact: true })))
    : emptyState("Nothing to suggest yet", "Browse the catalog to find something.");
  return h("section", { class: "section" },
    h("div", { class: "section-head" },
      h("h2", {}, faculty ? "From the research collection" : "Ready to borrow"),
      h("a", { href: faculty ? "/catalog?type=thesis" : "/catalog?available=1" }, "See more")),
    body);
}

function askPanel() {
  return h("section", { class: "dark-panel", id: "ask", "aria-labelledby": "ask-title" },
    h("h2", { id: "ask-title" }, "Ask the librarian"),
    h("form", { class: "row", onsubmit: (e) => e.preventDefault() },
      h("label", { class: "visually-hidden", for: "ask-input" }, "Message"),
      h("input", { class: "input", id: "ask-input", type: "text", disabled: true,
                   placeholder: "Is Deep Learning by Goodfellow available?" }),
      h("button", { class: "btn btn-light", type: "submit", disabled: true }, "Ask")),
    h("p", { class: "muted small" },
      "Coming soon: ask about availability, your loans, fines and what to read next."));
}

// ---------- page ----------

async function load() {
  const [fresh, loans, reservations, items] = await Promise.all([
    api.get("/api/me"),
    api.get("/api/me/loans"),
    api.get("/api/me/reservations"),
    api.get("/api/items"),
  ]);
  me = fresh;
  main.replaceChildren(
    head(),
    ...notices(reservations),
    statStrip(loans, reservations),
    h("div", { class: "columns" }, deskSection(loans), picksSection(items)),
    askPanel());
  if (window.location.hash === "#ask") document.getElementById("ask").scrollIntoView();
}

function reload() {
  load().catch((error) => main.replaceChildren(errorState(error, reload)));
}

boot(main, async () => {
  me = await startPage("member");
  main.replaceChildren(loadingState("rows", 4));
  reload();
});
