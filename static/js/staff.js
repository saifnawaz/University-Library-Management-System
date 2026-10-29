// Librarian overview: today's numbers, quick issue/return, overdue loans, most borrowed.

import { api, ApiError } from "./api.js";
import { overdueTable, shelfChart } from "./staff-common.js";
import {
  h, boot, startPage, stat, busy, toast, toastError, formatDate, formatMoney, todayLong,
  loadingState, errorState,
} from "./ui.js";

const main = document.getElementById("main");

function quickDesk(onChange) {
  const member = h("input", { class: "input input-bright", id: "q-member", placeholder: "Scan or type",
    autocomplete: "off", autocapitalize: "none" });
  const item = h("input", { class: "input input-bright", id: "q-item", placeholder: "Scan or type",
    autocomplete: "off", autocapitalize: "none" });
  const result = h("p", { class: "small", role: "status" });
  const issue = h("button", { class: "btn btn-primary", type: "submit", style: { flex: "1 1 140px" } }, "Issue");
  const giveBack = h("button", { class: "btn btn-quiet", type: "button", style: { flex: "1 1 140px" } }, "Return");

  async function run(kind, button) {
    // Convenience check only; the server checks the same thing.
    if (!member.value.trim() || !item.value.trim()) {
      result.className = "small tone-warn";
      result.textContent = "Enter a member ID and an item ID.";
      return;
    }
    const restore = busy(button, kind === "issue" ? "Issuing…" : "Returning…");
    const body = { member_id: member.value.trim(), item_id: item.value.trim() };
    try {
      const loan = await api.post(kind === "issue" ? "/api/loans" : "/api/loans/return", body);
      if (kind === "issue") {
        result.className = "small tone-good";
        result.textContent = `Issued "${loan.item_title}" to ${loan.member_name}, due ${formatDate(loan.due_date)}.`;
        toast("Issued", `"${loan.item_title}" to ${loan.member_name}.`);
      } else {
        result.className = "small tone-good";
        result.textContent = `Returned "${loan.item_title}" from ${loan.member_name}` +
          (loan.fine ? `. ${formatMoney(loan.fine)} added to the current fine.` : ", on time.");
        toast("Returned", `"${loan.item_title}" from ${loan.member_name}.`);
      }
      item.value = "";
      item.focus();
      onChange();
    } catch (error) {
      result.className = "small tone-warn";
      result.textContent = error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
      toastError(error, kind === "issue" ? "Couldn't issue this" : "Couldn't return this");
    } finally {
      restore();
    }
  }

  giveBack.addEventListener("click", () => run("return", giveBack));
  const form = h("form", { class: "panel", novalidate: true, "aria-labelledby": "quick-title" },
    h("h2", { id: "quick-title" }, "Quick issue"),
    h("div", { class: "field" }, h("label", { for: "q-member" }, "Member ID"), member),
    h("div", { class: "field" }, h("label", { for: "q-item" }, "Item ID"), item),
    h("div", { class: "row" }, issue, giveBack),
    result);
  form.addEventListener("submit", (event) => { event.preventDefault(); run("issue", issue); });
  return form;
}

let deskPanel = null; // kept between refreshes so typed IDs are not lost

async function load() {
  try {
    const [stats, overdue] = await Promise.all([
      api.get("/api/reports/stats"),
      api.get("/api/reports/overdue"),
    ]);
    deskPanel = deskPanel || quickDesk(load);
    main.replaceChildren(
      h("div", { class: "page-head" },
        h("div", {}, h("p", { class: "eyebrow" }, todayLong()), h("h1", {}, "Today at the desk"))),
      h("div", { class: "stats" },
        stat(String(stats.active_loans), "Items on loan"),
        stat(String(stats.overdue_loans), "Overdue", stats.overdue_loans ? "warn" : ""),
        stat(formatMoney(stats.current_fines), "Current fines, payable now"),
        stat(formatMoney(stats.total_fines), "Total fines, with overdue items"),
        stat(String(stats.reservations), "Reservations waiting")),
      h("div", { class: "columns" },
        deskPanel,
        h("section", { class: "section" },
          h("div", { class: "section-head" }, h("h2", {}, "Overdue"), h("a", { href: "/staff/reports" }, "See all")),
          overdueTable(overdue, { limit: 5 }))),
      h("section", { class: "section" },
        h("h2", {}, `Most borrowed, last ${stats.recent_days} days`),
        shelfChart(stats.most_borrowed_recent.slice(0, 4))));
  } catch (error) {
    main.replaceChildren(errorState(error, load));
  }
}

boot(main, async () => {
  await startPage("staff");
  main.replaceChildren(loadingState("rows", 3));
  load();
});
