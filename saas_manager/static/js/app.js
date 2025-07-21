// app.js
// Global JavaScript for Odoo SaaS Platform

// Utility functions
const AppUtils = {
  showNotification(message, type = "info", duration = 5000) {
    const toast = document.createElement("div");
    toast.className = `alert alert-${type} alert-dismissible fade show fixed-top m-3`;
    toast.style.zIndex = "2000";
    toast.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },

  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  },

  async fetchJSON(url, options = {}) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      return data;
    } catch (error) {
      console.error("Fetch error:", error);
      AppUtils.showNotification(`Error: ${error.message}`, "danger");
      throw error;
    }
  },
};

// Global event listeners
document.addEventListener("DOMContentLoaded", () => {
  const tooltipTriggerList = document.querySelectorAll(
    '[data-bs-toggle="tooltip"]'
  );
  [...tooltipTriggerList].forEach((tooltipTriggerEl) => {
    new bootstrap.Tooltip(tooltipTriggerEl);
  });

  const alerts = document.querySelectorAll(".alert-dismissible");
  alerts.forEach((alert) => {
    setTimeout(() => {
      alert.classList.remove("show");
      setTimeout(() => alert.remove(), 300);
    }, 5000);
  });

  const searchInputs = document.querySelectorAll(
    "#searchUsers, #searchTenants, #searchWorkers"
  );
  searchInputs.forEach((input) => {
    input.addEventListener(
      "input",
      AppUtils.debounce(() => {
        if (input.id === "searchUsers") filterUsers?.();
        if (input.id === "searchTenants") filterTable?.();
        if (input.id === "searchWorkers") filterWorkers?.();
      }, 300)
    );
  });

  const sidebarToggle = document.querySelector(".sidebar-toggle");
  const sidebar = document.querySelector(".sidebar");
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", () => {
      sidebar.classList.toggle("active");
    });
  }

  const statsCards = document.querySelectorAll(".card.text-white");
  if (
    statsCards.length &&
    document.querySelector("body").dataset.isAdmin === "true"
  ) {
    setInterval(async () => {
      try {
        const stats = await AppUtils.fetchJSON("/api/admin/stats");
        document.querySelector(".card.bg-primary h4").textContent =
          stats.total_tenants;
        document.querySelector(".card.bg-success h4").textContent =
          stats.active_tenants;
        document.querySelector(".card.bg-info h4").textContent =
          stats.total_users;
        document.querySelector(".card.bg-warning h4").textContent =
          stats.worker_instances;
      } catch (error) {}
    }, 60000);
  }

  // Tenant-specific initialization (only for manage_tenant.html)
  if (document.getElementById("log-timeline") && window.tenantId) {
    fetchLogs(window.tenantId)
      .then(() => {
        filterLogs();
        initSocketIO(window.tenantId);
      })
      .catch(() => {
        console.error("Failed to initialize tenant logs");
        AppUtils.showNotification(
          "Error: Failed to load tenant logs",
          "danger"
        );
      });
  } else if (document.getElementById("log-timeline")) {
    console.error("Tenant ID is undefined in manage_tenant.html");
    AppUtils.showNotification("Error: Tenant ID not found", "danger");
  }
});

window.getAdminStats = async () => {
  return AppUtils.fetchJSON("/api/admin/stats");
};

window.AppUtils = AppUtils;

let filteredLogs = [];
let currentServiceFilter = "all";
let currentLevelFilter = "all";
let searchQuery = "";
let socket;

