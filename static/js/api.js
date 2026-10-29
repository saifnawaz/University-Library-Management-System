// Talks to the Flask API. Every error comes back as an ApiError with a
// readable message, never a raw response or stack trace.

export class ApiError extends Error {
  constructor(message, type, status, nextStep = null) {
    super(message);
    this.type = type;          // e.g. "LimitExceeded", from the Python exception
    this.status = status;      // HTTP status; 0 means the server could not be reached
    this.nextStep = nextStep;  // what the user can do about it, if Python said
  }
}

async function request(method, url, body) {
  const options = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new ApiError(
      "Can't reach the library server. Check your connection and try again.",
      "NetworkError", 0);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data && data.error;
    throw new ApiError(
      (error && error.message) || "Something went wrong. Please try again.",
      (error && error.type) || "Error",
      response.status,
      (error && error.next_step) || null);
  }
  return data;
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, body = {}) => request("POST", url, body),
  del: (url) => request("DELETE", url),
};
