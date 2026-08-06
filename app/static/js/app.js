// EVLädeQueue - Frontend-Logik

let currentUser = null;

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function switchView(viewName) {
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  const target = document.getElementById(`view-${viewName}`);
  if (target) target.classList.remove("hidden");

  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.view === viewName);
  });

  if (viewName === "dashboard") loadDashboard();
  if (viewName === "my-status") loadMyStatus();
  if (viewName === "admin") loadAdminView();
  if (viewName === "leaderboard") loadLeaderboard();
  if (viewName === "profile") loadProfile();
}

function setLoggedInUI(user) {
  currentUser = user;
  document.getElementById("view-auth").classList.add("hidden");
  document.getElementById("mainNav").classList.remove("hidden");
  document.getElementById("logoutBtn").classList.remove("hidden");
  const badge = document.getElementById("userBadge");
  badge.textContent = `${user.full_name} (${user.role === "admin" ? "Admin" : "Mitglied"})`;
  badge.classList.remove("hidden");

  document.querySelectorAll(".admin-only").forEach(el => {
    el.classList.toggle("hidden", user.role !== "admin");
  });

  document.getElementById("footerAuth").classList.add("hidden");
  document.getElementById("footerApp").classList.remove("hidden");

  switchView("dashboard");
}

function setLoggedOutUI() {
  currentUser = null;
  TokenStore.clear();
  document.getElementById("mainNav").classList.add("hidden");
  document.getElementById("logoutBtn").classList.add("hidden");
  document.getElementById("userBadge").classList.add("hidden");
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  document.getElementById("view-auth").classList.remove("hidden");

  document.getElementById("footerApp").classList.add("hidden");
  document.getElementById("footerAuth").classList.remove("hidden");
}

async function tryAutoLogin() {
  if (!TokenStore.getAccess()) { setLoggedOutUI(); return; }
  try {
    const user = await Api.me();
    setLoggedInUI(user);
  } catch (_) {
    setLoggedOutUI();
  }
}

window.addEventListener("ev:unauthorized", () => {
  setLoggedOutUI();
  showToast("Sitzung abgelaufen, bitte erneut anmelden.", "error");
});

/* ---------- Auth Forms ---------- */
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("loginForm").classList.toggle("hidden", tab !== "login");
    document.getElementById("registerForm").classList.toggle("hidden", tab !== "register");
  });
});

document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = document.getElementById("loginMsg");
  msgEl.textContent = "";
  const fd = new FormData(e.target);
  try {
    const data = await Api.login({ email: fd.get("email"), password: fd.get("password") });
    TokenStore.set(data.access_token, data.refresh_token);
    const user = await Api.me();
    setLoggedInUI(user);
    showToast(`Willkommen zurueck, ${user.full_name}!`, "success");
  } catch (err) {
    msgEl.textContent = err.detail || "Anmeldung fehlgeschlagen.";
    msgEl.classList.add("error");
  }
});

document.getElementById("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = document.getElementById("registerMsg");
  msgEl.textContent = "";
  msgEl.classList.remove("error", "success");
  const fd = new FormData(e.target);
  try {
    await Api.register({
      email: fd.get("email"),
      password: fd.get("password"),
      full_name: fd.get("full_name"),
    });
    msgEl.textContent = "Konto erstellt! Du kannst dich jetzt anmelden.";
    msgEl.classList.add("success");
    document.querySelector('.tab-btn[data-tab="login"]').click();
  } catch (err) {
    msgEl.textContent = err.detail || "Registrierung fehlgeschlagen.";
    msgEl.classList.add("error");
  }
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  try { await Api.logout(); } catch (_) { /* ignore */ }
  setLoggedOutUI();
  showToast("Erfolgreich abgemeldet.", "success");
});

document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

