// Schlanker API-Client fuer die EVLädeQueue
// Verwaltet Access-/Refresh-Token im localStorage und haengt Authorization automatisch an.

const API_BASE = "/api/v1";

const TokenStore = {
  getAccess() { return localStorage.getItem("ev_access_token"); },
  getRefresh() { return localStorage.getItem("ev_refresh_token"); },
  set(access, refresh) {
    localStorage.setItem("ev_access_token", access);
    localStorage.setItem("ev_refresh_token", refresh);
  },
  clear() {
    localStorage.removeItem("ev_access_token");
    localStorage.removeItem("ev_refresh_token");
  },
};

class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : "Anfrage fehlgeschlagen");
    this.status = status;
    this.detail = detail;
  }
}

async function apiRequest(method, path, body, opts = {}) {
  const { auth = true, retry = true } = opts;
  const headers = { "Content-Type": "application/json" };
  if (auth && TokenStore.getAccess()) {
    headers["Authorization"] = `Bearer ${TokenStore.getAccess()}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && auth && retry && TokenStore.getRefresh()) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return apiRequest(method, path, body, { auth, retry: false });
    }
    TokenStore.clear();
    window.dispatchEvent(new CustomEvent("ev:unauthorized"));
    throw new ApiError(401, "Sitzung abgelaufen, bitte erneut anmelden.");
  }

  if (res.status === 204) return null;

  let data = null;
  try { data = await res.json(); } catch (_) { /* kein JSON-Body */ }

  if (!res.ok) {
    let detailMsg = data && data.detail ? data.detail : `Fehler ${res.status}`;
    if (Array.isArray(detailMsg)) {
      detailMsg = detailMsg.map(e => e.msg || JSON.stringify(e)).join(", ");
    }
    throw new ApiError(res.status, detailMsg);
  }
  return data;
}

async function tryRefreshToken() {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: TokenStore.getRefresh() }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    TokenStore.set(data.access_token, data.refresh_token);
    return true;
  } catch (_) {
    return false;
  }
}

const Api = {
  register: (payload) => apiRequest("POST", "/auth/register", payload, { auth: false }),
  login: (payload) => apiRequest("POST", "/auth/login", payload, { auth: false }),
  logout: () => apiRequest("POST", "/auth/logout", { refresh_token: TokenStore.getRefresh() }, { auth: false }),
  me: () => apiRequest("GET", "/auth/me"),

  listLocations: () => apiRequest("GET", "/charging/locations"),
  getLocation: (id) => apiRequest("GET", `/charging/locations/${id}`),
  checkIn: (pointId) => apiRequest("POST", `/charging/charging-points/${pointId}/check-in`),
  mySession: () => apiRequest("GET", "/charging/my-session"),

  joinQueue: (pointId, parkingOffer) => apiRequest("POST", `/queue/charging-points/${pointId}/join`, { parking_offer: parkingOffer }),
  leaveQueue: (entryId) => apiRequest("DELETE", `/queue/entries/${entryId}`),
  myQueueStatus: () => apiRequest("GET", "/queue/my-status"),

  initiateCheckout: (pointId) => apiRequest("POST", `/checkout/charging-points/${pointId}/initiate`),
  checkoutDecision: (pointId, action) => apiRequest("POST", `/checkout/charging-points/${pointId}/decision`, { action }),

  adminListLocations: () => apiRequest("GET", "/admin/locations"),
  adminCreateLocation: (payload) => apiRequest("POST", "/admin/locations", payload),
  adminGetLocation: (id) => apiRequest("GET", `/admin/locations/${id}`),
  adminCreatePoint: (locationId, payload) => apiRequest("POST", `/admin/locations/${locationId}/charging-points`, payload),
  adminDeletePoint: (pointId) => apiRequest("DELETE", `/admin/charging-points/${pointId}`),
  adminDeleteLocation: (locationId) => apiRequest("DELETE", `/admin/locations/${locationId}`),

  myRewards: () => apiRequest("GET", "/rewards/me"),
  setLeaderboardOptIn: (optIn) => apiRequest("PUT", "/rewards/leaderboard-opt-in", { leaderboard_opt_in: optIn }),
  setLeaderboardDisplay: (display) => apiRequest("PUT", "/rewards/leaderboard-display", { leaderboard_display: display }),
  getLeaderboard: () => apiRequest("GET", "/rewards/leaderboard"),

  updateProfile: (payload) => apiRequest("PUT", "/auth/me", payload),

  listCars: () => apiRequest("GET", "/rewards/cars"),
  createCar: (payload) => apiRequest("POST", "/rewards/cars", payload),
  updateCar: (carId, payload) => apiRequest("PUT", `/rewards/cars/${carId}`, payload),
  deleteCar: (carId) => apiRequest("DELETE", `/rewards/cars/${carId}`),

  uploadAvatar: (file) => uploadImage("/rewards/avatar", file),
  uploadCarPhoto: (carId, file) => uploadImage(`/rewards/cars/${carId}/photo`, file),
};

async function uploadImage(path, file) {
  const formData = new FormData();
  formData.append("file", file);
  const headers = {};
  if (TokenStore.getAccess()) headers["Authorization"] = `Bearer ${TokenStore.getAccess()}`;
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: formData });
  let data = null;
  try { data = await res.json(); } catch (_) { /* kein JSON-Body */ }
  if (!res.ok) {
    const detailMsg = data && data.detail ? data.detail : `Fehler ${res.status}`;
    throw new ApiError(res.status, detailMsg);
  }
  return data;
}
