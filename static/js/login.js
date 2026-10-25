// Login page: send the user id and password, then go to the right home page.

import { api, ApiError } from "./api.js";
import { homeFor, themeToggle, toast } from "./ui.js";

const form = document.getElementById("login-form");
const userIdInput = document.getElementById("user-id");
const passwordInput = document.getElementById("password");
const submit = document.getElementById("submit");
const errorBox = document.getElementById("form-error");

document.getElementById("theme-slot").append(themeToggle());

// There is no self-service reset; say how it works instead of a dead link.
document.getElementById("forgot").addEventListener("click", (event) => {
  event.preventDefault();
  toast("Forgot your password?", "Ask at the circulation desk and a librarian will reset it for you.");
});

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

// Already signed in? Skip the form.
api.get("/api/me").then((user) => window.location.replace(homeFor(user))).catch(() => {
  userIdInput.focus();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;

  // Convenience check only; the server checks the same thing.
  if (!userIdInput.value.trim() || !passwordInput.value) {
    showError("Enter your user ID and password.");
    return;
  }

  submit.disabled = true;
  submit.textContent = "Signing in…";
  try {
    const user = await api.post("/api/login", {
      user_id: userIdInput.value.trim(),
      password: passwordInput.value,
    });
    window.location.replace(homeFor(user));
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    passwordInput.value = "";
    passwordInput.focus();
    submit.disabled = false;
    submit.textContent = "Sign in";
  }
});
