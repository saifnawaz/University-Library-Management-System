// "Ask the librarian": sends the member's question to Python and shows the answer.
// Python decides everything (topic, rate limit, what data the LLM sees); this only draws it.

import { api, ApiError } from "./api.js";
import { h, busy } from "./ui.js";

const SUGGESTIONS = ["What's due soon?", "Do I owe any fines?", "What should I read next?"];
const KEEP = 4; // exchanges kept on screen

/** One question and its answer (or "Thinking…" while waiting). */
function exchange(question) {
  const answer = h("p", { class: "chat-answer pending" }, "Thinking…");
  const el = h("div", { class: "chat-exchange" },
    h("p", { class: "chat-question" }, h("span", { class: "chat-who" }, "You"), question),
    h("div", {}, h("span", { class: "chat-who" }, "Librarian"), answer));
  return {
    el,
    show(text, kind = "answer") {
      answer.className = `chat-answer ${kind}`;
      answer.textContent = text; // text only: the reply is never treated as HTML
    },
  };
}

export function chatPanel() {
  const input = h("input", { class: "input", id: "ask-input", type: "text", maxlength: "500",
    autocomplete: "off", placeholder: "Is Deep Learning by Goodfellow available?" });
  const send = h("button", { class: "btn btn-light", type: "submit" }, "Ask");
  const log = h("div", { class: "chat-log", "aria-live": "polite" });
  const suggestions = h("div", { class: "chat-suggestions" },
    SUGGESTIONS.map((text) => h("button", { class: "btn btn-quiet btn-small", type: "button",
      onclick: () => ask(text) }, text)));

  async function ask(text) {
    const question = text.trim();
    if (!question) { input.focus(); return; } // convenience only; Python checks too
    suggestions.hidden = true;
    const item = exchange(question);
    log.append(item.el);
    while (log.children.length > KEEP) log.firstElementChild.remove();
    input.value = "";
    const restore = busy(send, "Asking…");
    try {
      const reply = await api.post("/api/chat", { question });
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
    h("h2", { id: "ask-title" }, "Ask the librarian"),
    log, suggestions, form,
    h("p", { class: "muted small" },
      "Answers come only from the library catalog and your own account. Library questions only."));
}