/* ---------- Dashboard ---------- */
async function loadDashboard() {
  const container = document.getElementById("locationsContainer");
  container.innerHTML = '<p class="empty-state">Lade Standorte...</p>';
  try {
    const locations = await Api.listLocations();
    if (!locations.length) {
      container.innerHTML = '<div class="empty-state"><span class="icon">&#128204;</span>Noch keine Standorte vorhanden.</div>';
      return;
    }
    container.innerHTML = locations.map(renderLocationCard).join("");
    attachDashboardHandlers();
  } catch (err) {
    container.innerHTML = `<p class="empty-state">Fehler beim Laden: ${err.detail || err.message}</p>`;
  }
}

function renderLocationCard(loc) {
  const points = loc.charging_points.map(cp => {
    let statusClass = "status-free";
    let statusText = "Frei";
    if (!cp.is_active) { statusClass = "status-inactive"; statusText = "Deaktiviert"; }
    else if (cp.is_occupied) { statusClass = "status-occupied"; statusText = "Belegt"; }

    let actionHtml = "";
    if (cp.is_active) {
      if (!cp.is_occupied) {
        actionHtml = `<button class="btn btn-primary btn-sm" data-action="checkin" data-point="${cp.id}">Einchecken</button>`;
      } else {
        actionHtml = `
          <select class="parking-select" data-point-select="${cp.id}">
            <option value="none">Kein Parkplatzangebot</option>
            <option value="free">Kostenloser Parkplatz</option>
            <option value="paid">Kostenpflichtiger Parkplatz</option>
          </select>
          <button class="btn btn-secondary btn-sm" data-action="join-queue" data-point="${cp.id}">Warteschlange</button>`;
      }
    }

    return `
      <div class="point-row">
        <div class="point-info">
          <span class="point-label">${escapeHtml(cp.label)}</span>
          <span class="point-meta">${cp.connector_type ? escapeHtml(cp.connector_type) + " &middot; " : ""}${cp.max_power_kw ? cp.max_power_kw + " kW &middot; " : ""}${cp.queue_length} in Warteschlange</span>
        </div>
        <span class="status-pill ${statusClass}">${statusText}</span>
        <div class="point-actions">${actionHtml}</div>
      </div>`;
  }).join("");

  return `
    <div class="card location-card">
      <h3>${escapeHtml(loc.name)}</h3>
      <p class="location-address">${escapeHtml(loc.address)}</p>
      ${points || '<p class="point-meta">Keine Ladepunkte an diesem Standort.</p>'}
    </div>`;
}

function attachDashboardHandlers() {
  document.querySelectorAll('[data-action="checkin"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        await Api.checkIn(btn.dataset.point);
        showToast("Erfolgreich eingecheckt. Guten Ladevorgang!", "success");
        loadDashboard();
      } catch (err) {
        showToast(err.detail || "Check-in fehlgeschlagen.", "error");
      }
    });
  });

  document.querySelectorAll('[data-action="join-queue"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      const select = document.querySelector(`[data-point-select="${btn.dataset.point}"]`);
      try {
        await Api.joinQueue(btn.dataset.point, select.value);
        showToast("Du wurdest in die Warteschlange eingetragen.", "success");
        loadDashboard();
      } catch (err) {
        showToast(err.detail || "Beitritt zur Warteschlange fehlgeschlagen.", "error");
      }
    });
  });
}

document.getElementById("refreshDashboardBtn").addEventListener("click", loadDashboard);

