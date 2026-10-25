// Members: every account at a glance, filtered in the browser, linking to the desk.

import { api } from "./api.js";
import {
  h, boot, startPage, formatMoney, plural, loadingState, emptyState, errorState,
} from "./ui.js";

const main = document.getElementById("main");
let members = [];
const filter = h("input", { class: "input", id: "member-filter", type: "search",
  placeholder: "Name or ID", autocomplete: "off" });
const tableSlot = h("div");

function render() {
  const q = filter.value.trim().toLowerCase();
  const shown = members.filter((m) => `${m.name} ${m.user_id} ${m.role}`.toLowerCase().includes(q));
  if (!members.length) {
    tableSlot.replaceChildren(emptyState("No members yet", "Member accounts will appear here."));
    return;
  }
  if (!shown.length) {
    tableSlot.replaceChildren(emptyState(`No members match "${filter.value.trim()}"`, "Try part of a name or an ID."));
    return;
  }
  tableSlot.replaceChildren(
    h("p", { class: "result-count" }, plural(shown.length, "member")),
    h("div", { class: "table-wrap" },
      h("table", { class: "table" },
        h("thead", {}, h("tr", {},
          h("th", {}, "Member"), h("th", {}, "Role"), h("th", {}, "On loan"),
          h("th", {}, "Overdue"), h("th", { class: "num" }, "Fines"), h("th", {}, "Borrowing"))),
        h("tbody", {}, shown.map((m) => h("tr", {},
          h("td", {}, h("a", { href: `/staff/desk?member=${encodeURIComponent(m.user_id)}` }, m.name),
            h("div", { class: "muted small" }, m.user_id)),
          h("td", {}, m.role),
          h("td", {}, `${m.active_loans} / ${m.borrow_limit}`),
          h("td", { class: m.overdue_loans ? "late" : "" }, String(m.overdue_loans)),
          h("td", { class: "num" }, m.fines ? formatMoney(m.fines) : "—"),
          h("td", { class: m.can_borrow ? "tone-good" : "tone-warn" },
            m.can_borrow ? "Can borrow" : "Paused")))))));
}

async function load() {
  tableSlot.replaceChildren(loadingState("lines", 6));
  try {
    members = await api.get("/api/members");
    render();
  } catch (error) {
    tableSlot.replaceChildren(errorState(error, load));
  }
}

boot(main, async () => {
  await startPage("staff");
  filter.addEventListener("input", render);
  main.replaceChildren(
    h("div", { class: "page-head" },
      h("div", {}, h("p", { class: "eyebrow" }, "Accounts"), h("h1", {}, "Members")),
      h("div", { class: "field quiet", style: { flex: "0 1 320px" } },
        h("label", { for: "member-filter" }, "Filter"), filter)),
    tableSlot);
  load();
});
