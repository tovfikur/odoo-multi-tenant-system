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
  if (document.getElementById("log-timeline")) {
    // Wait a bit for window.tenantId to be set by the template script
    setTimeout(() => {
      if (window.tenantId) {
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
      } else {
        console.error("Tenant ID is undefined in manage_tenant.html");
        AppUtils.showNotification("Error: Tenant ID not found", "danger");
      }
    }, 100); // Small delay to allow template script to run first
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
  if (typeof io === "undefined") {
    console.warn("Socket.io not available, disabling real-time features");
    return;
  }

  try {
    socket = io.connect(window.location.origin, {
      transports: ["polling", "websocket"],
      upgrade: true,
      rememberUpgrade: false,
      timeout: 20000,
      forceNew: true,
    });

    socket.on("connect", () => {
      console.log("Connected to SocketIO");
      socket.emit("join", `tenant_${tenantId}`);
    });

    socket.on("connect_error", (error) => {
      console.warn("Socket.io connection error:", error);
      // Fallback to polling only
      socket.io.opts.transports = ["polling"];
    });

    socket.on("new_log", (log) => {
      filteredLogs.unshift(log);
      filteredLogs = filteredLogs.slice(0, 1000);
      filterLogs();
    });

    socket.on("stats_update", (stats) => {
      updateStats(stats);
    });
  } catch (error) {
    console.error("Failed to initialize Socket.io:", error);
    AppUtils.showNotification("Real-time updates unavailable", "warning");
  }
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
  const totalLogs = document.getElementById("total-logs");
  const errorCount = document.getElementById("error-count");
  const warningCount = document.getElementById("warning-count");
  const infoCount = document.getElementById("info-count");
  const successCount = document.getElementById("success-count");
  const lastUpdate = document.getElementById("last-update");
  
  if (totalLogs) totalLogs.textContent = stats.total || 0;
  if (errorCount) errorCount.textContent = stats.error || 0;
  if (warningCount) warningCount.textContent = stats.warning || 0;
  if (infoCount) infoCount.textContent = stats.info || 0;
  if (successCount) successCount.textContent = stats.success || 0;
  if (lastUpdate) lastUpdate.textContent = new Date(
    stats.last_update || Date.now()
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

links.forEach((link) => {
  // Check if this link has a tenant ID for SSO
  const tenantId = link.dataset.tenantId;
  
  if (tenantId) {
    // Use SSO endpoint for authenticated users
    link.href = `/sso/tenant/${tenantId}`;
    link.removeAttribute('target'); // Don't open in new tab for SSO
  } else {
    // Fallback to direct tenant URL for legacy links
    const tenantDb = link.dataset.tenantDb;
    if (tenantDb) {
      const host = window.location.hostname;
      const port = window.location.port;
      const protocol = window.location.protocol;
      const subdomain = tenantDb + "." + host;
      const fullHost = port ? `${subdomain}:${port}` : subdomain;
      const url = `${protocol}//${fullHost}`;
      link.href = url;
    }
  }
});

document.body.innerHTML = document.body.innerHTML.replace(
  /<domain>/g,
  window.location.host
);

// ===== BEAUTIFUL CTA ANIMATIONS =====

// Intersection Observer for CTA animations
const observeCTAAnimations = () => {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate-in');
        
        // Animate feature badges with stagger
        const featureBadges = entry.target.querySelectorAll('.feature-badge');
        featureBadges.forEach((badge, index) => {
          setTimeout(() => {
            badge.style.opacity = '0';
            badge.style.transform = 'translateY(20px)';
            badge.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
            
            requestAnimationFrame(() => {
              badge.style.opacity = '1';
              badge.style.transform = 'translateY(0)';
            });
          }, index * 150);
        });
        
        observer.unobserve(entry.target);
      }
    });
  }, {
    threshold: 0.3,
    rootMargin: '-50px'
  });

  const ctaCards = document.querySelectorAll('.cta-card-modern');
  ctaCards.forEach(card => observer.observe(card));
};