/* ---------- My Status ---------- */
async function loadMyStatus() {
  const container = document.getElementById("myStatusContainer");
  container.innerHTML = '<p class="empty-state">Lade Status...</p>';

  try {
    const [session, queueStatus] = await Promise.all([
      Api.mySession().catch(() => null),
      Api.myQueueStatus().catch(() => null),
    ]);

    let html = "";

    if (session) {
      html += `
        <div class="status-block">
          <h4>&#9889; Aktiver Ladevorgang</h4>
          <div class="status-row"><span>Standort</span><span>${escapeHtml(session.location_name)}</span></div>
          <div class="status-row"><span>Ladepunkt</span><span>${escapeHtml(session.charging_point_label)}</span></div>
          <div class="status-row"><span>Eingecheckt seit</span><span>${formatDate(session.checked_in_at)}</span></div>
          <div style="margin-top:14px;">
            <button class="btn btn-warning" id="initiateCheckoutBtn" data-point="${session.charging_point_id}">Abstoepseln</button>
          </div>
          <div id="checkoutDecisionArea"></div>
        </div>`;
    }

    if (queueStatus) {
      html += `
        <div class="status-block queue">
          <h4>&#8987; In der Warteschlange</h4>
          <div class="status-row"><span>Standort</span><span>${escapeHtml(queueStatus.location_name)}</span></div>
          <div class="status-row"><span>Ladepunkt</span><span>${escapeHtml(queueStatus.charging_point_label)}</span></div>
          <div class="status-row"><span>Position</span><span>#${queueStatus.position}</span></div>
          <div class="status-row"><span>Personen vor dir</span><span>${queueStatus.people_ahead}</span></div>
          <div class="status-row"><span>Dein Angebot</span><span>${translateOffer(queueStatus.parking_offer)}</span></div>
          <div style="margin-top:14px;">
            <button class="btn btn-danger btn-sm" id="leaveQueueBtn" data-entry="${queueStatus.queue_entry_id}">Warteschlange verlassen</button>
          </div>
        </div>`;
    }

    if (!session && !queueStatus) {
      html = '<div class="empty-state"><span class="icon">&#127925;</span>Du ladest aktuell nicht und stehst in keiner Warteschlange.<br><br>Gehe zu "Standorte", um einzuchecken.</div>';
    }

    container.innerHTML = html;
    attachStatusHandlers();
  } catch (err) {
    container.innerHTML = `<p class="empty-state">Fehler beim Laden: ${err.detail || err.message}</p>`;
  }
}

function attachStatusHandlers() {
  const checkoutBtn = document.getElementById("initiateCheckoutBtn");
  if (checkoutBtn) {
    checkoutBtn.addEventListener("click", async () => {
      try {
        const result = await Api.initiateCheckout(checkoutBtn.dataset.point);
        handleCheckoutResult(result, checkoutBtn.dataset.point);
      } catch (err) {
        showToast(err.detail || "Abstoepseln fehlgeschlagen.", "error");
      }
    });
  }

  const leaveBtn = document.getElementById("leaveQueueBtn");
  if (leaveBtn) {
    leaveBtn.addEventListener("click", async () => {
      try {
        await Api.leaveQueue(leaveBtn.dataset.entry);
        showToast("Du hast die Warteschlange verlassen.", "success");
        loadMyStatus();
      } catch (err) {
        showToast(err.detail || "Aktion fehlgeschlagen.", "error");
      }
    });
  }
}

function handleCheckoutResult(result, pointId) {
  const area = document.getElementById("checkoutDecisionArea");
  if (result.action === "pending_decision") {
    area.innerHTML = `
      <div class="decision-box">
        <p>Die naechste Person in der Warteschlange bietet keinen kostenlosen Parkplatz (${translateOffer(result.pending_user_parking_offer)}). Wie moechtest du vorgehen?</p>
        <div class="decision-actions">
          <button class="btn btn-primary btn-sm" id="notifyDecisionBtn">Trotzdem benachrichtigen</button>
          <button class="btn btn-ghost btn-sm" id="skipDecisionBtn">Ueberspringen</button>
        </div>
      </div>`;
    document.getElementById("notifyDecisionBtn").addEventListener("click", () => submitDecision(pointId, "notify"));
    document.getElementById("skipDecisionBtn").addEventListener("click", () => submitDecision(pointId, "skip"));
  } else {
    showToast(result.message || "Ladevorgang abgeschlossen.", "success");
    loadMyStatus();
  }
}

async function submitDecision(pointId, action) {
  try {
    const result = await Api.checkoutDecision(pointId, action);
    if (result.action === "skipped_next_pending") {
      handleCheckoutResult({ action: "pending_decision", pending_user_parking_offer: result.pending_user_parking_offer }, pointId);
    } else {
      showToast(result.message || "Erledigt.", "success");
      loadMyStatus();
    }
  } catch (err) {
    showToast(err.detail || "Aktion fehlgeschlagen.", "error");
  }
}

