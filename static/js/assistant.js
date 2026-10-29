// Chat panels: "Ask the librarian" for members and the staff assistant for librarians.
// Python decides everything (who may ask, topic, rate limit, what data the LLM sees);
// this only sends the question and draws the answer.

import { api, ApiError } from "./api.js";
import { h, busy } from "./ui.js";

const KEEP = 4; // exchanges kept on screen

const MEMBER = {
  title: "Ask the librarian",
  endpoint: "/api/chat",
  answerer: "Librarian",
  placeholder: "Is Deep Learning by Goodfellow available?",
  suggestions: ["What's due soon?", "Do I owe any fines?", "What should I read next?"],
  note: "Answers come only from the library catalog and your own account. Library questions only.",
};

const STAFF = {
  title: "Staff assistant",
  endpoint: "/api/staff/chat",
  answerer: "Assistant",
  placeholder: "Which members have overdue theses?",
  suggestions: ["Who is more than 7 days overdue?", "How many theses are on loan?",
    "Which books have a waitlist?"],
  note: "Answers come only from the library's own records: loans, fines, waitlists, members " +
    "and the catalog. It can't change anything; use Issue & return or Members for that.",
};

/** One question and its answer (or "Thinking…" while waiting). */
function exchange(question, answerer) {
  const answer = h("p", { class: "chat-answer pending" }, "Thinking…");
  const el = h("div", { class: "chat-exchange" },
    h("p", { class: "chat-question" }, h("span", { class: "chat-who" }, "You"), question),
    h("div", {}, h("span", { class: "chat-who" }, answerer), answer));
  return {
    el,
    show(text, kind = "answer") {
      answer.className = `chat-answer ${kind}`;
      answer.textContent = text; // text only: the reply is never treated as HTML
    },
  };
}

function panel({ title, endpoint, answerer, placeholder, suggestions: starters, note }) {
  const input = h("input", { class: "input", id: "ask-input", type: "text", maxlength: "500",
    autocomplete: "off", placeholder });
  const send = h("button", { class: "btn btn-light", type: "submit" }, "Ask");
  const log = h("div", { class: "chat-log", "aria-live": "polite" });
  const suggestions = h("div", { class: "chat-suggestions" },
    starters.map((text) => h("button", { class: "btn btn-quiet btn-small", type: "button",
      onclick: () => ask(text) }, text)));

  async function ask(text) {
    const question = text.trim();
    if (!question) { input.focus(); return; } // convenience only; Python checks too
    suggestions.hidden = true;
    const item = exchange(question, answerer);
    log.append(item.el);
    while (log.children.length > KEEP) log.firstElementChild.remove();
    input.value = "";
    const restore = busy(send, "Asking…");
    try {
      const reply = await api.post(endpoint, { question });
      item.show(reply.answer, reply.kind);
    } catch (error) {
      const message = error instanceof ApiError
        ? [error.message, error.nextStep].filter(Boolean).join(" ")
        : "Something went wrong. Please try again.";
      item.show(message, "error");
    } finally {
      restore();
      input.focus();
    }
  }

  const form = h("form", { class: "row", onsubmit: (e) => { e.preventDefault(); ask(input.value); } },
    h("label", { class: "visually-hidden", for: "ask-input" }, "Your question"), input, send);
  return h("section", { class: "dark-panel", id: "ask", "aria-labelledby": "ask-title" },
    h("h2", { id: "ask-title" }, title),
    log, suggestions, form,
    h("p", { class: "muted small" }, note));
}

/** The member's "Ask the librarian" panel. */
export function chatPanel() {
  return panel(MEMBER);
}

/** The librarian's staff assistant panel (staff overview). */
export function staffChatPanel() {
  return panel(STAFF);
}
