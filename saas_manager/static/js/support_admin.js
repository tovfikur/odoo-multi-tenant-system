// Simple Master Admin Support System
class MasterAdminSupport {
  constructor() {
    this.tickets = [];
    this.currentTicketId = null;
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadTickets();

    // Auto-refresh every 30 seconds
    setInterval(() => this.loadTickets(), 30000);
  }

  bindEvents() {
    // Refresh button
    const refreshBtn = document.getElementById("masterRefreshBtn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => this.loadTickets());
    }

    // Filter buttons
    document.querySelectorAll(".masterFilterBtn").forEach((btn) => {
      btn.addEventListener("click", (e) =>
        this.filterTickets(e.target.dataset.masterFilter)
      );
    });

    // Search input
    const searchInput = document.getElementById("masterSearchInput");
    if (searchInput) {
      searchInput.addEventListener("input", (e) =>
        this.searchTickets(e.target.value)
      );
    }

    // Status change
    document.addEventListener("change", (e) => {
      if (e.target.classList.contains("masterStatusSelect")) {
        this.updateStatus(e.target.dataset.masterTicket, e.target.value);
      }
      if (e.target.classList.contains("masterPrioritySelect")) {
        this.updatePriority(e.target.dataset.masterTicket, e.target.value);
      }
    });

    // Button clicks
    document.addEventListener("click", (e) => {
      const ticketId = e.target.dataset.masterTicket;

      if (e.target.classList.contains("masterReplyBtn")) {
        this.showReplyModal(ticketId);
      }
      if (e.target.classList.contains("masterNotesBtn")) {
        this.toggleNotes(ticketId);
      }
      if (e.target.classList.contains("masterViewBtn")) {
        this.viewTicket(ticketId);
      }
      if (e.target.classList.contains("masterRepliesBtn")) {
        this.toggleReplies(ticketId);
      }
      if (e.target.classList.contains("masterQuickBtn")) {
        this.quickStatusChange(ticketId, e.target.dataset.masterCurrent);
      }
      if (e.target.classList.contains("masterSaveNotesBtn")) {
        this.saveNotes(ticketId);
      }
      if (e.target.id === "masterSendReply") {
        this.sendReply();
      }
    });
  }

  async loadTickets() {
    try {
      const response = await fetch("/admin/support/api/tickets");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      this.tickets = await response.json();
      this.updateStats();

      console.log("Tickets loaded:", this.tickets.length);
    } catch (error) {
      console.error("Failed to load tickets:", error);
      this.showAlert("Failed to load tickets", "danger");
    }
  }

  updateStats() {
    const stats = {
      total: this.tickets.length,
      open: this.tickets.filter((t) => t.status === "open").length,
      in_progress: this.tickets.filter((t) => t.status === "in_progress")
        .length,
      closed: this.tickets.filter((t) => t.status === "closed").length,
      urgent: this.tickets.filter((t) => t.priority === "urgent").length,
    };

    // Update stat displays
    Object.keys(stats).forEach((key) => {
      const element = document.getElementById(
        `masterStat${
          key.charAt(0).toUpperCase() + key.slice(1).replace("_", "")
        }`
      );
      if (element) {
        element.textContent = stats[key];
        element.classList.add("pulse");
        setTimeout(() => element.classList.remove("pulse"), 500);
      }
    });
  }

  async updateStatus(ticketId, status) {
    try {
      const headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      };
      
      // Add CSRF token
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                       document.querySelector('input[name="csrf_token"]')?.value;
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }

      const response = await fetch(`/admin/support/update/${ticketId}`, {
        method: "POST",
        headers,
        body: JSON.stringify({ status }),
      });

      const result = await response.json();