document.getElementById("refreshMyStatusBtn").addEventListener("click", loadMyStatus);

/* ---------- Admin View ---------- */
async function loadAdminView() {
  try {
    const locations = await Api.adminListLocations();
    const select = document.getElementById("pointLocationSelect");
    select.innerHTML = locations.map(l => `<option value="${l.id}">${escapeHtml(l.name)}</option>`).join("");

    const listContainer = document.getElementById("adminLocationsList");
    if (!locations.length) {
      listContainer.innerHTML = '<p class="point-meta">Noch keine Standorte angelegt.</p>';
      return;
    }

    const detailed = await Promise.all(locations.map(l => Api.adminGetLocation(l.id)));
    listContainer.innerHTML = detailed.map(renderAdminLocationItem).join("");
    attachAdminListHandlers();
  } catch (err) {
    showToast(err.detail || "Verwaltungsdaten konnten nicht geladen werden.", "error");
  }
}

function renderAdminLocationItem(loc) {
  const chips = loc.charging_points.map(cp => `
    <span class="chip">
      ${escapeHtml(cp.label)}${cp.max_power_kw ? " &middot; " + cp.max_power_kw + " kW" : ""}
      <a href="#" data-action="delete-point" data-point="${cp.id}" style="color:var(--color-danger); margin-left:6px; text-decoration:none; font-weight:800;">&times;</a>
    </span>`).join("");

  return `
    <div class="admin-location-item">
      <div class="alh">
        <span>${escapeHtml(loc.name)}</span>
        <button class="btn btn-danger btn-sm" data-action="delete-location" data-location="${loc.id}">Standort loeschen</button>
      </div>
      <p class="point-meta">${escapeHtml(loc.address)}</p>
      <div class="points-inline">${chips || '<span class="point-meta">Keine Ladepunkte</span>'}</div>
    </div>`;
}

function attachAdminListHandlers() {
  document.querySelectorAll('[data-action="delete-location"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Standort inkl. aller Ladepunkte wirklich loeschen?")) return;
      try {
        await Api.adminDeleteLocation(btn.dataset.location);
        showToast("Standort geloescht.", "success");
        loadAdminView();
      } catch (err) {
        showToast(err.detail || "Loeschen fehlgeschlagen.", "error");
      }
    });
  });

  document.querySelectorAll('[data-action="delete-point"]').forEach(link => {
    link.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!confirm("Ladepunkt wirklich loeschen?")) return;
      try {
        await Api.adminDeletePoint(link.dataset.point);
        showToast("Ladepunkt geloescht.", "success");
        loadAdminView();
      } catch (err) {
        showToast(err.detail || "Loeschen fehlgeschlagen.", "error");
      }
    });
  });
}

document.getElementById("createLocationForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = document.getElementById("createLocationMsg");
  msgEl.textContent = "";
  msgEl.classList.remove("error", "success");
  const fd = new FormData(e.target);
  try {
    await Api.adminCreateLocation({
      name: fd.get("name"),
      address: fd.get("address"),
      description: fd.get("description") || null,
    });
    msgEl.textContent = "Standort erfolgreich angelegt.";
    msgEl.classList.add("success");
    e.target.reset();
    loadAdminView();
  } catch (err) {
    msgEl.textContent = err.detail || "Anlegen fehlgeschlagen.";
    msgEl.classList.add("error");
  }
});

document.getElementById("createPointForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = document.getElementById("createPointMsg");
  msgEl.textContent = "";
  msgEl.classList.remove("error", "success");
  const fd = new FormData(e.target);
  const locationId = fd.get("location_id");
  try {
    await Api.adminCreatePoint(locationId, {
      label: fd.get("label"),
      connector_type: fd.get("connector_type") || null,
      max_power_kw: fd.get("max_power_kw") ? parseInt(fd.get("max_power_kw"), 10) : null,
    });
    msgEl.textContent = "Ladepunkt erfolgreich angelegt.";
    msgEl.classList.add("success");
    e.target.reset();
    loadAdminView();
  } catch (err) {
    msgEl.textContent = err.detail || "Anlegen fehlgeschlagen.";
    msgEl.classList.add("error");
  }
});

