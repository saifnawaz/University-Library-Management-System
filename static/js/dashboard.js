// Member dashboard (Student and Faculty). Shows what the API says; decides no rules.

import { api } from "./api.js";
import { bookHandlers } from "./actions.js";
import {
  h, boot, startPage, cover, stat, bookTile, dueText, formatMoney, todayLong,
  blockedNotice, accruingText, assistantPanel, loadingState, emptyState, errorState,
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
  const ready = reservations.filter((r) => r.ready).map((r) =>
    h("div", { class: "notice ok" },
      h("strong", {}, "Ready to collect. "),
      `A copy of "${r.item_title}" is being held for you at the desk.`));
  const list = [blockedNotice(me), ...ready].filter(Boolean);
  return list.length ? h("div", { class: "notices" }, list) : "";
}

/** Only numbers worth reading: zeros are left out. */
function statStrip(loans, reservations) {
  const overdue = loans.current.filter((l) => l.overdue).length;
  const dueThisWeek = loans.current.filter((l) => !l.overdue && l.days_left <= 7).length;
  const bestPlace = reservations.length ? Math.min(...reservations.map((r) => r.position)) : null;
  const stats = [
    stat(h("span", {}, String(loans.current.length), h("small", {}, ` / ${me.borrow_limit}`)),
      "Books borrowed"),
  ];
  if (overdue) stats.push(stat(String(overdue), "Overdue", "warn"));
  else if (dueThisWeek) stats.push(stat(String(dueThisWeek), "Due this week"));
  if (me.current_fine > 0) stats.push(stat(formatMoney(me.current_fine), "Current fine, payable now", "warn"));
  if (me.total_fine > me.current_fine) stats.push(stat(formatMoney(me.total_fine), "Total fine, with overdue items"));
  if (bestPlace) stats.push(stat(`#${bestPlace}`, "On the waitlist"));
  return h("div", { class: "stats" }, stats);
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
      loan.overdue ? h("span", { class: "muted" }, accruingText(loan)) : null));
}

function deskSection(loans) {
  return h("section", { class: "section" },
    h("div", { class: "section-head" }, h("h2", {}, "On your desk"), h("a", { href: "/loans" }, "All loans")),
    loans.current.length
      ? h("div", { class: "stack" }, loans.current.map(deskRow))
      : emptyState("Nothing on your desk", "Find something to read in the catalog.",
          h("a", { class: "btn btn-outline", href: "/catalog" }, "Browse the catalog")));
}

/**
 * Until the recommender exists (Phase 8), suggest up to three things this member can
 * borrow right now (the API's actions.can_borrow). Faculty see theses first.
 * Returns "" when there is nothing borrowable, e.g. while borrowing is paused.
 */
function picksSection(items) {
  const faculty = me.role === "Faculty";
  const borrowable = items.filter((i) => i.actions.can_borrow);
  const ordered = faculty
    ? [...borrowable.filter((i) => i.type === "thesis"), ...borrowable.filter((i) => i.type !== "thesis")]
    : borrowable;
  const picks = ordered.slice(0, 3);
  if (!picks.length) return "";
  return h("section", { class: "section" },
    h("div", { class: "section-head" },
      h("h2", {}, faculty && picks[0].type === "thesis" ? "From the research collection" : "Ready to borrow"),
      h("a", { href: faculty ? "/catalog?type=thesis" : "/catalog?available=1" }, "See more")),
    h("div", { class: "picks" },
      picks.map((item, i) => bookTile(item, bookHandlers(reload), i, { compact: true }))));
}

function askPanel() {
  return assistantPanel({
    title: "Ask the librarian",
    placeholder: "Is Deep Learning by Goodfellow available?",
    comingSoon: "ask about availability, your loans, fines and what to read next.",
  });
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
    notices(reservations),
    statStrip(loans, reservations),
    h("div", { class: "columns" }, deskSection(loans), picksSection(items) || null),
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