async function fetchLogs(tenantId) {
  try {
    const data = await AppUtils.fetchJSON(
      `/api/tenant/${tenantId}/logs?include_db_logs=true`,
      {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("auth_token")}`,
        },
      }
    );
    filteredLogs = data.logs;
    updateStats(data.stats);
    return data.logs;
  } catch (error) {
    console.error("Error fetching logs:", error);
    return [];
  }
}

function initSocketIO(tenantId) {
  socket = io.connect(window.location.origin);
  socket.on("connect", () => {
    console.log("Connected to SocketIO");
    socket.emit("join", `tenant_${tenantId}`);
  });
  socket.on("new_log", (log) => {
    filteredLogs.unshift(log);
    filteredLogs = filteredLogs.slice(0, 1000);
    filterLogs();
  });
  socket.on("stats_update", (stats) => {
    updateStats(stats);
  });
}

function formatTimeAgo(timestamp) {
  const now = new Date();
  const logDate = new Date(timestamp);
  const diffInMs = now - logDate;
  const diffInMinutes = Math.floor(diffInMs / (1000 * 60));
  const diffInHours = Math.floor(diffInMs / (1000 * 60 * 60));
  const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24));

  if (isNaN(logDate)) return "Invalid timestamp";
  if (diffInMinutes < 1) return "just now";
  if (diffInMinutes < 60)
    return `${diffInMinutes} minute${diffInMinutes > 1 ? "s" : ""} ago`;
  if (diffInHours < 24)
    return `${diffInHours} hour${diffInHours > 1 ? "s" : ""} ago`;
  return `${diffInDays} day${diffInDays > 1 ? "s" : ""} ago`;
}

function getServiceBadgeClass(service) {
  const serviceClasses = {
    "odoomulti-tenantsystem-odoo_master-1": "bg-primary",
    "odoomulti-tenantsystem-odoo_worker1-1": "bg-info",
    postgres: "bg-warning text-dark",
    nginx: "bg-danger",
  };
  return serviceClasses[service] || "bg-secondary";
}

function getLevelIcon(level) {
  const levelIcons = {
    error: "fas fa-exclamation-circle",
    warning: "fas fa-exclamation-triangle",
    info: "fas fa-info-circle",
    debug: "fas fa-bug",
    success: "fas fa-check-circle",
  };
  return levelIcons[level] || "fas fa-circle";
}

function renderLogs() {
  const timeline = document.getElementById("log-timeline");
  timeline.innerHTML = "";

  if (filteredLogs.length === 0) {
    timeline.innerHTML =
      '<div class="text-center text-muted py-4"><i class="fas fa-search fa-2x mb-2"></i><br>No logs found matching your criteria</div>';
    return;
  }

  filteredLogs.forEach((log) => {
    const timelineItem = document.createElement("div");
    timelineItem.className = `timeline-item log-level-${log.level}`;
    timelineItem.innerHTML = `
      <div class="timeline-marker"></div>
      <div class="timeline-content">
        <div class="d-flex justify-content-between align-items-start mb-2">
          <h6 class="timeline-title mb-0">
            <i class="${getLevelIcon(log.level)} me-2"></i>
            ${log.title}
          </h6>
          <span class="badge log-service-badge ${getServiceBadgeClass(
            log.service
          )}">${log.service
      .replace("odoomulti-tenantsystem-", "")
      .replace("-1", "")}</span>
        </div>
        <p class="timeline-text text-muted mb-2">${log.message}</p>
        <div class="d-flex justify-content-between align-items-center">
          <small class="text-muted">${formatTimeAgo(log.timestamp)}</small>
          <button class="btn btn-sm btn-outline-secondary toggle-details" data-log-id="${
            log.id
          }">
            <i class="fas fa-chevron-down"></i> Details
          </button>
        </div>
        <div class="log-detail" id="details-${log.id}" style="display: none;">
          <pre>${log.details || "No additional details"}</pre>
        </div>
      </div>
    `;
    timeline.appendChild(timelineItem);
  });

  document.querySelectorAll(".toggle-details").forEach((btn) => {
    btn.addEventListener("click", function () {
      const logId = this.dataset.logId;
      const details = document.getElementById(`details-${logId}`);
      const icon = this.querySelector("i");
      if (details.style.display === "none") {
        details.style.display = "block";
        icon.className = "fas fa-chevron-up";
        this.innerHTML = '<i class="fas fa-chevron-up"></i> Hide';
      } else {
        details.style.display = "none";
        icon.className = "fas fa-chevron-down";
        this.innerHTML = '<i class="fas fa-chevron-down"></i> Details';
      }
    });
  });
}

function updateStats(stats) {
  document.getElementById("total-logs").textContent = stats.total || 0;
  document.getElementById("error-count").textContent = stats.error || 0;
  document.getElementById("warning-count").textContent = stats.warning || 0;
  document.getElementById("info-count").textContent = stats.info || 0;
  document.getElementById("success-count").textContent = stats.success || 0;
  document.getElementById("last-update").textContent = new Date(
    stats.last_update
  ).toLocaleTimeString();
}

function renderAlerts() {
  const alertsContainer = document.getElementById("alerts-container");
  const criticalLogs = filteredLogs.filter(
    (log) => log.level === "error" || log.level === "warning"
  );

  if (criticalLogs.length === 0) {
    alertsContainer.innerHTML =
      '<div class="text-muted text-center py-3"><i class="fas fa-check-circle me-2"></i>No critical alerts</div>';
    return;
  }

  alertsContainer.innerHTML = criticalLogs
    .slice(0, 3)
    .map((log) => {
      const alertClass =
        log.level === "error" ? "alert-danger" : "alert-warning";
      const icon =
        log.level === "error"
          ? "fas fa-exclamation-circle"
          : "fas fa-exclamation-triangle";
      return `
      <div class="alert ${alertClass} alert-sm" role="alert">
        <i class="${icon} me-2"></i>
        <strong>${log.title}:</strong> ${log.message}
        <small class="d-block mt-1 opacity-75">${formatTimeAgo(
          log.timestamp
        )}</small>
      </div>
    `;
    })
    .join("");
}

function renderServiceStatus() {
  const serviceStatus = document.getElementById("service-status");
  const services = Array.from(new Set(filteredLogs.map((log) => log.service)));

  if (services.length === 0) {
    serviceStatus.innerHTML =
      '<div class="text-muted text-center py-3"><i class="fas fa-info-circle me-2"></i>No service status available</div>';
    return;
  }

  serviceStatus.innerHTML = services
    .map((service) => {
      const hasErrors = filteredLogs.some(
        (log) => log.service === service && log.level === "error"
      );
      const statusClass = hasErrors ? "text-danger" : "text-success";
      const statusIcon = hasErrors
        ? "fas fa-times-circle"
        : "fas fa-check-circle";
      const statusText = hasErrors ? "Issues" : "Healthy";
      return `
      <div class="d-flex justify-content-between align-items-center mb-2">
        <span>${service
          .replace("odoomulti-tenantsystem-", "")
          .replace("-1", "")
          .toUpperCase()}</span>
        <span class="${statusClass}">
          <i class="${statusIcon}"></i> ${statusText}
        </span>
      </div>
    `;
    })
    .join("");
}

function filterLogs() {
  const filtered = filteredLogs.filter((log) => {
    const serviceMatch =
      currentServiceFilter === "all" ||
      log.service.includes(currentServiceFilter);
    const levelMatch =
      currentLevelFilter === "all" || log.level === currentLevelFilter;
    const searchMatch =
      searchQuery === "" ||
      log.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.service.toLowerCase().includes(searchQuery.toLowerCase());
    return serviceMatch && levelMatch && searchMatch;
  });

  filteredLogs = filtered;
  renderLogs();
  renderAlerts();
  renderServiceStatus();
}

document.querySelectorAll(".service-filter").forEach((btn) => {
  btn.addEventListener("click", function () {
    document
      .querySelectorAll(".service-filter")
      .forEach((b) => b.classList.remove("active"));
    this.classList.add("active");
    currentServiceFilter = this.dataset.service;
    filterLogs();
  });
});

document.querySelectorAll(".log-level-filter").forEach((btn) => {
  btn.addEventListener("click", function (e) {
    e.preventDefault();
    currentLevelFilter = this.dataset.level;
    filterLogs();
  });
});

document.getElementById("log-search")?.addEventListener("input", function () {
  searchQuery = this.value;
  filterLogs();
});

document
  .getElementById("refresh-logs")
  ?.addEventListener("click", async function () {
    if (document.getElementById("log-timeline") && window.tenantId) {
      await fetchLogs(window.tenantId);
      filterLogs();
    } else if (document.getElementById("log-timeline")) {
      console.error("Tenant ID is undefined. Cannot refresh logs.");
      AppUtils.showNotification("Error: Tenant ID not found", "danger");
    }
  });

const links = document.querySelectorAll(".tenant-link");

const host = window.location.hostname; // e.g. "localhost"
const port = window.location.port; // e.g. "5000"
const protocol = window.location.protocol; // "http:" or "https:"

links.forEach((link) => {
  const tenantDb = link.dataset.tenantDb;
  const subdomain = tenantDb + "." + host;
  const fullHost = port ? `${subdomain}:${port}` : subdomain;
  const url = `${protocol}//${fullHost}`;

  link.href = url;
});

document.body.innerHTML = document.body.innerHTML.replace(
  /<domain>/g,
  window.location.host
);