// Enhanced button interactions
const initCTAButtonEffects = () => {
  const ctaButtons = document.querySelectorAll('.btn-cta-primary, .btn-cta-secondary');
  
  ctaButtons.forEach(button => {
    // Add click ripple effect
    button.addEventListener('click', function(e) {
      const ripple = this.querySelector('.btn-ripple');
      if (ripple) {
        ripple.style.width = '0';
        ripple.style.height = '0';
        
        setTimeout(() => {
          ripple.style.width = '300px';
          ripple.style.height = '300px';
        }, 10);
        
        setTimeout(() => {
          ripple.style.width = '0';
          ripple.style.height = '0';
        }, 600);
      }
    });
    
    // Add hover sound effect (optional - can be disabled)
    button.addEventListener('mouseenter', function() {
      // Subtle vibration on mobile devices
      if ('vibrate' in navigator) {
        navigator.vibrate(50);
      }
    });
  });
};

// Fix white CTA sections for dark mode compatibility
const fixWhiteCTASections = () => {
  // Find all bg-light cards that might be CTA sections
  const potentialCTACards = document.querySelectorAll('.card.bg-light, .bg-light');
  
  potentialCTACards.forEach(card => {
    const cardBody = card.querySelector('.card-body') || card;
    
    // Check if this card contains CTA-like content
    const hasCTAContent = (
      cardBody.textContent.includes('Ready to Transform') ||
      cardBody.textContent.includes('Start Free Trial') ||
      cardBody.textContent.includes('Contact Sales') ||
      cardBody.querySelector('[href*="register"]') ||
      cardBody.querySelector('[href*="contact"]') ||
      cardBody.querySelector('[href*="trial"]') ||
      cardBody.querySelector('.btn-primary') ||
      cardBody.querySelector('.btn-outline-primary')
    );
    
    if (hasCTAContent) {
      console.log('🎨 Found CTA section, applying beautiful styles...');
      
      // Remove the problematic bg-light class
      card.classList.remove('bg-light');
      
      // Add our beautiful CTA class
      card.classList.add('cta-card-beautiful');
      
      // Apply styles immediately for better UX
      card.style.background = 'linear-gradient(135deg, var(--primary) 0%, var(--secondary) 50%, var(--support) 100%)';
      card.style.border = '1px solid rgba(255, 255, 255, 0.1)';
      card.style.borderRadius = '24px';
      card.style.color = 'white';
      card.style.position = 'relative';
      card.style.overflow = 'hidden';
      
      // Check for dark mode
      const isDarkMode = document.documentElement.getAttribute('data-theme') === 'dark' || 
                        document.body.classList.contains('dark-mode');
      
      if (isDarkMode) {
        card.style.background = 'linear-gradient(135deg, rgba(26, 115, 232, 0.8) 0%, rgba(0, 191, 165, 0.8) 50%, rgba(155, 81, 224, 0.8) 100%)';
        card.style.backdropFilter = 'blur(20px)';
        card.style.webkitBackdropFilter = 'blur(20px)';
      }
      
      // Fix text colors
      const headings = cardBody.querySelectorAll('h1, h2, h3, h4, h5, h6');
      headings.forEach(heading => {
        heading.style.color = 'white';
        heading.style.fontWeight = '700';
        heading.style.textShadow = '0 2px 20px rgba(0, 0, 0, 0.3)';
      });
      
      const paragraphs = cardBody.querySelectorAll('p, .text-muted');
      paragraphs.forEach(p => {
        p.style.color = 'rgba(255, 255, 255, 0.9)';
        p.style.textShadow = '0 1px 10px rgba(0, 0, 0, 0.2)';
      });
      
      // Fix button styles
      const primaryBtns = cardBody.querySelectorAll('.btn-primary');
      primaryBtns.forEach(btn => {
        btn.style.background = 'rgba(255, 255, 255, 0.95)';
        btn.style.color = 'var(--primary)';
        btn.style.border = 'none';
        btn.style.boxShadow = '0 8px 32px rgba(255, 255, 255, 0.3), 0 4px 16px rgba(0, 0, 0, 0.1)';
        btn.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        btn.style.borderRadius = '50px';
        btn.style.fontWeight = '600';
        
        btn.addEventListener('mouseenter', () => {
          btn.style.background = 'white';
          btn.style.transform = 'translateY(-4px) scale(1.05)';
          btn.style.boxShadow = '0 12px 48px rgba(255, 255, 255, 0.4), 0 8px 24px rgba(0, 0, 0, 0.15)';
        });
        
        btn.addEventListener('mouseleave', () => {
          btn.style.background = 'rgba(255, 255, 255, 0.95)';
          btn.style.transform = 'translateY(0) scale(1)';
          btn.style.boxShadow = '0 8px 32px rgba(255, 255, 255, 0.3), 0 4px 16px rgba(0, 0, 0, 0.1)';
        });
      });
      
      const outlineBtns = cardBody.querySelectorAll('.btn-outline-primary');
      outlineBtns.forEach(btn => {
        btn.style.background = 'rgba(255, 255, 255, 0.1)';
        btn.style.color = 'white';
        btn.style.border = '2px solid rgba(255, 255, 255, 0.3)';
        btn.style.boxShadow = '0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 2px rgba(255, 255, 255, 0.1)';
        btn.style.borderRadius = '50px';
        btn.style.fontWeight = '600';
        
        btn.addEventListener('mouseenter', () => {
          btn.style.background = 'rgba(255, 255, 255, 0.2)';
          btn.style.borderColor = 'rgba(255, 255, 255, 0.5)';
          btn.style.transform = 'translateY(-4px) scale(1.05)';
          btn.style.boxShadow = '0 12px 48px rgba(0, 0, 0, 0.15), inset 0 2px 4px rgba(255, 255, 255, 0.2)';
        });
        
        btn.addEventListener('mouseleave', () => {
          btn.style.background = 'rgba(255, 255, 255, 0.1)';
          btn.style.borderColor = 'rgba(255, 255, 255, 0.3)';
          btn.style.transform = 'translateY(0) scale(1)';
          btn.style.boxShadow = '0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 2px rgba(255, 255, 255, 0.1)';
        });
      });
      
      // Add floating animation background
      const bgPattern = document.createElement('div');
      bgPattern.style.position = 'absolute';
      bgPattern.style.top = '0';
      bgPattern.style.left = '0';
      bgPattern.style.right = '0';
      bgPattern.style.bottom = '0';
      bgPattern.style.backgroundImage = `
        radial-gradient(circle at 25% 25%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
        radial-gradient(circle at 75% 75%, rgba(255, 255, 255, 0.05) 0%, transparent 50%)
      `;
      bgPattern.style.animation = 'float 6s ease-in-out infinite';
      bgPattern.style.pointerEvents = 'none';
      bgPattern.style.zIndex = '1';
      
      card.insertBefore(bgPattern, card.firstChild);
      
      // Ensure content is above background
      if (cardBody) {
        cardBody.style.position = 'relative';
        cardBody.style.zIndex = '2';
      }
      
      console.log('✅ CTA section successfully beautified!');
    }
  });
};

// Watch for theme changes and reapply fixes
const watchThemeChanges = () => {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && 
          (mutation.attributeName === 'data-theme' || 
           mutation.attributeName === 'class')) {
        setTimeout(fixWhiteCTASections, 100);
      }
    });
  });
  
  observer.observe(document.documentElement, { 
    attributes: true, 
    attributeFilter: ['data-theme', 'class'] 
  });
  
  observer.observe(document.body, { 
    attributes: true, 
    attributeFilter: ['class'] 
  });
};

// Initialize all CTA effects when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  observeCTAAnimations();
  initCTAButtonEffects();
  
  // Fix any white CTA sections
  setTimeout(fixWhiteCTASections, 500); // Small delay to ensure all CSS is loaded
  
  // Watch for theme changes
  watchThemeChanges();
  
  console.log('🎨 CTA beautification system initialized');
});

// Add smooth scroll for CTA buttons if they link to anchors
document.addEventListener('click', (e) => {
  const link = e.target.closest('.btn-cta-primary, .btn-cta-secondary');
  if (link && link.getAttribute('href').startsWith('#')) {
    e.preventDefault();
    const target = document.querySelector(link.getAttribute('href'));
    if (target) {
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }
  }
});
