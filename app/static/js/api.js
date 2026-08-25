/* GFS shared frontend helpers - loaded by /app and /admin pages */
(function () {
  "use strict";

  var SESSION_KEY = "gfs_session";
  var USER_KEY = "gfs_user";

  function formatDt(value) {
    if (!value) return "-";
    var iso = value.endsWith("Z") || value.indexOf("+") >= 0 ? value : value + "Z";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return value;
    return d.toLocaleString();
  }

  function statusPill(status) {
    var safe = String(status).replace(/\s+/g, "-");
    return '<span class="status-pill status-' + safe + '">' + status + "</span>";
  }

  var api = {
    getToken: function () {
      return localStorage.getItem(SESSION_KEY);
    },
    getUser: function () {
      var raw = localStorage.getItem(USER_KEY);
      if (!raw) return null;
      try {
        return JSON.parse(raw);
      } catch (e) {
        return null;
      }
    },
    setSession: function (token, user) {
      localStorage.setItem(SESSION_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    },
    clearSession: function () {
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(USER_KEY);
    },
    isManagerPortal: function (user) {
      return user && (user.Role === "Manager" || user.Role === "Admin");
    },
    request: function (path, options) {
      options = options || {};
      var headers = Object.assign({}, options.headers || {});
      var token = this.getToken();
      if (token) headers["X-Session-Token"] = token;
      if (options.body && !(options.body instanceof FormData)) {
        headers["Content-Type"] = "application/json";
      }
      return fetch(path, {
        method: options.method || "GET",
        headers: headers,
        body: options.body,
      }).then(function (res) {
        return res.text().then(function (text) {
          var data = null;
          try {
            data = text ? JSON.parse(text) : null;
          } catch (e) {
            data = { detail: text };
          }
          if (!res.ok) {
            var detail = data && data.detail;
            var msg = "Request failed";
            if (typeof detail === "string") msg = detail;
            else if (Array.isArray(detail))
              msg = detail.map(function (d) {
                return d.msg || JSON.stringify(d);
              }).join("; ");
            else if (detail) msg = JSON.stringify(detail);
            var err = new Error(msg);
            err.status = res.status;
            err.data = data;
            throw err;
          }
          return data;
        });
      });
    },
    get: function (path) {
      return this.request(path);
    },
    post: function (path, body) {
      return this.request(path, { method: "POST", body: JSON.stringify(body) });
    },
    requireAuth: function (opts) {
      opts = opts || {};
      var user = this.getUser();
      if (!user || !this.getToken()) {
        window.location.href = "/login.html";
        return null;
      }
      if (opts.managerOnly && !this.isManagerPortal(user)) {
        alert("Manager or Admin access required.");
        window.location.href = "/app/index.html";
        return null;
      }
      return user;
    },
  };

  function renderHeader(active, portal) {
    var user = api.getUser();
    var brand =
      '<div class="brand">' +
      '<img src="/static/img/logo.png" alt="Standard Bank" />' +
      '<div class="brand-text"><strong>GFS Vehicle Management</strong>' +
      "<span>Group Forensic Services</span></div></div>";
    var links = "";
    if (portal === "admin") {
      links =
        '<a href="/admin/index.html"' + (active === "dash" ? ' class="active"' : "") + ">Dashboard</a>" +
        '<a href="/admin/approvals.html"' + (active === "approvals" ? ' class="active"' : "") + ">Approvals</a>" +
        '<a href="/admin/keys.html"' + (active === "keys" ? ' class="active"' : "") + ">Keys</a>" +
        '<a href="/admin/incidents.html"' + (active === "incidents" ? ' class="active"' : "") + ">Incidents</a>" +
        '<a href="/admin/analytics.html"' + (active === "analytics" ? ' class="active"' : "") + ">Analytics</a>" +
        '<a href="/admin/vehicles.html"' + (active === "vehicles" ? ' class="active"' : "") + ">Vehicles</a>" +
        '<a href="/admin/emails.html"' + (active === "emails" ? ' class="active"' : "") + ">Sent Emails</a>" +
        '<a href="/admin/audit.html"' + (active === "audit" ? ' class="active"' : "") + ">Audit Log</a>";
    } else if (portal === "app") {
      links =
        '<a href="/app/index.html"' + (active === "home" ? ' class="active"' : "") + ">Vehicles</a>" +
        '<a href="/app/request.html"' + (active === "request" ? ' class="active"' : "") + ">Request</a>" +
        '<a href="/app/trips.html"' + (active === "trips" ? ' class="active"' : "") + ">My Trips</a>" +
        '<a href="/app/checkout.html"' + (active === "checkout" ? ' class="active"' : "") + ">Check-Out</a>" +
        '<a href="/app/checkin.html"' + (active === "checkin" ? ' class="active"' : "") + ">Check-In</a>";
    }
    var portalSwitch =
      user && api.isManagerPortal(user)
        ? '<a href="/admin/index.html">Admin</a><a href="/app/index.html">Employee app</a>'
        : "";
    return (
      '<header class="gfs-header mb-4"><div class="container py-3 d-flex flex-wrap justify-content-between align-items-center gap-3">' +
      brand +
      '<nav class="gfs-nav d-flex flex-wrap gap-1 align-items-center">' +
      links +
      portalSwitch +
      "</nav>" +
      '<div class="d-flex align-items-center gap-2"><span class="small">' +
      (user ? user.DisplayName + " · " + user.Role : "") +
      '</span><button class="btn btn-sm btn-light" type="button" id="logoutBtn">Log out</button></div></div></header>'
    );
  }

  function wireLogout() {
    var btn = document.getElementById("logoutBtn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      api.post("/api/auth/logout", {}).catch(function () {});
      api.clearSession();
      window.location.href = "/login.html";
    });
  }

  /** Call page setup after DOM is ready. Shows errors instead of failing silently. */
  function ready(fn) {
    function run() {
      if (!window.GFS || !window.GFS.api) {
        var errEl = document.getElementById("err");
        var msg = "App scripts failed to load. Hard refresh: Ctrl+Shift+R";
        if (errEl) errEl.textContent = msg;
        else alert(msg);
        return;
      }
      try {
        fn(window.GFS);
      } catch (e) {
        var el = document.getElementById("err");
        var text = e.message || String(e);
        if (el) el.textContent = text;
        else alert(text);
      }
    }
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", run);
    } else {
      run();
    }
  }

  window.GFS = {
    api: api,
    formatDt: formatDt,
    statusPill: statusPill,
    renderHeader: renderHeader,
    wireLogout: wireLogout,
    ready: ready,
  };
})();