/* ---------- Utilities ---------- */
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDate(isoString) {
  try {
    const d = new Date(isoString);
    return d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
  } catch (_) {
    return isoString;
  }
}

function translateOffer(offer) {
  const map = { none: "Keines", free: "Kostenlos", paid: "Kostenpflichtig" };
  return map[offer] || offer;
}

/* ---------- Banner-Breite an Login-Karte anpassen ---------- */
function syncBannerWidth() {
  const wrapper = document.getElementById("JM_wrapper");
  const authCard = document.querySelector(".auth-card");
  if (!wrapper) return;
  if (authCard && !document.getElementById("view-auth").classList.contains("hidden")) {
    const width = authCard.getBoundingClientRect().width;
    document.documentElement.style.setProperty("--banner-sync-width", `${width}px`);
  } else {
    document.documentElement.style.setProperty("--banner-sync-width", "496px");
  }
}
window.addEventListener("resize", syncBannerWidth);
window.addEventListener("load", syncBannerWidth);
const bannerSyncObserver = new ResizeObserver(syncBannerWidth);
const authCardEl = document.querySelector(".auth-card");
if (authCardEl) bannerSyncObserver.observe(authCardEl);

/* ---------- Init ---------- */
tryAutoLogin();
syncBannerWidth();


/* ---------- Leaderboard ---------- */
async function loadLeaderboard() {
  const container = document.getElementById("leaderboardContainer");
  container.innerHTML = `<p class="hint-text">Lade Leaderboard...</p>`;
  try {
    const entries = await Api.getLeaderboard();
    if (!entries.length) {
      container.innerHTML = `<p class="hint-text">Noch niemand auf dem Leaderboard sichtbar.</p>`;
      return;
    }
    container.innerHTML = `
      <table class="leaderboard-table">
        <thead><tr><th>Rang</th><th></th><th>Name</th><th>Punkte</th></tr></thead>
        <tbody>
          ${entries.map(e => `
            <tr>
              <td>#${e.rank}</td>
              <td><img class="leaderboard-avatar" src="${e.avatar_path || "/static/img/avatar-placeholder.png"}" alt=""></td>
              <td>${escapeHtml(e.display_name)}${e.is_car ? ` <span class="badge-car" title="Zeigt ein Auto">&#128663;</span>` : ""}</td>
              <td>${e.reward_points}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (err) {
    container.innerHTML = `<p class="form-msg error">Fehler beim Laden: ${err.detail || err.message}</p>`;
  }
}

/* ---------- Profile ---------- */
async function loadProfile() {
  const preview = document.getElementById("profileAvatarPreview");
  if (currentUser && currentUser.avatar_path) {
    preview.src = currentUser.avatar_path;
  }
  document.getElementById("profileFullNameInput").value = currentUser ? currentUser.full_name : "";
  document.getElementById("profileNicknameInput").value = currentUser ? (currentUser.nickname || "") : "";

  const summary = document.getElementById("profileRewardsSummary");
  const toggle = document.getElementById("leaderboardOptInToggle");
  summary.textContent = "Lade Punktestand...";
  try {
    const rewards = await Api.myRewards();
    toggle.checked = rewards.leaderboard_opt_in;
    document.getElementById("displayChoiceUser").checked = rewards.leaderboard_display === "user";
    document.getElementById("displayChoiceCar").checked = rewards.leaderboard_display === "car";
    summary.textContent = rewards.leaderboard_opt_in && rewards.leaderboard_rank
      ? `Du hast ${rewards.reward_points} Punkte und stehst auf Rang #${rewards.leaderboard_rank} im Leaderboard.`
      : `Du hast ${rewards.reward_points} Punkte gesammelt.`;
  } catch (err) {
    summary.textContent = `Fehler beim Laden: ${err.detail || err.message}`;
  }

  loadCars();
}

document.getElementById("profileForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = document.getElementById("profileFormMsg");
  msgEl.textContent = "";
  msgEl.classList.remove("error", "success");
  const fd = new FormData(e.target);
  try {
    const updated = await Api.updateProfile({
      full_name: fd.get("full_name"),
      nickname: fd.get("nickname") || null,
    });
    currentUser.full_name = updated.full_name;
    currentUser.nickname = updated.nickname;
    document.getElementById("userBadge").textContent = `${updated.full_name} (${updated.role === "admin" ? "Admin" : "Mitglied"})`;
    msgEl.textContent = "Gespeichert.";
    msgEl.classList.add("success");
  } catch (err) {
    msgEl.textContent = err.detail || "Speichern fehlgeschlagen.";
    msgEl.classList.add("error");
  }
});

