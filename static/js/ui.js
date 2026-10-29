// Shared UI helpers: building elements, navigation, toasts, page states, theme.
// No library rules here: only rendering what the API returns.

import { api, ApiError } from "./api.js";

// ---------- building elements safely ----------

/**
 * Create an element. Text is always set with textContent, so data from the
 * API can never inject HTML.
 *   h("p", { class: "muted" }, "Hello", h("strong", {}, "there"))
 */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style" && typeof value === "object") {
      for (const [prop, v] of Object.entries(value)) {
        // CSS variables ("--bar-height") only work through setProperty.
        if (prop.startsWith("--")) el.style.setProperty(prop, v);
        else el.style[prop] = v;
      }
    }
    else if (key.startsWith("on")) el.addEventListener(key.slice(2).toLowerCase(), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  if (tag === "table") labelledTable(el); // header labels for the phone layout
  return el;
}

/** Make an SVG icon from a list of path strings (24x24 grid, stroked). */
export function icon(paths) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  for (const d of paths) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

const ICONS = {
  moon: ["M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"],
  sun: ["M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z",
        "M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"],
};

// ---------- formatting ----------

const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const longDay = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });

/** Read "2026-11-04" as a local date, so it never shifts by a day. */
function parseDate(iso) {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** "2026-11-04" -> "4 Nov 2026" */
export function formatDate(iso) {
  return iso ? shortDate.format(parseDate(iso)) : "";
}

/** Today as "Sunday, 25 October" */
export function todayLong() {
  return longDay.format(new Date());
}

export function formatMoney(amount) {
  return `Rs ${Number(amount).toLocaleString("en-PK", { maximumFractionDigits: 2 })}`;
}

export function plural(n, word, many = word + "s") {
  return `${n} ${n === 1 ? word : many}`;
}

/** "Due in 3 days", "Due today", "Overdue by 2 days" from a loan's days_left / days_overdue. */
export function dueText(loan) {
  if (loan.overdue) return `Overdue by ${plural(loan.days_overdue, "day")}`;
  if (loan.days_left === 0) return "Due today";
  if (loan.days_left === 1) return "Due tomorrow";
  return `Due in ${plural(loan.days_left, "day")}`;
}

// ---------- session ----------

/** The logged-in user, or redirect to the login page. */
export async function requireUser() {
  try {
    return await api.get("/api/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      window.location.replace("/");
      return new Promise(() => {}); // stop here while the browser navigates
    }
    throw error;
  }
}

/** The page each role starts on. */
export function homeFor(user) {
  return user.can_manage_library ? "/staff" : "/dashboard";
}

/**
 * Load the user and draw the nav. Returns the user.
 * who: "member" or "staff" sends anyone else to their own home page; "any" lets both in.
 */
export async function startPage(who) {
  const user = await requireUser();
  const wrongRole = (who === "member" && user.can_manage_library) ||
                    (who === "staff" && !user.can_manage_library);
  if (wrongRole) {
    window.location.replace(homeFor(user));
    return new Promise(() => {});
  }
  renderNav(user);
  return user;
}

// ---------- theme ----------

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function themeToggle() {
  const button = h("button", { class: "btn btn-quiet btn-icon", type: "button" });
  const paint = () => {
    const dark = currentTheme() === "dark";
    button.replaceChildren(icon(dark ? ICONS.sun : ICONS.moon));
    button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    button.title = button.getAttribute("aria-label");
  };
  button.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch { /* storage blocked: still works for this page */ }
    paint();
  });
  paint();
  return button;
}

// ---------- navigation ----------

const MEMBER_LINKS = [
  ["/dashboard", "Dashboard"],
  ["/catalog", "Catalog"],
  ["/loans", "My loans"],
  ["/reservations", "Reservations"],
  ["/dashboard#ask", "Ask the librarian"],
];
const STAFF_LINKS = [
  ["/staff", "Overview"],
  ["/catalog", "Catalog"],
  ["/staff/desk", "Issue & return"],
  ["/staff/members", "Members"],
  ["/staff/reports", "Reports"],
];

