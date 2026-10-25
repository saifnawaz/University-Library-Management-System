// My loans: what's out, what's late, fines (with payment), the member's rules, and history.

import { api } from "./api.js";
import {
  h, boot, startPage, cover, stat, dueText, busy, toast, toastError,
  formatDate, formatMoney, plural, loadingState, emptyState, errorState,
} from "./ui.js";

const main = document.getElementById("main");

function loanRow(loan) {
  const soon = loan.overdue || loan.days_left <= 3;
  return h("div", { class: "row-card" },
    cover(loan.item_type_key, loan.item_title, { size: "small" }),
    h("div", { class: "grow" },
      h("div", { class: "title" },
        h("a", { href: `/catalog/${encodeURIComponent(loan.item_id)}` }, loan.item_title)),
      h("div", { class: "sub" },
        `${loan.item_author} · borrowed ${formatDate(loan.issue_date)} · due ${formatDate(loan.due_date)}`)),
    h("div", { class: "side" },
      h("span", { class: `status ${soon ? "tone-warn" : "tone-muted"}` }, dueText(loan)),
      loan.overdue ? h("span", { class: "muted" }, `${formatMoney(loan.fine)} so far`) : null));
}

function finesPanel(me, loans) {
  const panel = h("section", { class: "panel", "aria-labelledby": "fines-title" },
    h("h2", { id: "fines-title" }, "Fines"),
    h("div", {},
      h("div", { class: `stat-value ${me.fines > 0 ? "tone-warn" : ""}` }, formatMoney(me.fines)),
      h("div", { class: "stat-label" }, `Outstanding · ${loans.fine_policy}`)));

  if (me.fines <= 0) {
    panel.append(h("p", { class: "muted" }, "Nothing to pay. Thank you for returning things on time."));
    return panel;
  }

  const amount = h("input", { class: "input", id: "pay-amount", type: "number", min: "1",
    step: "any", value: String(me.fines), inputmode: "decimal" });
  const pay = h("button", { class: "btn btn-primary", type: "submit" }, "Pay fine");
  const form = h("form", { class: "row", novalidate: true },
    h("div", { class: "field", style: { flex: "1 1 160px" } },
      h("label", { for: "pay-amount" }, "Amount (Rs)"), amount),
    h("div", { style: { alignSelf: "flex-end" } }, pay));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const restore = busy(pay, "Paying…");
    try {
      const updated = await api.post("/api/fines/pay", { amount: amount.value });
      toast(`Paid ${formatMoney(Number(amount.value))}`,
        updated.fines > 0 ? `${formatMoney(updated.fines)} still outstanding.` : "Your fines are cleared.");
      load();
    } catch (error) {
      restore();
      toastError(error, "Couldn't take the payment");
    }
  });
  panel.append(form);
  return panel;
}

function rulesSection(me) {
  const item = (title, text) => h("div", { class: "row-card" },
    h("div", { class: "grow" }, h("div", { class: "title" }, title), h("div", { class: "sub" }, text)));
  return h("section", { class: "section" },
    h("h2", {}, "Your borrowing rules"),
    h("div", { class: "stack" },
      item(`Up to ${plural(me.borrow_limit, "item")} at a time`,
        `Loans last ${me.loan_days} days. Some items, like magazines, have shorter loans.`),
      item("Late returns", me.fine_policy),
      me.has_research_access ? item("Research access", "You can borrow theses from the research collection.") : null));
}

function historyTable(history) {
  if (!history.length) return emptyState("No past loans yet", "Items you return will be listed here.");
  return h("div", { class: "table-wrap" },
    h("table", { class: "table" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Item"), h("th", {}, "Borrowed"), h("th", {}, "Returned"),
        h("th", {}, "Days late"), h("th", { class: "num" }, "Fine"))),
      h("tbody", {}, history.map((loan) => h("tr", {},
        h("td", {}, loan.item_title),
        h("td", {}, formatDate(loan.issue_date)),
        h("td", {}, formatDate(loan.return_date)),
        h("td", { class: loan.days_overdue ? "late" : "" }, loan.days_overdue ? String(loan.days_overdue) : "On time"),
        h("td", { class: "num" }, loan.fine ? formatMoney(loan.fine) : "—"))))));
}

async function load() {
  try {
    const [me, loans] = await Promise.all([api.get("/api/me"), api.get("/api/me/loans")]);
    const overdue = loans.current.filter((l) => l.overdue).length;
    main.replaceChildren(
      h("div", { class: "page-head" },
        h("div", {}, h("p", { class: "eyebrow" }, "My loans"), h("h1", {}, "Loans and fines"))),
      me.can_borrow ? "" : h("div", { class: "notice warn", role: "status" },
        h("strong", {}, "Borrowing is paused. "), me.borrow_block_reason),
      h("div", { class: "stats" },
        stat(h("span", {}, String(loans.current.length), h("small", {}, ` / ${me.borrow_limit}`)), "Books borrowed"),
        stat(String(overdue), "Overdue", overdue ? "warn" : ""),
        stat(formatMoney(me.fines), "Outstanding fines", me.fines > 0 ? "warn" : ""),
        stat(String(loans.history.length), "Returned so far")),
      h("div", { class: "columns" },
        h("section", { class: "section" },
          h("h2", {}, "On your desk"),
          loans.current.length
            ? h("div", { class: "stack" }, loans.current.map(loanRow))
            : emptyState("Nothing on loan", "Find something to read in the catalog.",
                h("a", { class: "btn btn-outline", href: "/catalog" }, "Browse the catalog"))),
        h("div", { class: "section" }, finesPanel(me, loans), rulesSection(me))),
      h("section", { class: "section" }, h("h2", {}, "History"), historyTable(loans.history)));
  } catch (error) {
    main.replaceChildren(errorState(error, load));
  }
}

boot(main, async () => {
  await startPage("member");
  main.replaceChildren(loadingState("rows", 4));
  load();
});
