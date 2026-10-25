// Issue & return: look up a member, then issue, return, record fine payments and
// manage their reservations. Every rule check happens in Python; this page shows the answers.

import { api, ApiError } from "./api.js";
import {
  h, boot, startPage, stat, busy, toast, toastError, dueText, formatDate, formatMoney, plural,
  loadingState, emptyState, errorState,
} from "./ui.js";

const main = document.getElementById("main");
const enc = encodeURIComponent;
let memberId = new URLSearchParams(window.location.search).get("member") || "";
const memberSlot = h("div", { class: "section", style: { gap: "var(--space-6)" } });

function lookupForm() {
  const input = h("input", { class: "input input-bright", id: "lookup", value: memberId,
    placeholder: "Scan or type a member ID", autocomplete: "off", autocapitalize: "none" });
  const form = h("form", { class: "row", role: "search", style: { alignItems: "flex-end" } },
    h("div", { class: "field", style: { flex: "1 1 260px" } }, h("label", { for: "lookup" }, "Member ID"), input),
    h("button", { class: "btn btn-primary", type: "submit" }, "Look up"));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    memberId = input.value.trim();
    history.replaceState(null, "", memberId ? `/staff/desk?member=${enc(memberId)}` : "/staff/desk");
    loadMember();
  });
  return form;
}

// ---------- the member's account ----------

function issueBox(member) {
  const item = h("input", { class: "input input-bright", id: "issue-item", placeholder: "Scan or type",
    autocomplete: "off", autocapitalize: "none" });
  const button = h("button", { class: "btn btn-primary", type: "submit" }, "Issue");
  const form = h("form", { class: "panel", novalidate: true },
    h("h2", {}, `Issue to ${member.name}`),
    h("div", { class: "row", style: { alignItems: "flex-end" } },
      h("div", { class: "field", style: { flex: "1 1 200px" } }, h("label", { for: "issue-item" }, "Item ID"), item),
      button));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!item.value.trim()) { item.focus(); return; } // convenience only
    const restore = busy(button, "Issuing…");
    try {
      const loan = await api.post("/api/loans", { member_id: member.user_id, item_id: item.value.trim() });
      toast("Issued", `"${loan.item_title}" to ${loan.member_name}, due ${formatDate(loan.due_date)}.`);
      loadMember();
    } catch (error) {
      restore();
      toastError(error, "Couldn't issue this");
    }
  });
  return form;
}

function loansTable(member, loans) {
  if (!loans.current.length) return emptyState("Nothing on loan", `${member.name} has no items out.`);
  return h("div", { class: "table-wrap" },
    h("table", { class: "table" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Item"), h("th", {}, "Due"), h("th", {}, "Status"),
        h("th", { class: "num" }, "Fine so far"), h("th", { class: "actions" }, h("span", { class: "visually-hidden" }, "Actions")))),
      h("tbody", {}, loans.current.map((loan) => {
        const button = h("button", { class: "btn btn-quiet btn-small", type: "button" }, "Return");
        button.addEventListener("click", async () => {
          const restore = busy(button, "Returning…");
          try {
            const done = await api.post("/api/loans/return", { member_id: member.user_id, item_id: loan.item_id });
            toast("Returned", done.fine
              ? `"${done.item_title}". Fine added: ${formatMoney(done.fine)}.`
              : `"${done.item_title}", on time.`);
            loadMember();
          } catch (error) {
            restore();
            toastError(error, "Couldn't return this");
          }
        });
        return h("tr", {},
          h("td", {}, loan.item_title, h("div", { class: "muted small" }, loan.item_id)),
          h("td", { class: "nowrap" }, formatDate(loan.due_date)),
          h("td", { class: loan.overdue ? "late nowrap" : "nowrap" }, dueText(loan)),
          h("td", { class: "num" }, loan.fine ? formatMoney(loan.fine) : "—"),
          h("td", { class: "actions" }, button));
      }))));
}