/** Fill <header id="topnav"> for this user. Librarians get the dark staff bar. */
export function renderNav(user) {
  const staff = user.can_manage_library;
  const here = window.location.pathname;
  const isCurrent = (href) =>
    href === here || (href === "/catalog" && here.startsWith("/catalog/"));

  const logout = h("button", { class: "btn btn-quiet btn-small", type: "button" }, "Log out");
  logout.addEventListener("click", async () => {
    logout.setAttribute("aria-busy", "true");
    try { await api.post("/api/logout"); } catch { /* going to the login page anyway */ }
    window.location.replace("/");
  });

  const header = document.getElementById("topnav");
  header.className = staff ? "topnav staff" : "topnav";
  header.replaceChildren(
    h("div", { class: "container" },
      h("a", { class: "brand", href: homeFor(user) },
        "The Reading Room",
        staff ? h("span", { class: "brand-sub" }, " · Front desk") : null),
      h("nav", { class: "nav-links", "aria-label": "Main" },
        (staff ? STAFF_LINKS : MEMBER_LINKS).map(([href, label]) =>
          h("a", { href, "aria-current": isCurrent(href) ? "page" : null }, label))),
      h("div", { class: "nav-user" },
        h("span", { class: "who" }, `${user.name} · ${user.role}`),
        themeToggle(),
        logout)));
}

// ---------- shared pieces ----------

/** A book cover in the item's type colour, with the title on it (or blank when small). */
export function cover(type, title, { size = "", href = null } = {}) {
  const props = {
    class: `cover ${size}`, dataset: { type },
    "aria-hidden": href ? null : "true",
  };
  if (href) return h("a", { ...props, href }, title);
  return h("div", props, size === "small" ? null : title);
}

/** One number in a stat strip. tone: "" or "warn". */
export function stat(value, label, tone = "") {
  return h("div", { class: "stat" },
    h("div", { class: `stat-value ${tone === "warn" ? "tone-warn" : ""}` }, value),
    h("div", { class: "stat-label" }, label));
}

/** Colour for an item's status words, from flags the API sends. */
export function statusTone(item) {
  if (item.restriction_note && !(item.actions && item.actions.can_borrow)) return "tone-muted";
  return item.available_now ? "tone-good" : "tone-warn";
}

/**
 * The one button under a book, chosen only from item.actions (decided in Python).
 * handlers: { borrow(item, button), reserve(item, button) }
 */
export function bookButton(item, handlers) {
  const a = item.actions;
  if (!a) {
    return h("a", { class: "btn btn-quiet btn-block", href: `/catalog/${encodeURIComponent(item.item_id)}` },
      "View details");
  }
  if (a.has_loan) return h("button", { class: "btn btn-block", type: "button", disabled: true }, "On your shelf");
  if (a.queue_position) {
    return h("button", { class: "btn btn-block", type: "button", disabled: true },
      `Number ${a.queue_position} in line`);
  }
  if (a.can_borrow) {
    return h("button", { class: "btn btn-outline btn-block", type: "button",
      onclick: (e) => handlers.borrow(item, e.currentTarget) }, "Borrow");
  }
  if (a.can_reserve) {
    return h("button", { class: "btn btn-quiet btn-block", type: "button",
      onclick: (e) => handlers.reserve(item, e.currentTarget) }, "Join waitlist");
  }
  return h("button", { class: "btn btn-block", type: "button", disabled: true, title: a.reason || null },
    a.unavailable_label || "Not available");
}

/** A book tile: cover (links to the item page), meta, status, one button. */
export function bookTile(item, handlers, index = 0, { compact = false } = {}) {
  const href = `/catalog/${encodeURIComponent(item.item_id)}`;
  return h("article", { class: "book", style: { animationDelay: `${Math.min(index, 12) * 25}ms` } },
    cover(item.type, item.title, { href, size: compact ? "tiny" : "" }),
    h("div", { class: "book-meta" }, compact ? item.author : `${item.author} · ${item.item_type}`),
    compact ? null : h("div", { class: `status ${statusTone(item)}` }, item.status_text),
    bookButton(item, handlers));
}

/** Copy each column header onto its cells as data-label, so phones can show "Due: 4 Nov". */
export function labelledTable(table) {
  const labels = [...table.querySelectorAll("thead th")].map((th) => th.textContent.trim());
  for (const row of table.querySelectorAll("tbody tr")) {
    [...row.children].forEach((cell, i) => { if (labels[i]) cell.dataset.label = labels[i]; });
  }
  return table;
}

/** Put a button into its "working" state; returns a function that restores it. */
export function busy(button, text) {
  const old = button.textContent;
  button.setAttribute("aria-busy", "true");
  button.disabled = true;
  button.textContent = text;
  return () => {
    button.removeAttribute("aria-busy");
    button.disabled = false;
    button.textContent = old;
  };
}

// ---------- toasts ----------