      if (result.success) {
        this.showAlert(
          `Status updated to ${status.replace("_", " ")}`,
          "success"
        );
        this.updateTicketBadge(ticketId, status);
        this.updateQuickButton(ticketId, status);
        this.loadTickets(); // Refresh stats
      } else {
        throw new Error(result.error || "Update failed");
      }
    } catch (error) {
      console.error("Failed to update status:", error);
      this.showAlert("Failed to update status", "danger");
    }
  }

  async updatePriority(ticketId, priority) {
    try {
      const headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      };
      
      // Add CSRF token
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                       document.querySelector('input[name="csrf_token"]')?.value;
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }

      const response = await fetch(`/admin/support/update/${ticketId}`, {
        method: "POST",
        headers,
        body: JSON.stringify({ priority }),
      });

      const result = await response.json();

      if (result.success) {
        this.showAlert(`Priority updated to ${priority}`, "success");
        this.loadTickets(); // Refresh stats
      } else {
        throw new Error(result.error || "Update failed");
      }
    } catch (error) {
      console.error("Failed to update priority:", error);
      this.showAlert("Failed to update priority", "danger");
    }
  }

  async quickStatusChange(ticketId, currentStatus) {
    const nextStatus = this.getNextStatus(currentStatus);

    const statusSelect = document.querySelector(
      `.masterStatusSelect[data-master-ticket="${ticketId}"]`
    );
    if (statusSelect) {
      statusSelect.value = nextStatus;
      await this.updateStatus(ticketId, nextStatus);
    }
  }

  getNextStatus(current) {
    const cycle = {
      open: "in_progress",
      in_progress: "closed",
      closed: "open",
    };
    return cycle[current] || "open";
  }

  updateTicketBadge(ticketId, status) {
    const card = document.querySelector(`[data-master-ticket="${ticketId}"]`);
    if (card) {
      const badge = card.querySelector(".masterStatusBadge");
      if (badge) {
        badge.className = `badge masterStatusBadge bg-${this.getStatusColor(
          status
        )}`;
        badge.textContent = status.replace("_", " ").toUpperCase();
      }
    }
  }

  updateQuickButton(ticketId, status) {
    const button = document.querySelector(
      `.masterQuickBtn[data-master-ticket="${ticketId}"]`
    );
    if (button) {
      button.dataset.masterCurrent = status;
      const nextStatus = this.getNextStatus(status);
      button.innerHTML = `<i class="fas fa-fast-forward"></i> ${nextStatus.replace(
        "_",
        " "
      )}`;
    }
  }

  getStatusColor(status) {
    const colors = {
      open: "primary",
      in_progress: "warning",
      closed: "success",
    };
    return colors[status] || "secondary";
  }

  showReplyModal(ticketId) {
    const ticket = this.findTicketById(ticketId);
    if (!ticket) return;

    this.currentTicketId = ticketId;

    document.getElementById("masterReplyCustomer").textContent =
      ticket.user_email || "Unknown";
    document.getElementById("masterReplySubject").textContent =
      ticket.subject || "No subject";
    document.getElementById("masterReplyMessage").value = "";

    const modal = new bootstrap.Modal(
      document.getElementById("masterReplyModal")
    );
    modal.show();
  }

  async sendReply() {
    if (!this.currentTicketId) return;

    const message = document.getElementById("masterReplyMessage").value.trim();
    if (!message) {
      this.showAlert("Please enter a reply message", "warning");
      return;
    }

    try {
      const headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      };
      
      // Add CSRF token
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                       document.querySelector('input[name="csrf_token"]')?.value;
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }

      const response = await fetch(
        `/admin/support/reply/${this.currentTicketId}`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({ message }),
        }
      );

      const result = await response.json();

      if (result.success) {
        this.showAlert("Reply sent successfully!", "success");
        bootstrap.Modal.getInstance(
          document.getElementById("masterReplyModal")
        ).hide();
        this.currentTicketId = null;

        // Refresh any open replies sections
        this.refreshOpenReplies();
      } else {
        throw new Error(result.error || "Send failed");
      }
    } catch (error) {
      console.error("Failed to send reply:", error);
      this.showAlert("Failed to send reply", "danger");
    }
  }

  toggleNotes(ticketId) {
    const notesSection = document.getElementById(`masterNotes-${ticketId}`);
    if (notesSection) {
      const isVisible = notesSection.style.display !== "none";
      notesSection.style.display = isVisible ? "none" : "block";

      if (!isVisible) {
        const textarea = notesSection.querySelector(".masterNotesText");
        if (textarea) setTimeout(() => textarea.focus(), 100);
      }
    }
  }

  async saveNotes(ticketId) {
    const textarea = document.querySelector(
      `.masterNotesText[data-master-ticket="${ticketId}"]`
    );
    if (!textarea) return;

    const notes = textarea.value.trim();

    try {
      const headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      };
      
      // Add CSRF token
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                       document.querySelector('input[name="csrf_token"]')?.value;
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }

      const response = await fetch(`/admin/support/update/${ticketId}`, {
        method: "POST",
        headers,
        body: JSON.stringify({ admin_notes: notes }),
      });

      const result = await response.json();

      if (result.success) {
        this.showAlert("Notes saved successfully!", "success");
      } else {
        throw new Error(result.error || "Save failed");
      }
    } catch (error) {
      console.error("Failed to save notes:", error);
      this.showAlert("Failed to save notes", "danger");
    }
  }

  async toggleReplies(ticketId) {
    const repliesSection = document.getElementById(`masterReplies-${ticketId}`);
    const button = document.querySelector(
      `.masterRepliesBtn[data-master-ticket="${ticketId}"]`
    );

    if (repliesSection) {
      const isVisible = repliesSection.style.display !== "none";
      repliesSection.style.display = isVisible ? "none" : "block";

      if (button) {
        button.innerHTML = isVisible
          ? '<i class="fas fa-comments"></i> Show Replies'
          : '<i class="fas fa-comments"></i> Hide Replies';
      }

      if (!isVisible) {
        await this.loadReplies(ticketId);
      }
    }
  }

  async loadReplies(ticketId) {
    const repliesContent = document.getElementById(
      `masterRepliesContent-${ticketId}`
    );
    if (!repliesContent) return;

    // Show loading
    repliesContent.innerHTML =
      '<div class="text-center py-3"><i class="fas fa-spinner fa-spin"></i> Loading replies...</div>';

    try {
      const response = await fetch(`/admin/support/ticket/${ticketId}/replies`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const replies = await response.json();

      if (!replies.length) {
        repliesContent.innerHTML =
          '<div class="text-center py-3 text-muted"><i class="fas fa-inbox"></i> No replies yet</div>';
        return;
      }

      const repliesHtml = replies
        .map(
          (reply) => `
        <div class="reply-item border-start border-3 ${
          reply.is_admin ? "border-primary" : "border-secondary"
        } ps-3 mb-3">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <strong class="${
              reply.is_admin ? "text-primary" : "text-secondary"
            }">
              <i class="fas fa-${
                reply.is_admin ? "user-shield" : "user"
              } me-1"></i>
              ${reply.is_admin ? "Admin" : "Customer"}
            </strong>
            <small class="text-muted">${new Date(
              reply.created_at
            ).toLocaleString()}</small>
          </div>
          <div class="reply-message">
            ${this.escapeHtml(reply.message).replace(/\n/g, "<br>")}
          </div>
        </div>
      `
        )
        .join("");

      repliesContent.innerHTML = repliesHtml;
    } catch (error) {
      console.error("Failed to load replies:", error);
      repliesContent.innerHTML =
        '<div class="text-center py-3 text-danger"><i class="fas fa-exclamation-triangle"></i> Failed to load replies</div>';
    }
  }

  refreshOpenReplies() {
    // Find all currently open replies sections and refresh them
    document.querySelectorAll(".masterRepliesSection").forEach((section) => {
      if (section.style.display !== "none") {
        const ticketId = section.id.replace("masterReplies-", "");
        this.loadReplies(ticketId);
      }
    });
  }

  viewTicket(ticketId) {
    const ticket = this.findTicketById(ticketId);
    if (!ticket) return;

    const modal = document.createElement("div");
    modal.className = "modal fade";
    modal.innerHTML = `
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Ticket #${ticketId}: ${this.escapeHtml(
      ticket.subject
    )}</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <div class="row mb-3">
              <div class="col-md-6"><strong>Customer:</strong> ${this.escapeHtml(
                ticket.user_email
              )}</div>
              <div class="col-md-6"><strong>Status:</strong> <span class="badge bg-${this.getStatusColor(
                ticket.status
              )}">${ticket.status.replace("_", " ").toUpperCase()}</span></div>
            </div>
            <div class="row mb-3">
              <div class="col-md-6"><strong>Priority:</strong> ${ticket.priority.toUpperCase()}</div>
              <div class="col-md-6"><strong>Created:</strong> ${new Date(
                ticket.created_at
              ).toLocaleString()}</div>
            </div>
            <div class="mb-3">
              <strong>Message:</strong>
              <div class="bg-light p-3 rounded mt-2">${this.escapeHtml(
                ticket.message
              ).replace(/\n/g, "<br>")}</div>
            </div>
            ${
              ticket.admin_notes
                ? `
              <div class="mb-3">
                <strong>Admin Notes:</strong>
                <div class="bg-primary bg-opacity-10 p-3 rounded mt-2">${this.escapeHtml(
                  ticket.admin_notes
                ).replace(/\n/g, "<br>")}</div>
              </div>
            `
                : ""
            }
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
            <button type="button" class="btn btn-primary" onclick="window.masterAdminSupport.showReplyModal(${ticketId}); bootstrap.Modal.getInstance(this.closest('.modal')).hide();">
              <i class="fas fa-reply me-2"></i>Reply
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
    modal.addEventListener("hidden.bs.modal", () => modal.remove());
  }

  filterTickets(filter) {
    // Update active filter button
    document
      .querySelectorAll(".masterFilterBtn")
      .forEach((btn) => btn.classList.remove("active"));
    document
      .querySelector(`[data-master-filter="${filter}"]`)
      .classList.add("active");

    // Show/hide tickets
    document.querySelectorAll(".masterTicketCard").forEach((card) => {
      const status = card.dataset.masterStatus;
      card.style.display =
        filter === "all" || status === filter ? "block" : "none";
    });
  }

  searchTickets(query) {
    const searchTerm = query.toLowerCase();

    document.querySelectorAll(".masterTicketCard").forEach((card) => {
      const title = card
        .querySelector(".masterTicketTitle")
        .textContent.toLowerCase();
      const message = card
        .querySelector(".masterTicketMessage")
        .textContent.toLowerCase();

      const matches =
        title.includes(searchTerm) || message.includes(searchTerm);
      card.style.display = matches ? "block" : "none";
    });
  }

  findTicketById(ticketId) {
    return this.tickets.find((t) => t.id == ticketId);
  }

  showAlert(message, type = "info") {
    // Try to use global notification system first
    if (window.showNotification) {
      window.showNotification(message, type);
      return;
    }

    // Fallback alert system
    const alert = document.createElement("div");
    alert.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alert.style.cssText =
      "top: 20px; right: 20px; z-index: 10000; max-width: 400px;";
    alert.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(alert);
    setTimeout(() => {
      if (alert.parentNode) alert.remove();
    }, 5000);
  }

  escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  console.log("Initializing Master Admin Support...");
  window.masterAdminSupport = new MasterAdminSupport();

  // Add some basic styling
  const style = document.createElement("style");
  style.textContent = `
    .pulse { animation: pulse 0.5s ease-in-out; }
    @keyframes pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.1); color: #007bff; }
      100% { transform: scale(1); }
    }
    .masterTicketCard { transition: all 0.2s ease; }
    .masterTicketCard:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
    .masterAdminPanel { border-left: 3px solid #007bff; }
    .reply-item { background: #f8f9fa; border-radius: 6px; padding: 12px; }
    .reply-item.border-primary { background: #e7f3ff; }
    .reply-item.border-secondary { background: #f8f9fa; }
  `;
  document.head.appendChild(style);
});

// Global functions for any inline handlers
window.masterAdminFunctions = {
  updateStatus: (ticketId, status) =>
    window.masterAdminSupport?.updateStatus(ticketId, status),
  showReply: (ticketId) => window.masterAdminSupport?.showReplyModal(ticketId),
  viewTicket: (ticketId) => window.masterAdminSupport?.viewTicket(ticketId),
  toggleReplies: (ticketId) =>
    window.masterAdminSupport?.toggleReplies(ticketId),
};