function finePanel(member) {
  const panel = h("section", { class: "panel" },
    h("h2", {}, "Fines"),
    h("div", {},
      h("div", { class: `stat-value ${member.fines > 0 ? "tone-warn" : ""}` }, formatMoney(member.fines)),
      h("div", { class: "stat-label" }, member.fine_policy)));
  if (member.fines <= 0) {
    panel.append(h("p", { class: "muted" }, "No fines outstanding."));
    return panel;
  }
  const amount = h("input", { class: "input input-bright", id: "fine-amount", type: "number",
    min: "1", step: "any", value: String(member.fines) });
  const button = h("button", { class: "btn btn-primary", type: "submit" }, "Record payment");
  const form = h("form", { class: "row", novalidate: true, style: { alignItems: "flex-end" } },
    h("div", { class: "field", style: { flex: "1 1 140px" } }, h("label", { for: "fine-amount" }, "Amount (Rs)"), amount),
    button);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const restore = busy(button, "Saving…");
    try {
      const updated = await api.post("/api/fines/pay", { member_id: member.user_id, amount: amount.value });
      toast("Payment recorded", updated.fines > 0
        ? `${formatMoney(updated.fines)} still outstanding.` : `${member.name}'s fines are cleared.`);
      loadMember();
    } catch (error) {
      restore();
      toastError(error, "Couldn't record the payment");
    }
  });
  panel.append(form);
  return panel;
}

function reservationsSection(member, reservations) {
  const body = !reservations.length
    ? emptyState("No reservations", `${member.name} is not waiting for anything.`)
    : h("div", { class: "stack" }, reservations.map((r) => {
        const cancel = h("button", { class: "btn btn-quiet btn-small", type: "button" }, "Cancel");
        cancel.addEventListener("click", async () => {
          const restore = busy(cancel, "Cancelling…");
          try {
            await api.del(`/api/reservations/${enc(r.item_id)}?member_id=${enc(member.user_id)}`);
            toast("Reservation cancelled", `"${r.item_title}" for ${member.name}.`);
            loadMember();
          } catch (error) {
            restore();
            toastError(error, "Couldn't cancel this");
          }
        });
        return h("div", { class: "row-card" },
          h("div", { class: "grow" },
            h("div", { class: "title" }, r.item_title),
            h("div", { class: "sub" }, `${r.item_id} · reserved ${formatDate(r.created_at)}`)),
          h("div", { class: "side" },
            h("span", { class: `status ${r.ready ? "tone-good" : "tone-muted"}` },
              r.ready ? "Copy held at the desk" : `Number ${r.position} in line`),
            cancel));
      }));
  return h("section", { class: "section" }, h("h2", {}, "Reservations"), body);
}

async function loadMember() {
  if (!memberId) {
    memberSlot.replaceChildren(emptyState("Look up a member to begin",
      "Scan their library card or type their ID. You'll see their loans, fines and reservations here."));
    return;
  }
  memberSlot.replaceChildren(loadingState("rows", 3));
  try {
    const [member, loans, reservations] = await Promise.all([
      api.get(`/api/members/${enc(memberId)}`),
      api.get(`/api/members/${enc(memberId)}/loans`),
      api.get(`/api/members/${enc(memberId)}/reservations`),
    ]);
    memberSlot.replaceChildren(
      h("div", { class: "section-head" },
        h("h2", { class: "serif", style: { fontSize: "var(--text-2xl)", fontWeight: "400" } }, member.name),
        h("span", { class: "muted" }, `${member.role} · ${member.user_id}`)),
      member.can_borrow
        ? h("div", { class: "notice ok" }, h("strong", {}, "Can borrow. "),
            `${plural(member.loans_remaining, "more item")} allowed right now.`)
        : h("div", { class: "notice warn" }, h("strong", {}, "Borrowing is paused. "), member.borrow_block_reason),
      h("div", { class: "stats" },
        stat(h("span", {}, String(member.active_loans), h("small", {}, ` / ${member.borrow_limit}`)), "On loan"),
        stat(String(member.overdue_loans), "Overdue", member.overdue_loans ? "warn" : ""),
        stat(formatMoney(member.fines), "Outstanding fines", member.fines > 0 ? "warn" : ""),
        stat(String(reservations.length), "Reservations")),
      h("div", { class: "columns" },
        h("section", { class: "section" }, h("h2", {}, "On loan"), loansTable(member, loans)),
        h("div", { class: "section" }, issueBox(member), finePanel(member))),
      reservationsSection(member, reservations));
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 403)) {
      memberSlot.replaceChildren(emptyState("No member with that ID",
        `Check the ID and try again. ${error.message}`));
    } else {
      memberSlot.replaceChildren(errorState(error, loadMember));
    }
  }
}

boot(main, async () => {
  await startPage("staff");
  main.replaceChildren(
    h("div", { class: "page-head" },
      h("div", {}, h("p", { class: "eyebrow" }, "Front desk"), h("h1", {}, "Issue & return"))),
    lookupForm(),
    memberSlot);
  loadMember();
});
