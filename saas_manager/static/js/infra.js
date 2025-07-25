/**
 * Infrastructure Admin Dashboard JavaScript
 * Clean, modular, and complete implementation
 */

const InfraAdmin = {
  // Configuration
  config: {
    refreshInterval: 30000, // 30 seconds
    apiBase: "/infra-admin/api",
    pollInterval: 2000, // 2 seconds for task polling
  },

  // State management
  state: {
    monitoringActive: false,
    selectedDeploymentId: null,
    selectedServerId: null,
    refreshInterval: null,
    discoveredMachines: [],
  },

  // Initialize dashboard
  init() {
    this.setupEventListeners();
    this.loadInitialData();
    this.startAutoRefresh();
    console.log("Infrastructure Admin Dashboard initialized");
  },

  // Setup all event listeners
  setupEventListeners() {
    // Form submissions
    document
      .getElementById("addServerForm")
      ?.addEventListener("submit", this.handleAddServer.bind(this));
    document
      .getElementById("addDomainForm")
      ?.addEventListener("submit", this.handleAddDomain.bind(this));
    document
      .getElementById("networkScanForm")
      ?.addEventListener("submit", this.handleNetworkScan.bind(this));
    document
      .getElementById("createDeploymentForm")
      ?.addEventListener("submit", this.handleCreateDeployment.bind(this));

    // Authentication method toggle
    document.querySelectorAll('input[name="authMethod"]').forEach((radio) => {
      radio.addEventListener("change", this.toggleAuthMethod.bind(this));
    });

    // Deployment type change
    document
      .getElementById("deploymentType")
      ?.addEventListener("change", this.handleDeploymentTypeChange.bind(this));

    // Tab changes
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach((tab) => {
      tab.addEventListener("shown.bs.tab", this.handleTabChange.bind(this));
    });

    // Cleanup on page unload
    window.addEventListener("beforeunload", this.cleanup.bind(this));
  },

  // Load initial data for all tabs
  loadInitialData() {
    this.loadOverviewData();
    this.loadServers();
    this.loadDomains();
    this.loadDeployments();
    this.loadAlerts();
  },

  // Start auto-refresh
  startAutoRefresh() {
    this.state.refreshInterval = setInterval(() => {
      this.loadOverviewData();
      if (this.state.monitoringActive) {
        this.loadAlerts();
      }
    }, this.config.refreshInterval);
  },

  // API helper function
  async apiCall(endpoint, options = {}) {
    try {
      const response = await fetch(`${this.config.apiBase}${endpoint}`, {
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API call failed: ${endpoint}`, error);
      this.showNotification(`API Error: ${error.message}`, "error");
      throw error;
    }
  },

  // Show notification
  showNotification(message, type = "info", duration = 5000) {
    if (window.showNotification) {
      window.showNotification(message, type, duration);
    } else {
      console.log(`${type.toUpperCase()}: ${message}`);
    }
  },

  // Overview Data Management
  async loadOverviewData() {
    try {
      const data = await this.apiCall("/status/overview");
      if (data.success) {
        this.updateOverviewCards(data.infrastructure_status);
      }
    } catch (error) {
      console.error("Failed to load overview data:", error);
    }
  },

  updateOverviewCards(status) {
    // Update server metrics
    this.updateElement("totalServers", status.servers.total);
    this.updateElement("activeServersText", `${status.servers.active} active`);
    this.updateProgressBar(
      "activeServersProgress",
      status.servers.health_percentage
    );

    // Update domain metrics
    this.updateElement("totalDomains", status.domains.total);
    this.updateElement("activeDomainsText", `${status.domains.active} active`);
    const domainProgress =
      status.domains.total > 0
        ? (status.domains.active / status.domains.total) * 100
        : 0;
    this.updateProgressBar("activeDomainProgress", domainProgress);

    // Update deployment metrics
    this.updateElement("activeDeployments", status.deployments.recent_24h);

    // Update alert metrics
    this.updateElement("activeAlerts", status.alerts.active);
    this.updateElement(
      "criticalAlertsText",
      `${status.alerts.critical} critical`
    );

    // Update alert status indicator
    const alertsStatus = document.getElementById("alertsStatus");
    if (alertsStatus) {
      if (status.alerts.critical > 0) {
        alertsStatus.className = "status-indicator status-critical";
      } else if (status.alerts.active > 0) {
        alertsStatus.className = "status-indicator status-warning";
      } else {
        alertsStatus.className = "status-indicator status-healthy";
      }
    }

    // Update server health chart
    this.updateServerHealthChart(status.servers);
  },

  updateServerHealthChart(servers) {
    const healthPercentage = servers.health_percentage || 0;
    const chart = document.getElementById("serverHealthChart");
    const text = chart?.querySelector(".circular-progress-text");

    if (chart && text) {
      text.textContent = `${Math.round(healthPercentage)}%`;
      const color =
        healthPercentage >= 80
          ? "var(--success)"
          : healthPercentage >= 60
          ? "var(--warning)"
          : "var(--danger)";
      chart.style.background = `conic-gradient(${color} ${
        healthPercentage * 3.6
      }deg, var(--bg-tertiary) 0deg)`;
    }

    this.updateElement("activeServersCount", servers.active);
    this.updateElement("failedServersCount", servers.failed);
  },

  // Server Management
  async loadServers() {
    try {
      const data = await this.apiCall("/servers/list");
      if (data.success) {
        this.updateServersTable(data.servers);
        this.populateServerSelects(data.servers);
      }
    } catch (error) {
      this.showErrorInTable("serversTableBody", "Failed to load servers", 5);
    }
  },

  updateServersTable(servers) {
    const tbody = document.getElementById("serversTableBody");
    if (!tbody) return;

    if (servers.length === 0) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-4 text-muted">
                        <i class="fas fa-server fa-2x mb-3"></i>
                        <p>No servers configured yet. Add your first server to get started.</p>
                    </td>
                </tr>
            `;
      return;
    }

    tbody.innerHTML = servers
      .map(
        (server) => `
            <tr onclick="showServerDetails(${
              server.id
            })" style="cursor: pointer;">
                <td>
                    <div class="d-flex align-items-center">
                        <div class="status-indicator status-${
                          server.status === "active" ? "healthy" : "critical"
                        } me-2"></div>
                        <div>
                            <div class="fw-semibold">${this.escapeHtml(
                              server.name
                            )}</div>
                            <small class="text-muted">${this.escapeHtml(
                              server.ip_address
                            )}:${server.port || 22}</small>
                        </div>
                    </div>
                </td>
                <td>
                    <span class="badge bg-${
                      server.status === "active" ? "success" : "danger"
                    }">
                        ${
                          server.status.charAt(0).toUpperCase() +
                          server.status.slice(1)
                        }
                    </span>
                </td>
                <td>
                    <div class="d-flex flex-wrap gap-1">
                        ${server.current_services
                          .map(
                            (service) =>
                              `<span class="badge bg-secondary">${this.escapeHtml(
                                service
                              )}</span>`
                          )
                          .join("")}
                        ${
                          server.current_services.length === 0
                            ? '<span class="text-muted">No services</span>'
                            : ""
                        }
                    </div>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="progress progress-modern me-2" style="width: 60px;">
                            <div class="progress-bar-modern bg-${
                              server.health_score >= 80
                                ? "success"
                                : server.health_score >= 60
                                ? "warning"
                                : "danger"
                            }" 
                                 style="width: ${
                                   server.health_score || 0
                                 }%"></div>
                        </div>
                        <small>${server.health_score || 0}%</small>
                    </div>
                </td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-primary" onclick="event.stopPropagation(); InfraAdmin.deployToServer(${
                          server.id
                        })" data-tooltip="Deploy Service">
                            <i class="fas fa-rocket"></i>
                        </button>
                        <button class="btn btn-outline-info" onclick="event.stopPropagation(); InfraAdmin.healthCheckServer(${
                          server.id
                        })" data-tooltip="Health Check">
                            <i class="fas fa-heartbeat"></i>
                        </button>
                        <button class="btn btn-outline-warning" onclick="event.stopPropagation(); InfraAdmin.restartServer(${
                          server.id
                        })" data-tooltip="Restart">
                            <i class="fas fa-redo"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `
      )
      .join("");
  },

  populateServerSelects(servers) {
    ["targetServerId", "sourceServerId"].forEach((selectId) => {
      const select = document.getElementById(selectId);
      if (select) {
        const currentValue = select.value;
        select.innerHTML =
          '<option value="">Select server...</option>' +
          servers
            .map(
              (server) =>
                `<option value="${server.id}">${this.escapeHtml(
                  server.name
                )} (${this.escapeHtml(server.ip_address)})</option>`
            )
            .join("");
        select.value = currentValue;
      }
    });
  },

  async handleAddServer(event) {
    event.preventDefault();

    const formData = {
      name: document.getElementById("serverName").value,
      ip_address: document.getElementById("serverIp").value,
      username: document.getElementById("serverUsername").value,
      port: parseInt(document.getElementById("serverPort").value) || 22,
      service_roles: Array.from(
        document.querySelectorAll(
          '#addServerForm input[type="checkbox"]:checked'
        )
      ).map((cb) => cb.value),
    };

    const authMethod = document.querySelector(
      'input[name="authMethod"]:checked'
    )?.value;
    if (authMethod === "password") {
      formData.password = document.getElementById("serverPassword").value;
    } else {
      formData.ssh_key_path = document.getElementById("serverKeyPath").value;
    }

    try {
      const data = await this.apiCall("/servers/add", {
        method: "POST",
        body: JSON.stringify(formData),
      });

      if (data.success) {
        this.showNotification("Server added successfully!", "success");
        bootstrap.Modal.getInstance(
          document.getElementById("addServerModal")
        )?.hide();
        document.getElementById("addServerForm").reset();
        this.loadServers();
        this.loadOverviewData();
      } else {
        this.showNotification(data.message || "Failed to add server", "error");
      }
    } catch (error) {
      this.showNotification("Failed to add server", "error");
    }
  },

  async testServerConnection() {
    const formData = {
      ip_address: document.getElementById("serverIp").value,
      username: document.getElementById("serverUsername").value,
      port: parseInt(document.getElementById("serverPort").value) || 22,
    };

    const authMethod = document.querySelector(
      'input[name="authMethod"]:checked'
    )?.value;
    if (authMethod === "password") {
      formData.password = document.getElementById("serverPassword").value;
    } else {
      formData.ssh_key_path = document.getElementById("serverKeyPath").value;
    }

    if (!formData.ip_address || !formData.username) {
      this.showNotification(
        "Please fill in IP address and username",
        "warning"
      );
      return;
    }

    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Testing...';
    btn.disabled = true;

    try {
      const data = await this.apiCall("/servers/test-connection", {
        method: "POST",
        body: JSON.stringify(formData),
      });

      if (data.success) {
        this.showNotification("Connection successful!", "success");
        if (data.system_info) {
          console.log("System info:", data.system_info);
        }
      } else {
        this.showNotification(data.message || "Connection failed", "error");
      }
    } catch (error) {
      this.showNotification("Connection test failed", "error");
    } finally {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }
  },

  toggleAuthMethod() {
    const authMethod = document.querySelector(
      'input[name="authMethod"]:checked'
    )?.value;
    const passwordField = document.getElementById("passwordField");
    const keyField = document.getElementById("keyField");

    if (authMethod === "password") {
      passwordField.style.display = "block";
      keyField.style.display = "none";
    } else {
      passwordField.style.display = "none";
      keyField.style.display = "block";
    }
  },

  // Domain Management
  async loadDomains() {
    try {
      const data = await this.apiCall("/domains/list");
      if (data.success) {
        this.updateDomainsTable(data.mappings);
      }
    } catch (error) {
      this.showErrorInTable("domainsTableBody", "Failed to load domains", 6);
    }
  },

  updateDomainsTable(domains) {
    const tbody = document.getElementById("domainsTableBody");
    if (!tbody) return;

    if (domains.length === 0) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4 text-muted">
                        <i class="fas fa-globe fa-2x mb-3"></i>
                        <p>No domain mappings configured yet.</p>
                    </td>
                </tr>
            `;
      return;
    }

    tbody.innerHTML = domains
      .map(
        (domain) => `
            <tr>
                <td>
                    <div class="fw-semibold">${this.escapeHtml(
                      domain.custom_domain
                    )}</div>
                    <small class="text-muted">${this.escapeHtml(
                      domain.tenant_name || "No tenant assigned"
                    )}</small>
                </td>
                <td>
                    <code class="small">${this.escapeHtml(
                      domain.target_subdomain
                    )}</code>
                </td>
                <td>
                    <span class="badge bg-${
                      domain.ssl_enabled ? "success" : "secondary"
                    }">
                        <i class="fas fa-${
                          domain.ssl_enabled ? "lock" : "unlock"
                        } me-1"></i>
                        ${domain.ssl_enabled ? "Enabled" : "Disabled"}
                    </span>
                </td>
                <td>
                    <span class="badge bg-${
                      domain.status === "active"
                        ? "success"
                        : domain.status === "pending"
                        ? "warning"
                        : "danger"
                    }">
                        ${
                          domain.status.charAt(0).toUpperCase() +
                          domain.status.slice(1)
                        }
                    </span>
                </td>
                <td>
                    ${
                      domain.last_verified
                        ? `<small>${new Date(
                            domain.last_verified
                          ).toLocaleString()}</small>`
                        : '<small class="text-muted">Never</small>'
                    }
                </td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-info" onclick="InfraAdmin.verifyDomain('${this.escapeHtml(
                          domain.custom_domain
                        )}')" data-tooltip="Verify Domain">
                            <i class="fas fa-check"></i>
                        </button>
                        <button class="btn btn-outline-primary" onclick="InfraAdmin.editDomain(${
                          domain.id
                        })" data-tooltip="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="InfraAdmin.deleteDomain(${
                          domain.id
                        })" data-tooltip="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `
      )
      .join("");
  },

  async handleAddDomain(event) {
    event.preventDefault();

    const formData = {
      custom_domain: document.getElementById("customDomain").value,
      target_subdomain: document.getElementById("targetSubdomain").value,
      tenant_id: document.getElementById("tenantSelect").value || null,
      ssl_enabled: document.getElementById("enableSsl").checked,
      ssl_auto_renew: document.getElementById("autoRenewSsl").checked,
    };

    try {
      const data = await this.apiCall("/domains/add", {
        method: "POST",
        body: JSON.stringify(formData),
      });

      if (data.success) {
        this.showNotification("Domain mapping added successfully!", "success");
        bootstrap.Modal.getInstance(
          document.getElementById("addDomainModal")
        )?.hide();
        document.getElementById("addDomainForm").reset();
        this.loadDomains();
        this.loadOverviewData();
      } else {
        this.showNotification(
          data.message || "Failed to add domain mapping",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to add domain mapping", "error");
    }
  },

  // Deployment Management
  async loadDeployments() {
    try {
      const data = await this.apiCall("/deployments/list");
      if (data.success) {
        this.updateDeploymentsTable(data.tasks);
      }
    } catch (error) {
      this.showErrorInTable(
        "deploymentsTableBody",
        "Failed to load deployments",
        7
      );
    }
  },

  updateDeploymentsTable(deployments) {
    const tbody = document.getElementById("deploymentsTableBody");
    if (!tbody) return;

    if (deployments.length === 0) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center py-4 text-muted">
                        <i class="fas fa-rocket fa-2x mb-3"></i>
                        <p>No deployment tasks yet.</p>
                    </td>
                </tr>
            `;
      return;
    }

    tbody.innerHTML = deployments
      .map(
        (deployment) => `
            <tr onclick="InfraAdmin.showDeploymentDetails(${
              deployment.id
            })" style="cursor: pointer;">
                <td>
                    <div class="fw-semibold">${this.escapeHtml(
                      deployment.service_type
                    )}</div>
                    <small class="text-muted">${this.escapeHtml(
                      deployment.current_step || "Waiting..."
                    )}</small>
                </td>
                <td>
                    <span class="badge bg-secondary">${this.escapeHtml(
                      deployment.task_type
                    )}</span>
                </td>
                <td>
                    <div>
                        ${
                          deployment.source_server
                            ? `<small>From: ${this.escapeHtml(
                                deployment.source_server
                              )}</small><br>`
                            : ""
                        }
                        ${
                          deployment.target_server
                            ? `<small>To: ${this.escapeHtml(
                                deployment.target_server
                              )}</small>`
                            : ""
                        }
                    </div>
                </td>
                <td>
                    <span class="badge bg-${
                      deployment.status === "completed"
                        ? "success"
                        : deployment.status === "failed"
                        ? "danger"
                        : deployment.status === "running"
                        ? "info"
                        : "secondary"
                    }">
                        ${
                          deployment.status.charAt(0).toUpperCase() +
                          deployment.status.slice(1)
                        }
                    </span>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="progress progress-modern me-2" style="width: 80px;">
                            <div class="progress-bar-modern bg-info" style="width: ${
                              deployment.progress || 0
                            }%"></div>
                        </div>
                        <small>${deployment.progress || 0}%</small>
                    </div>
                </td>
                <td>
                    <small>${new Date(
                      deployment.created_at
                    ).toLocaleString()}</small>
                </td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-info" onclick="event.stopPropagation(); InfraAdmin.showDeploymentLogs(${
                          deployment.id
                        })" data-tooltip="View Logs">
                            <i class="fas fa-file-alt"></i>
                        </button>
                        ${
                          deployment.status === "running"
                            ? `<button class="btn btn-outline-danger" onclick="event.stopPropagation(); InfraAdmin.cancelDeployment(${deployment.id})" data-tooltip="Cancel">
                                <i class="fas fa-stop"></i>
                            </button>`
                            : ""
                        }
                    </div>
                </td>
            </tr>
        `
      )
      .join("");
  },

  handleDeploymentTypeChange() {
    const deploymentType = document.getElementById("deploymentType")?.value;
    const sourceServerField = document.getElementById("sourceServerField");
    const sourceServerId = document.getElementById("sourceServerId");

    if (deploymentType === "migrate") {
      sourceServerField.style.display = "block";
      sourceServerId.required = true;
    } else {
      sourceServerField.style.display = "none";
      sourceServerId.required = false;
    }
  },

  async handleCreateDeployment(event) {
    event.preventDefault();

    const formData = {
      task_type: document.getElementById("deploymentType").value,
      service_type: document.getElementById("serviceType").value,
      target_server_id: parseInt(
        document.getElementById("targetServerId").value
      ),
      priority: document.getElementById("deploymentPriority").value,
      config: {
        test_before_deploy: document.getElementById("testBeforeDeploy").checked,
      },
    };

    const sourceServerId = document.getElementById("sourceServerId").value;
    if (sourceServerId) {
      formData.source_server_id = parseInt(sourceServerId);
    }

    try {
      const data = await this.apiCall("/deployments/create", {
        method: "POST",
        body: JSON.stringify(formData),
      });

      if (data.success) {
        this.showNotification("Deployment started successfully!", "success");
        bootstrap.Modal.getInstance(
          document.getElementById("createDeploymentModal")
        )?.hide();
        document.getElementById("createDeploymentForm").reset();
        this.loadDeployments();
        this.loadOverviewData();
      } else {
        this.showNotification(
          data.message || "Failed to start deployment",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to start deployment", "error");
    }
  },

  async showDeploymentDetails(deploymentId) {
    this.state.selectedDeploymentId = deploymentId;

    try {
      const data = await this.apiCall(`/deployments/${deploymentId}/logs`);
      if (data.success) {
        const content = document.getElementById("deploymentDetailsContent");
        const cancelBtn = document.getElementById("cancelDeploymentBtn");

        content.innerHTML = `
                    <div class="row">
                        <div class="col-md-8">
                            <div class="card">
                                <div class="card-header">
                                    <h6 class="mb-0">Deployment Logs</h6>
                                </div>
                                <div class="card-body">
                                    <div class="log-container" style="max-height: 400px; overflow-y: auto;">
                                        <pre>${this.escapeHtml(
                                          data.logs ||
                                            "No logs available yet..."
                                        )}</pre>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card">
                                <div class="card-header">
                                    <h6 class="mb-0">Task Status</h6>
                                </div>
                                <div class="card-body">
                                    <p><strong>Status:</strong> 
                                        <span class="badge bg-${
                                          data.status === "completed"
                                            ? "success"
                                            : data.status === "failed"
                                            ? "danger"
                                            : data.status === "running"
                                            ? "info"
                                            : "secondary"
                                        }">${data.status}</span>
                                    </p>
                                    <p><strong>Progress:</strong> ${
                                      data.progress || 0
                                    }%</p>
                                    <div class="progress mb-3">
                                        <div class="progress-bar bg-info" style="width: ${
                                          data.progress || 0
                                        }%"></div>
                                    </div>
                                    ${
                                      data.error_message
                                        ? `<div class="alert alert-danger"><strong>Error:</strong> ${this.escapeHtml(
                                            data.error_message
                                          )}</div>`
                                        : ""
                                    }
                                </div>
                            </div>
                        </div>
                    </div>
                `;

        cancelBtn.style.display =
          data.status === "running" ? "inline-block" : "none";

        const modal = new bootstrap.Modal(
          document.getElementById("deploymentDetailsModal")
        );
        modal.show();
      }
    } catch (error) {
      this.showNotification("Failed to load deployment details", "error");
    }
  },

  async cancelDeployment(deploymentId = null) {
    const id = deploymentId || this.state.selectedDeploymentId;
    if (!id) return;

    if (!confirm("Are you sure you want to cancel this deployment?")) return;

    try {
      const data = await this.apiCall(`/deployments/${id}/cancel`, {
        method: "POST",
      });

      if (data.success) {
        this.showNotification("Deployment cancelled successfully", "success");
        this.loadDeployments();
        if (this.state.selectedDeploymentId === id) {
          bootstrap.Modal.getInstance(
            document.getElementById("deploymentDetailsModal")
          )?.hide();
        }
      } else {
        this.showNotification(
          data.message || "Failed to cancel deployment",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to cancel deployment", "error");
    }
  },

  // Alert Management
  async loadAlerts() {
    try {
      const data = await this.apiCall("/monitoring/alerts");
      if (data.success) {
        this.updateAlertsTable(data.alerts);
        this.updateAlertsSummary(data.alerts);
      }
    } catch (error) {
      this.showErrorInTable("alertsTableBody", "Failed to load alerts", 6);
    }
  },

  updateAlertsTable(alerts) {
    const tbody = document.getElementById("alertsTableBody");
    if (!tbody) return;

    if (alerts.length === 0) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4 text-muted">
                        <i class="fas fa-check-circle fa-2x mb-3 text-success"></i>
                        <p>No active alerts. All systems are running normally.</p>
                    </td>
                </tr>
            `;
      return;
    }

    tbody.innerHTML = alerts
      .map(
        (alert) => `
            <tr>
                <td>
                    <div class="fw-semibold">${this.escapeHtml(
                      alert.title
                    )}</div>
                    <small class="text-muted">${this.escapeHtml(
                      alert.message
                    )}</small>
                </td>
                <td>
                    <span class="badge bg-${
                      alert.severity === "critical"
                        ? "danger"
                        : alert.severity === "warning"
                        ? "warning"
                        : "info"
                    }">
                        ${
                          alert.severity.charAt(0).toUpperCase() +
                          alert.severity.slice(1)
                        }
                    </span>
                </td>
                <td>
                    ${
                      alert.server_name
                        ? `<span class="badge bg-secondary">${this.escapeHtml(
                            alert.server_name
                          )}</span>`
                        : alert.domain_name
                        ? `<span class="badge bg-info">${this.escapeHtml(
                            alert.domain_name
                          )}</span>`
                        : '<span class="text-muted">System</span>'
                    }
                </td>
                <td>
                    ${
                      alert.metric_name
                        ? `<small>${this.escapeHtml(alert.metric_name)}: ${
                            alert.metric_value
                          }${
                            alert.metric_name.includes("usage") ? "%" : ""
                          }</small>`
                        : '<span class="text-muted">-</span>'
                    }
                </td>
                <td>
                    <small>${new Date(
                      alert.first_occurrence
                    ).toLocaleString()}</small>
                </td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-success" onclick="InfraAdmin.acknowledgeAlert(${
                          alert.id
                        })" data-tooltip="Acknowledge">
                            <i class="fas fa-check"></i>
                        </button>
                        <button class="btn btn-outline-primary" onclick="InfraAdmin.resolveAlert(${
                          alert.id
                        })" data-tooltip="Resolve">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `
      )
      .join("");
  },

  updateAlertsSummary(alerts) {
    const critical = alerts.filter((a) => a.severity === "critical").length;
    const warning = alerts.filter((a) => a.severity === "warning").length;
    const info = alerts.filter((a) => a.severity === "info").length;

    this.updateElement("criticalAlertsCount", critical);
    this.updateElement("warningAlertsCount", warning);
    this.updateElement("infoAlertsCount", info);
  },

  async acknowledgeAlert(alertId) {
    try {
      const data = await this.apiCall(
        `/monitoring/alerts/${alertId}/acknowledge`,
        {
          method: "POST",
        }
      );

      if (data.success) {
        this.showNotification("Alert acknowledged", "success");
        this.loadAlerts();
      } else {
        this.showNotification(
          data.message || "Failed to acknowledge alert",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to acknowledge alert", "error");
    }
  },

  async resolveAlert(alertId) {
    const notes = prompt("Resolution notes (optional):");
    if (notes === null) return; // User cancelled

    try {
      const data = await this.apiCall(`/monitoring/alerts/${alertId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution_notes: notes }),
      });

      if (data.success) {
        this.showNotification("Alert resolved", "success");
        this.loadAlerts();
        this.loadOverviewData();
      } else {
        this.showNotification(
          data.message || "Failed to resolve alert",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to resolve alert", "error");
    }
  },

  // Network Discovery
  async handleNetworkScan(event) {
    event.preventDefault();

    const networkRange = document.getElementById("networkRange").value;
    const credentialRows = document.querySelectorAll("#sshCredentials .row");

    const credentials = Array.from(credentialRows)
      .map((row) => ({
        username: row.querySelector('input[name="username"]').value,
        password: row.querySelector('input[name="password"]').value,
        port: parseInt(row.querySelector('input[name="port"]').value) || 22,
      }))
      .filter((cred) => cred.username);

    if (credentials.length === 0) {
      this.showNotification(
        "Please provide at least one set of SSH credentials",
        "warning"
      );
      return;
    }

    const formData = {
      network_range: networkRange,
      ssh_credentials: { credentials },
    };

    try {
      const data = await this.apiCall("/discovery/scan-network", {
        method: "POST",
        body: JSON.stringify(formData),
      });

      if (data.success) {
        this.showNotification("Network scan started!", "success");
        this.showScanProgress(data.scan_task_id);
      } else {
        this.showNotification(
          data.message || "Failed to start network scan",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to start network scan", "error");
    }
  },

  addCredentialRow() {
    const container = document.getElementById("sshCredentials");
    const row = document.createElement("div");
    row.className = "row mb-2";
    row.innerHTML = `
            <div class="col-4">
                <input type="text" class="form-control" placeholder="Username" name="username">
            </div>
            <div class="col-4">
                <input type="password" class="form-control" placeholder="Password" name="password">
            </div>
            <div class="col-3">
                <input type="number" class="form-control" placeholder="Port" name="port" value="22">
            </div>
            <div class="col-1">
                <button type="button" class="btn btn-outline-danger btn-sm" onclick="this.closest('.row').remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
    container.appendChild(row);
  },

  async showScanProgress(taskId) {
    const modal = new bootstrap.Modal(
      document.getElementById("networkScanModal")
    );
    modal.show();

    const progressDiv = document.getElementById("scanProgress");
    const resultsDiv = document.getElementById("scanResults");
    const progressBar = document.getElementById("scanProgressBar");

    progressDiv.style.display = "block";
    resultsDiv.innerHTML = "";

    // Poll for scan progress
    const pollInterval = setInterval(async () => {
      try {
        const data = await this.apiCall(`/deployments/${taskId}/logs`);

        if (data.success) {
          progressBar.style.width = `${data.progress || 0}%`;

          if (data.status === "completed") {
            clearInterval(pollInterval);
            progressDiv.style.display = "none";

            if (data.config && data.config.discovered_machines) {
              this.showScanResults(data.config.discovered_machines);
            } else {
              resultsDiv.innerHTML =
                '<p class="text-center text-muted">No machines discovered.</p>';
            }
          } else if (data.status === "failed") {
            clearInterval(pollInterval);
            progressDiv.style.display = "none";
            resultsDiv.innerHTML = `<div class="alert alert-danger">Scan failed: ${this.escapeHtml(
              data.error_message || "Unknown error"
            )}</div>`;
          }
        }
      } catch (error) {
        console.error("Failed to get scan progress:", error);
        clearInterval(pollInterval);
        progressDiv.style.display = "none";
        resultsDiv.innerHTML =
          '<div class="alert alert-danger">Failed to get scan progress</div>';
      }
    }, this.config.pollInterval);
  },

  showScanResults(machines) {
    const resultsDiv = document.getElementById("scanResults");
    const autoSetupBtn = document.getElementById("autoSetupBtn");

    if (machines.length === 0) {
      resultsDiv.innerHTML =
        '<p class="text-center text-muted">No accessible machines found.</p>';
      autoSetupBtn.style.display = "none";
      return;
    }

    resultsDiv.innerHTML = `
            <div class="table-responsive">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>
                                <input type="checkbox" id="selectAllMachines" onchange="InfraAdmin.toggleAllMachines(this)">
                            </th>
                            <th>IP Address</th>
                            <th>Hostname</th>
                            <th>OS</th>
                            <th>Resources</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${machines
                          .map(
                            (machine, index) => `
                            <tr>
                                <td>
                                    <input type="checkbox" class="machine-checkbox" value="${index}" ${
                              machine.auto_setup_ready ? "" : "disabled"
                            }>
                                </td>
                                <td>
                                    <strong>${this.escapeHtml(
                                      machine.ip_address
                                    )}</strong>
                                    <br><small class="text-muted">${this.escapeHtml(
                                      machine.username || "Unknown user"
                                    )}</small>
                                </td>
                                <td>${this.escapeHtml(
                                  machine.hostname || "Unknown"
                                )}</td>
                                <td>
                                    ${this.escapeHtml(
                                      machine.os_type || "Unknown"
                                    )}
                                    <br><small class="text-muted">${this.escapeHtml(
                                      machine.os_version || ""
                                    )}</small>
                                </td>
                                <td>
                                    <small>
                                        CPU: ${
                                          machine.cpu_cores || "?"
                                        } cores<br>
                                        RAM: ${machine.memory_gb || "?"} GB<br>
                                        Disk: ${machine.disk_gb || "?"} GB
                                    </small>
                                </td>
                                <td>
                                    <span class="badge bg-${
                                      machine.ssh_accessible
                                        ? "success"
                                        : "danger"
                                    }">
                                        ${
                                          machine.ssh_accessible
                                            ? "SSH OK"
                                            : "SSH Failed"
                                        }
                                    </span>
                                    ${
                                      machine.auto_setup_ready
                                        ? '<br><span class="badge bg-info">Auto-setup ready</span>'
                                        : '<br><span class="badge bg-warning">Manual setup</span>'
                                    }
                                </td>
                            </tr>
                        `
                          )
                          .join("")}
                    </tbody>
                </table>
            </div>
        `;

    autoSetupBtn.style.display = machines.some((m) => m.auto_setup_ready)
      ? "inline-block"
      : "none";

    // Store machines data for auto-setup
    this.state.discoveredMachines = machines;
  },

  toggleAllMachines(checkbox) {
    const checkboxes = document.querySelectorAll(
      ".machine-checkbox:not(:disabled)"
    );
    checkboxes.forEach((cb) => (cb.checked = checkbox.checked));
  },

  async autoSetupSelectedMachines() {
    const selectedIndexes = Array.from(
      document.querySelectorAll(".machine-checkbox:checked")
    ).map((cb) => parseInt(cb.value));

    if (selectedIndexes.length === 0) {
      this.showNotification("Please select at least one machine", "warning");
      return;
    }

    const selectedMachines = selectedIndexes.map(
      (index) => this.state.discoveredMachines[index]
    );

    for (const machine of selectedMachines) {
      try {
        const setupData = {
          ip_address: machine.ip_address,
          username: machine.username,
          password: machine.password,
          service_roles: machine.recommended_roles || ["docker"],
          auto_migrate: false,
        };

        const data = await this.apiCall("/discovery/auto-setup", {
          method: "POST",
          body: JSON.stringify(setupData),
        });

        if (data.success) {
          this.showNotification(
            `Auto-setup started for ${machine.ip_address}`,
            "success"
          );
        } else {
          this.showNotification(
            `Failed to setup ${machine.ip_address}: ${data.message}`,
            "error"
          );
        }
      } catch (error) {
        this.showNotification(`Failed to setup ${machine.ip_address}`, "error");
      }
    }

    bootstrap.Modal.getInstance(
      document.getElementById("networkScanModal")
    )?.hide();
    this.loadServers();
  },

  // System Management Functions
  async toggleMonitoring() {
    const btn = document.getElementById("monitoringToggle");
    const isStarting = !this.state.monitoringActive;

    btn.disabled = true;
    btn.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i>${
      isStarting ? "Starting..." : "Stopping..."
    }`;

    try {
      const endpoint = isStarting ? "/monitoring/start" : "/monitoring/stop";
      const data = await this.apiCall(endpoint, { method: "POST" });

      if (data.success) {
        this.state.monitoringActive = isStarting;
        btn.innerHTML = `<i class="fas fa-${
          isStarting ? "stop" : "play"
        } me-2"></i>${isStarting ? "Stop" : "Start"} Monitoring`;
        btn.className = `btn btn-outline-${isStarting ? "warning" : "light"}`;
        this.showNotification(
          `Monitoring ${isStarting ? "started" : "stopped"}`,
          "success"
        );

        if (isStarting) {
          this.loadAlerts();
        }
      } else {
        this.showNotification(
          data.message ||
            `Failed to ${isStarting ? "start" : "stop"} monitoring`,
          "error"
        );
      }
    } catch (error) {
      this.showNotification(
        `Failed to ${isStarting ? "start" : "stop"} monitoring`,
        "error"
      );
    } finally {
      btn.disabled = false;
      if (!this.state.monitoringActive) {
        btn.innerHTML = '<i class="fas fa-play me-2"></i>Start Monitoring';
      }
    }
  },

  async initializeSystem() {
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML =
      '<i class="fas fa-spinner fa-spin me-2"></i>Initializing...';
    btn.disabled = true;

    try {
      const data = await this.apiCall("/system/initialize", {
        method: "POST",
      });

      if (data.success) {
        this.showNotification(
          "Infrastructure system initialized successfully!",
          "success"
        );
        bootstrap.Modal.getInstance(
          document.getElementById("systemInitModal")
        )?.hide();
        this.loadOverviewData();
      } else {
        this.showNotification(
          data.message || "Failed to initialize system",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to initialize system", "error");
    } finally {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }
  },

  // Utility Functions
  refreshServers() {
    this.loadServers();
    this.loadOverviewData();
    this.showNotification("Servers refreshed", "info", 2000);
  },

  refreshDeployments() {
    this.loadDeployments();
    this.showNotification("Deployments refreshed", "info", 2000);
  },

  async healthCheckAll() {
    try {
      const data = await this.apiCall("/servers/health-check-all", {
        method: "POST",
      });

      if (data.success) {
        this.showNotification(
          "Health check completed for all servers",
          "success"
        );
        this.loadServers();
        this.loadOverviewData();
      } else {
        this.showNotification(data.message || "Health check failed", "error");
      }
    } catch (error) {
      this.showNotification("Failed to run health check", "error");
    }
  },

  async healthCheckServer(serverId) {
    try {
      const data = await this.apiCall(`/servers/${serverId}/health-check`, {
        method: "POST",
      });

      if (data.success) {
        this.showNotification("Health check completed", "success");
        this.loadServers();
      } else {
        this.showNotification(data.message || "Health check failed", "error");
      }
    } catch (error) {
      this.showNotification("Failed to run health check", "error");
    }
  },

  async acknowledgeAllAlerts() {
    if (!confirm("Acknowledge all active alerts?")) return;

    try {
      const data = await this.apiCall("/monitoring/alerts/acknowledge-all", {
        method: "POST",
      });

      if (data.success) {
        this.showNotification("All alerts acknowledged", "success");
        this.loadAlerts();
      } else {
        this.showNotification(
          data.message || "Failed to acknowledge alerts",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to acknowledge alerts", "error");
    }
  },

  async createBackup() {
    if (
      !confirm("Create a full infrastructure backup? This may take some time.")
    )
      return;

    try {
      const data = await this.apiCall("/disaster-recovery/backup-all", {
        method: "POST",
        body: JSON.stringify({
          backup_type: "full",
          include_data: true,
        }),
      });

      if (data.success) {
        this.showNotification(
          "Backup started! Check deployments for progress.",
          "success"
        );
        this.loadDeployments();
      } else {
        this.showNotification(
          data.message || "Failed to start backup",
          "error"
        );
      }
    } catch (error) {
      this.showNotification("Failed to start backup", "error");
    }
  },

  testAllSystems() {
    this.healthCheckAll();
  },

  handleTabChange(event) {
    const targetTab = event.target.getAttribute("data-bs-target");

    switch (targetTab) {
      case "#servers":
        this.loadServers();
        break;
      case "#domains":
        this.loadDomains();
        break;
      case "#deployments":
        this.loadDeployments();
        break;
      case "#monitoring":
        this.loadAlerts();
        break;
      case "#discovery":
        // Discovery tab is static, no additional loading needed
        break;
    }
  },

  // Helper Functions
  updateElement(id, value) {
    const element = document.getElementById(id);
    if (element) {
      element.textContent = value;
    }
  },

  updateProgressBar(id, percentage) {
    const element = document.getElementById(id);
    if (element) {
      element.style.width = `${percentage}%`;
    }
  },

  showErrorInTable(tableBodyId, message, colCount) {
    const tbody = document.getElementById(tableBodyId);
    if (tbody) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="${colCount}" class="text-center py-4 text-danger">
                        <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                        <p>${this.escapeHtml(message)}</p>
                        <button class="btn btn-outline-primary btn-sm" onclick="location.reload()">
                            <i class="fas fa-redo me-2"></i>Retry
                        </button>
                    </td>
                </tr>
            `;
    }
  },

  // Add this method inside the InfraAdmin object
  deployToServer(serverId) {
    // Set the target server in the deployment modal
    document.getElementById("targetServerId").value = serverId;

    // Show the create deployment modal
    const modal = new bootstrap.Modal(
      document.getElementById("createDeploymentModal")
    );
    modal.show();
  },

  escapeHtml(text) {
    if (typeof text !== "string") return text;
    const map = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return text.replace(/[&<>"']/g, (m) => map[m]);
  },

  cleanup() {
    if (this.state.refreshInterval) {
      clearInterval(this.state.refreshInterval);
    }
  },
};

let currentServerId = null;

function showServerDetails(serverId) {
  currentServerId = serverId;

  // Reset modal state
  document.getElementById("serverDetailsLoading").style.display = "block";
  document.getElementById("serverDetailsContent").style.display = "none";
  document.getElementById("serverDetailsError").style.display = "none";
  document.getElementById("serverNameTitle").textContent = "Loading...";

  // Show modal
  const modal = new bootstrap.Modal(
    document.getElementById("serverDetailsModal")
  );
  modal.show();

  // Load server details
  loadServerDetails(serverId);
}

function loadServerDetails(serverId) {
  fetch(`/infra-admin/api/servers/${serverId}/details`)
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        populateServerDetails(data.server_details);
      } else {
        showServerDetailsError(data.message || "Failed to load server details");
      }
    })
    .catch((error) => {
      console.error("Error loading server details:", error);
      showServerDetailsError(
        "Network error occurred while loading server details"
      );
    });
}

function populateServerDetails(details) {
  const server = details.server;
  const health = details.health_data;
  const metrics = details.metrics;

  // Hide loading, show content
  document.getElementById("serverDetailsLoading").style.display = "none";
  document.getElementById("serverDetailsContent").style.display = "block";

  // Update title
  document.getElementById("serverNameTitle").textContent = server.name;

  // Populate server info
  document.getElementById("serverDetailName").textContent = server.name;
  document.getElementById("serverDetailIP").textContent = server.ip_address;
  document.getElementById("serverDetailOS").textContent = server.os_type || "-";

  const statusBadge = document.getElementById("serverDetailStatus");
  statusBadge.textContent = server.status;
  statusBadge.className = `badge bg-${getStatusColor(server.status)}`;

  document.getElementById("serverDetailCPU").textContent = server.cpu_cores
    ? `${server.cpu_cores} cores`
    : "-";
  document.getElementById("serverDetailMemory").textContent = server.memory_gb
    ? `${server.memory_gb} GB`
    : "-";
  document.getElementById("serverDetailDisk").textContent = server.disk_gb
    ? `${server.disk_gb} GB`
    : "-";

  // Populate health data
  const healthScore = health.score || 0;
  document.getElementById("serverHealthScore").textContent = `${healthScore}%`;

  const healthBar = document.getElementById("serverHealthBar");
  healthBar.style.width = `${healthScore}%`;
  healthBar.className = `progress-bar bg-${getHealthColor(healthScore)}`;

  // Populate metrics
  document.getElementById("serverCPUUsage").textContent = metrics.cpu_usage
    ? `${metrics.cpu_usage.toFixed(1)}%`
    : "-";
  document.getElementById("serverMemoryUsage").textContent =
    metrics.memory_usage ? `${metrics.memory_usage.toFixed(1)}%` : "-";
  document.getElementById("serverDiskUsage").textContent = metrics.disk_usage
    ? `${metrics.disk_usage.toFixed(1)}%`
    : "-";

  document.getElementById("serverLastHealthCheck").textContent =
    server.last_health_check
      ? new Date(server.last_health_check).toLocaleString()
      : "Never";

  // Populate services
  populateServicesStatus(details.service_status);

  // Populate tabs
  populateDeployments(details.recent_deployments);
  populateCronJobs(details.cron_jobs);
  populateAlerts(details.recent_alerts);
}

function populateServicesStatus(serviceStatus) {
  const container = document.getElementById("serverServicesStatus");
  container.innerHTML = "";

  if (Object.keys(serviceStatus).length === 0) {
    container.innerHTML =
      '<div class="col-12"><p class="text-muted">No services configured</p></div>';
    return;
  }

  Object.entries(serviceStatus).forEach(([service, status]) => {
    const serviceCard = `
            <div class="col-md-3 mb-2">
                <div class="card border-0 bg-light">
                    <div class="card-body text-center py-2">
                        <i class="fas fa-${getServiceIcon(
                          service
                        )} fa-2x mb-2 text-${
      status.running ? "success" : "danger"
    }"></i>
                        <h6 class="card-title mb-1">${service}</h6>
                        <span class="badge bg-${
                          status.running ? "success" : "danger"
                        }">${status.running ? "Running" : "Stopped"}</span>
                    </div>
                </div>
            </div>
        `;
    container.innerHTML += serviceCard;
  });
}

function populateDeployments(deployments) {
  const tbody = document.getElementById("serverDeploymentsList");
  tbody.innerHTML = "";

  if (deployments.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="5" class="text-center text-muted">No recent deployments</td></tr>';
    return;
  }

  deployments.forEach((deployment) => {
    const row = `
            <tr>
                <td>${deployment.task_type}</td>
                <td>${deployment.service_type}</td>
                <td><span class="badge bg-${getStatusColor(
                  deployment.status
                )}">${deployment.status}</span></td>
                <td>
                    <div class="progress" style="height: 15px;">
                        <div class="progress-bar" style="width: ${
                          deployment.progress
                        }%">${deployment.progress}%</div>
                    </div>
                </td>
                <td>${new Date(deployment.created_at).toLocaleString()}</td>
            </tr>
        `;
    tbody.innerHTML += row;
  });
}

function populateCronJobs(cronJobs) {
  const tbody = document.getElementById("serverCronJobsList");
  tbody.innerHTML = "";

  if (cronJobs.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="5" class="text-center text-muted">No cron jobs configured</td></tr>';
    return;
  }

  cronJobs.forEach((job) => {
    const row = `
            <tr>
                <td>${job.name}</td>
                <td><code>${job.schedule}</code></td>
                <td><span class="badge bg-${getStatusColor(job.status)}">${
      job.status
    }</span></td>
                <td>${
                  job.last_run
                    ? new Date(job.last_run).toLocaleString()
                    : "Never"
                }</td>
                <td>${
                  job.next_run ? new Date(job.next_run).toLocaleString() : "-"
                }</td>
            </tr>
        `;
    tbody.innerHTML += row;
  });
}

function populateAlerts(alerts) {
  const tbody = document.getElementById("serverAlertsList");
  tbody.innerHTML = "";

  if (alerts.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="5" class="text-center text-muted">No recent alerts</td></tr>';
    return;
  }

  alerts.forEach((alert) => {
    const row = `
            <tr>
                <td>${alert.alert_type}</td>
                <td><span class="badge bg-${getSeverityColor(
                  alert.severity
                )}">${alert.severity}</span></td>
                <td>${alert.message}</td>
                <td><span class="badge bg-${getStatusColor(alert.status)}">${
      alert.status
    }</span></td>
                <td>${new Date(alert.first_occurrence).toLocaleString()}</td>
            </tr>
        `;
    tbody.innerHTML += row;
  });
}

function showServerDetailsError(message) {
  document.getElementById("serverDetailsLoading").style.display = "none";
  document.getElementById("serverDetailsContent").style.display = "none";
  document.getElementById("serverDetailsError").style.display = "block";
  document.getElementById("serverDetailsErrorMessage").textContent = message;
}

function refreshServerDetails() {
  if (currentServerId) {
    document.getElementById("serverDetailsLoading").style.display = "block";
    document.getElementById("serverDetailsContent").style.display = "none";
    document.getElementById("serverDetailsError").style.display = "none";
    loadServerDetails(currentServerId);
  }
}

// Helper functions
function getStatusColor(status) {
  const colors = {
    active: "success",
    running: "success",
    completed: "success",
    pending: "warning",
    deploying: "info",
    failed: "danger",
    error: "danger",
    stopped: "secondary",
    cancelled: "secondary",
    acknowledged: "warning",
    resolved: "success",
  };
  return colors[status] || "secondary";
}

function getHealthColor(score) {
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  return "danger";
}

function getSeverityColor(severity) {
  const colors = {
    critical: "danger",
    warning: "warning",
    info: "info",
  };
  return colors[severity] || "secondary";
}

function getServiceIcon(service) {
  const icons = {
    docker: "cube",
    nginx: "globe",
    postgres: "database",
    redis: "memory",
    worker: "cogs",
    master: "crown",
  };
  return icons[service] || "cog";
}

// Make InfraAdmin globally available
window.InfraAdmin = InfraAdmin;
