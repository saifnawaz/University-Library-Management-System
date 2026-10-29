// Item detail: everything about one item, and the one action this viewer can take.

import { api, ApiError } from "./api.js";
import { bookHandlers } from "./actions.js";
import {
  h, boot, startPage, cover, bookButton, statusTone, busy, toast, toastError,
  formatDate, plural, loadingState, errorState,
} from "./ui.js";

const main = document.getElementById("main");
const itemId = decodeURIComponent(window.location.pathname.split("/").pop());
let me = null;

const EXTRA_FACTS = [
  ["isbn", "ISBN"], ["supervisor", "Supervisor"], ["issue_number", "Issue"], ["file_format", "Format"],
];

function facts(item) {
  const rows = [["Type", item.item_type], ["Author", item.author], ["Year", String(item.year)]];
  if (item.subject) rows.push(["Subject", item.subject]);
  for (const [key, label] of EXTRA_FACTS) if (item[key]) rows.push([label, item[key]]);
  if (item.total_copies !== null) rows.push(["Copies", String(item.total_copies)]);
  rows.push(["Waiting list", item.waiting ? plural(item.waiting, "person", "people") : "Nobody waiting"]);
  rows.push(["Item ID", item.item_id]);
  return h("dl", { class: "facts" }, rows.flatMap(([dt, dd]) => [h("dt", {}, dt), h("dd", {}, dd)]));
}

/** Member: the same single action as the catalog, plus the full reason in words. */
function memberActions(item, loan) {
  const a = item.actions;
  const parts = [bookButton(item, bookHandlers(load))];
  if (loan) parts.push(h("span", { class: "muted" }, `You have this on loan · due ${formatDate(loan.due_date)}`));
  if (a.held_until) {
    parts.push(h("span", { class: "status tone-good" },
      `Ready to collect until ${formatDate(a.held_until)} · a copy is held for you at the desk`));
  } else if (a.queue_position) {
    parts.push(h("span", { class: "muted" }, `Number ${a.queue_position} in line. We'll let you know when a copy is held for you.`));
  }
  if (!a.can_borrow && a.reason && !a.has_loan && !a.queue_position) {
    parts.push(h("span", { class: "muted" }, a.reason));
  }
  return h("div", { class: "action-row" }, parts);
}

/** Librarian: withdraw (soft delete), with a second click to confirm. */
function staffActions(item) {
  if (item.withdrawn) {
    return h("div", { class: "notice warn" }, "This item has been withdrawn. It is hidden from the catalog; past loans still show it.");
  }
  const button = h("button", { class: "btn btn-quiet", type: "button" }, "Withdraw from catalog");
  const cancel = h("button", { class: "btn btn-quiet", type: "button", hidden: true }, "Keep it");
  let armed = false;
  button.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      button.textContent = "Yes, withdraw it";
      button.className = "btn btn-primary";
      cancel.hidden = false;
      return;
    }
    const restore = busy(button, "Withdrawing…");
    try {
      await api.post(`/api/items/${encodeURIComponent(item.item_id)}/withdraw`);
      toast(`Withdrew "${item.title}"`, "It no longer appears in the catalog.");
      load();
    } catch (error) {
      restore();
      toastError(error, "Couldn't withdraw this");
    }
  });
  cancel.addEventListener("click", () => {
    armed = false;
    button.textContent = "Withdraw from catalog";
    button.className = "btn btn-quiet";
    cancel.hidden = true;
  });
  return h("div", { class: "action-row" }, button, cancel,
    h("span", { class: "muted small" }, "Refused while any copy is on loan. Waiting members are told."));
}

async function load() {
  try {
    const [item, loans] = await Promise.all([
      api.get(`/api/items/${encodeURIComponent(itemId)}`),
      me.can_manage_library ? Promise.resolve(null) : api.get("/api/me/loans"),
    ]);
    const loan = loans && loans.current.find((l) => l.item_id === item.item_id);
    document.title = `${item.title} · The Reading Room`;
    main.replaceChildren(
      h("a", { href: "/catalog", class: "small" }, "← Back to the stacks"),
      h("article", { class: "item-detail" },
        cover(item.type, item.title),
        h("div", { class: "info" },
          h("p", { class: "eyebrow" }, item.item_type),
          h("h1", {}, item.title),
          h("p", { class: "muted" }, `${item.author} · ${item.year}`),
          h("p", { class: `status ${statusTone(item)}` }, item.status_text),
          item.description ? h("p", {}, item.description) : null,
          me.can_manage_library ? staffActions(item) : memberActions(item, loan),
          facts(item))));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      main.replaceChildren(h("div", { class: "state" },
        h("h3", {}, "We couldn't find that item"),
        h("p", {}, "It may have been withdrawn, or the link is wrong."),
        h("a", { class: "btn btn-quiet", href: "/catalog" }, "Back to the stacks")));
    } else {
      main.replaceChildren(errorState(error, load));
    }
  }
}

boot(main, async () => {
  me = await startPage("any");
  main.replaceChildren(loadingState("lines", 6));
  load();
});