document.querySelectorAll('input[name="leaderboardDisplay"]').forEach(radio => {
  radio.addEventListener("change", async (e) => {
    const msgEl = document.getElementById("leaderboardDisplayMsg");
    msgEl.textContent = "";
    msgEl.classList.remove("error", "success");
    try {
      await Api.setLeaderboardDisplay(e.target.value);
      msgEl.textContent = "Gespeichert.";
      msgEl.classList.add("success");
      loadProfile();
    } catch (err) {
      msgEl.textContent = err.detail || "Aktion fehlgeschlagen.";
      msgEl.classList.add("error");
      loadProfile();
    }
  });
});

/* ---------- Cars ---------- */
async function loadCars() {
  const container = document.getElementById("carsList");
  container.innerHTML = `<p class="hint-text">Lade Autos...</p>`;
  try {
    const cars = await Api.listCars();
    if (!cars.length) {
      container.innerHTML = `<p class="hint-text">Du hast noch kein Auto angelegt.</p>`;
      return;
    }
    container.innerHTML = cars.map(car => `
      <div class="car-item" data-car-id="${car.id}">
        <img class="car-item-photo" src="${car.photo_path || "/static/img/avatar-placeholder.png"}" alt="${escapeHtml(car.name)}">
        <div class="car-item-info">
          <strong>${escapeHtml(car.name)}</strong>
          ${car.brand || car.model ? `<span class="hint-text">${escapeHtml([car.brand, car.model].filter(Boolean).join(" "))}</span>` : ""}
          ${car.is_primary ? `<span class="badge-primary">Hauptauto</span>` : ""}
        </div>
        <div class="car-item-actions">
          <label class="btn btn-secondary file-upload-btn btn-sm">
            Foto
            <input type="file" class="car-photo-input" accept="image/png,image/jpeg,image/webp" hidden>
          </label>
          ${!car.is_primary ? `<button class="btn btn-secondary btn-sm car-make-primary-btn">Als Hauptauto</button>` : ""}
          <button class="btn btn-ghost btn-sm car-delete-btn">Loeschen</button>
        </div>
      </div>
    `).join("");
    attachCarHandlers();
  } catch (err) {
    container.innerHTML = `<p class="form-msg error">Fehler beim Laden: ${err.detail || err.message}</p>`;
  }
}