function toastRegion() {
  let region = document.getElementById("toasts");
  if (!region) {
    region = h("div", { id: "toasts", class: "toasts", role: "status", "aria-live": "polite" });
    document.body.append(region);
  }
  return region;
}

/** Show a short message. kind: "success" or "error". */
export function toast(title, message = "", kind = "success") {
  const close = h("button", { type: "button", "aria-label": "Dismiss" }, "×");
  const el = h("div", { class: `toast ${kind === "error" ? "error" : ""}` },
    h("div", { class: "grow" }, h("strong", {}, title), message ? h("p", {}, message) : null),
    close);
  const remove = () => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 250);
  };
  close.addEventListener("click", remove);
  toastRegion().append(el);
  setTimeout(remove, kind === "error" ? 7000 : 4500);
}

export function toastError(error, title = "That didn't work") {
  const message = error instanceof ApiError
    ? [error.message, error.nextStep].filter(Boolean).join(" ")
    : "Something went wrong. Please try again.";
  toast(title, message, "error");
}

/** "Borrowing is paused" notice from the member's own block reason and next step, or "". */
export function blockedNotice(member) {
  if (member.can_borrow) return "";
  return h("div", { class: "notice warn", role: "status" },
    h("strong", {}, "Borrowing is paused. "), member.borrow_block_reason,
    member.borrow_next_step ? h("span", { class: "next" }, member.borrow_next_step) : null);
}

/** Toast after a fine payment: what is left, and what (if anything) still blocks borrowing. */
export function paymentToast(member, { forStaff = false } = {}) {
  const left = member.current_fine > 0 ? `${formatMoney(member.current_fine)} of the current fine is left. ` : "";
  const next = member.can_borrow
    ? (forStaff ? `${member.name} can borrow again.` : "You can borrow again.")
    : member.borrow_next_step || member.borrow_block_reason;
  toast(forStaff ? "Payment recorded" : "Fine paid", left + next);
}

/**
 * The dark "ask" panel, switched off until the chat assistant exists (Phase 9).
 * Members get ChatAssistant and staff get StaffAssistant; both share this panel.
 */
export function assistantPanel({ title, placeholder, comingSoon }) {
  return h("section", { class: "dark-panel", id: "ask", "aria-labelledby": "ask-title" },
    h("h2", { id: "ask-title" }, title),
    h("form", { class: "row", onsubmit: (e) => e.preventDefault() },
      h("label", { class: "visually-hidden", for: "ask-input" }, "Message"),
      h("input", { class: "input", id: "ask-input", type: "text", disabled: true, placeholder }),
      h("button", { class: "btn btn-light", type: "submit", disabled: true }, "Ask")),
    h("p", { class: "muted small" }, `Coming soon: ${comingSoon}`));
}

/** How an overdue loan's fine reads before it is charged. */
export function accruingText(loan) {
  return `adds ${formatMoney(loan.fine)} when returned`;
}

// ---------- page states ----------

/** Loading placeholder. kind: "covers", "rows" or "lines". */
export function loadingState(kind = "covers", n = 6) {
  const box = (cls) => h("div", { class: `skeleton ${cls}` });
  if (kind === "covers") {
    return h("div", { class: "book-grid", "aria-busy": "true", "aria-label": "Loading" },
      Array.from({ length: n }, () => box("skeleton-cover")));
  }
  if (kind === "rows") {
    return h("div", { class: "stack", "aria-busy": "true", "aria-label": "Loading" },
      Array.from({ length: n }, () => box("skeleton-row")));
  }
  return h("div", { "aria-busy": "true", "aria-label": "Loading" },
    Array.from({ length: n }, () => box("skeleton-line")));
}

export function emptyState(title, message, action = null, compact = true) {
  return h("div", { class: `state ${compact ? "compact" : ""}` },
    h("h3", {}, title), message ? h("p", {}, message) : null, action);
}

export function errorState(error, retry) {
  const message = error instanceof ApiError
    ? error.message : "Something went wrong while loading this page.";
  return h("div", { class: "state error", role: "alert" },
    h("h3", {}, "Couldn't load this"),
    h("p", {}, message),
    retry ? h("button", { class: "btn btn-quiet", type: "button", onclick: retry }, "Try again") : null);
}

/** Run a page's start function; if it fails before drawing, show an error with a retry. */
export async function boot(main, start) {
  try {
    await start();
  } catch (error) {
    main.replaceChildren(errorState(error, () => window.location.reload()));
  }
}