function attachCarHandlers() {
  document.querySelectorAll(".car-item").forEach(item => {
    const carId = item.dataset.carId;

    const photoInput = item.querySelector(".car-photo-input");
    photoInput.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (!AVATAR_ALLOWED_TYPES.includes(file.type)) {
        showToast("Nur JPEG-, PNG- oder WebP-Bilder sind erlaubt.", "error");
        e.target.value = "";
        return;
      }
      if (file.size > AVATAR_MAX_BYTES) {
        showToast("Datei ist zu gross, maximal 2 MB erlaubt.", "error");
        e.target.value = "";
        return;
      }
      try {
        await Api.uploadCarPhoto(carId, file);
        showToast("Auto-Foto aktualisiert.", "success");
        loadCars();
      } catch (err) {
        showToast(err.detail || "Upload fehlgeschlagen.", "error");
      }
    });

    const primaryBtn = item.querySelector(".car-make-primary-btn");
    if (primaryBtn) {
      primaryBtn.addEventListener("click", async () => {
        try {
          await Api.updateCar(carId, { is_primary: true });
          showToast("Hauptauto aktualisiert.", "success");
          loadCars();
        } catch (err) {
          showToast(err.detail || "Aktion fehlgeschlagen.", "error");
        }
      });
    }

    const deleteBtn = item.querySelector(".car-delete-btn");
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Dieses Auto wirklich loeschen?")) return;
      try {
        await Api.deleteCar(carId);
        showToast("Auto geloescht.", "success");
        loadCars();
      } catch (err) {
        showToast(err.detail || "Loeschen fehlgeschlagen.", "error");
      }
    });
  });
}

document.getElementById("createCarForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = document.getElementById("createCarMsg");
  msgEl.textContent = "";
  msgEl.classList.remove("error", "success");
  const fd = new FormData(e.target);
  try {
    await Api.createCar({
      name: fd.get("name"),
      brand: fd.get("brand") || null,
      model: fd.get("model") || null,
    });
    msgEl.textContent = "Auto angelegt.";
    msgEl.classList.add("success");
    e.target.reset();
    loadCars();
  } catch (err) {
    msgEl.textContent = err.detail || "Anlegen fehlgeschlagen.";
    msgEl.classList.add("error");
  }
});

document.getElementById("leaderboardOptInToggle").addEventListener("change", async (e) => {
  const msgEl = document.getElementById("leaderboardOptInMsg");
  msgEl.textContent = "";
  msgEl.classList.remove("error", "success");
  try {
    const rewards = await Api.setLeaderboardOptIn(e.target.checked);
    msgEl.textContent = rewards.leaderboard_opt_in
      ? "Du bist jetzt auf dem Leaderboard sichtbar."
      : "Du bist nicht mehr auf dem Leaderboard sichtbar.";
    msgEl.classList.add("success");
  } catch (err) {
    e.target.checked = !e.target.checked;
    msgEl.textContent = err.detail || "Aktion fehlgeschlagen.";
    msgEl.classList.add("error");
  }
});

const AVATAR_MAX_BYTES = 2 * 1024 * 1024;
const AVATAR_ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

document.getElementById("avatarFileInput").addEventListener("change", async (e) => {
  const msgEl = document.getElementById("avatarMsg");
  msgEl.textContent = "";
  msgEl.classList.remove("error", "success");

  const file = e.target.files[0];
  if (!file) return;

  // Client-seitige Vorabpruefung fuer schnelles Feedback. Die eigentliche,
  // massgebliche Pruefung von Dateityp, Groesse und Bildinhalt erfolgt serverseitig.
  if (!AVATAR_ALLOWED_TYPES.includes(file.type)) {
    msgEl.textContent = "Nur JPEG-, PNG- oder WebP-Bilder sind erlaubt.";
    msgEl.classList.add("error");
    e.target.value = "";
    return;
  }
  if (file.size > AVATAR_MAX_BYTES) {
    msgEl.textContent = "Datei ist zu gross, maximal 2 MB erlaubt.";
    msgEl.classList.add("error");
    e.target.value = "";
    return;
  }

  msgEl.textContent = "Bild wird hochgeladen...";
  try {
    const result = await Api.uploadAvatar(file);
    document.getElementById("profileAvatarPreview").src = result.avatar_path;
    if (currentUser) currentUser.avatar_path = result.avatar_path;
    msgEl.textContent = "Profilbild erfolgreich aktualisiert.";
    msgEl.classList.add("success");
  } catch (err) {
    msgEl.textContent = err.detail || "Upload fehlgeschlagen.";
    msgEl.classList.add("error");
  } finally {
    e.target.value = "";
  }
});
