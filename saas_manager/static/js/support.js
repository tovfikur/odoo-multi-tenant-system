// ===== support.js - User Support System =====
class SupportSystem {
  constructor() {
    this.tickets = [];
    this.baseUrl = window.location.origin;
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadMyTickets();
  }

  bindEvents() {
    const createForm = document.getElementById("createTicketForm");
    if (createForm) {
      createForm.addEventListener("submit", (e) => this.createTicket(e));
    }
  }

  async loadMyTickets() {
    try {
      const response = await fetch(`${this.baseUrl}/support/api/tickets`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      this.tickets = await response.json();
      this.renderTickets(this.tickets);
    } catch (error) {
      console.error("Failed to load tickets:", error);
      this.showError("Failed to load support tickets. Please try again.");
    }
  }

  renderTickets(tickets) {
    const container = document.getElementById("ticketsContainer");
    if (!container) return;

    if (!tickets || tickets.length === 0) {
      container.innerHTML = `
        <div class="text-center py-5">
          <i class="fas fa-ticket-alt fa-3x text-muted mb-3"></i>
          <h5 class="text-muted mb-2">No Support Tickets</h5>
          <p class="text-muted">You haven't created any support tickets yet</p>
        </div>
      `;
      return;
    }

    const ticketsHtml = tickets
      .map(
        (ticket) => `
      <div class="ticket-card mb-3" data-ticket-id="${ticket.id}">
        <div class="ticket-header">
          <div class="d-flex justify-content-between align-items-start">
            <h6 class="ticket-subject mb-1">${this.escapeHtml(
              ticket.subject
            )}</h6>
            <div class="d-flex gap-2">
              <span class="badge bg-${this.getStatusColor(ticket.status)}">
                ${ticket.status.replace("_", " ").toUpperCase()}
              </span>
              <span class="badge bg-${this.getPriorityColor(ticket.priority)}">
                ${ticket.priority.toUpperCase()}
              </span>
            </div>
          </div>
          <small class="text-muted">
            <i class="fas fa-clock me-1"></i>
            Created: ${this.formatDate(ticket.created_at)}
            ${
              ticket.updated_at !== ticket.created_at
                ? ` • Updated: ${this.formatDate(ticket.updated_at)}`
                : ""
            }
          </small>
        </div>
        
        <div class="ticket-message mt-2">
          ${this.escapeHtml(ticket.message).substring(0, 150)}${
          ticket.message.length > 150 ? "..." : ""
        }
        </div>
        
        ${
          ticket.admin_notes
            ? `
          <div class="admin-response mt-2 p-2 bg-light rounded">
            <h6 class="text-primary mb-1">
              <i class="fas fa-user-shield me-1"></i>Admin Response
            </h6>
            <p class="mb-0 small">${this.escapeHtml(ticket.admin_notes)}</p>
          </div>
        `
            : ""
        }
        
        <div class="ticket-actions mt-3">
          <button class="btn btn-sm btn-outline-primary" onclick="supportSystem.viewTicket(${
            ticket.id
          })">
            <i class="fas fa-eye me-1"></i>View Details
          </button>
          <button class="btn btn-sm btn-outline-info" onclick="supportSystem.toggleConversation(${
            ticket.id
          })">
            <i class="fas fa-comments me-1"></i>
            <span id="conv-btn-${ticket.id}">View Conversation</span>
            ${
              ticket.replies_count > 0
                ? `<span class="badge bg-info ms-1">${ticket.replies_count}</span>`
                : ""
            }
          </button>
          ${
            ticket.status !== "closed"
              ? `
            <button class="btn btn-sm btn-outline-success" onclick="supportSystem.showReplyForm(${ticket.id})">
              <i class="fas fa-reply me-1"></i>Reply
            </button>
          `
              : ""
          }
        </div>
        
        <!-- Conversation Container -->
        <div id="conversation-${
          ticket.id
        }" class="conversation-container mt-3" style="display: none;">
          <div class="conversation-loading text-center py-3">
            <i class="fas fa-spinner fa-spin me-2"></i>Loading conversation...
          </div>
        </div>
        
        <!-- Reply Form Container -->
        <div id="reply-form-${
          ticket.id
        }" class="reply-form-container mt-3" style="display: none;">
          <div class="card">
            <div class="card-body">
              <h6 class="card-title">Add Reply</h6>
              <textarea class="form-control mb-3" id="reply-message-${
                ticket.id
              }" 
                        rows="3" placeholder="Type your message..."></textarea>
              <div class="d-flex gap-2">
                <button class="btn btn-primary btn-sm" onclick="supportSystem.sendReply(${
                  ticket.id
                })">
                  <i class="fas fa-paper-plane me-1"></i>Send Reply
                </button>
                <button class="btn btn-secondary btn-sm" onclick="supportSystem.hideReplyForm(${
                  ticket.id
                })">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `
      )
      .join("");

    container.innerHTML = ticketsHtml;
  }

  async createTicket(e) {
    e.preventDefault();

    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const formData = new FormData(form);

    const ticketData = {
      subject: formData.get("subject"),
      message: formData.get("message"),
      priority: formData.get("priority") || "medium",
    };

    if (!ticketData.subject.trim()) {
      this.showNotification("Please enter a subject", "warning");
      return;
    }

    if (!ticketData.message.trim()) {
      this.showNotification("Please describe your issue", "warning");
      return;
    }

    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML =
      '<i class="fas fa-spinner fa-spin me-2"></i>Creating...';

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

      const response = await fetch(`${this.baseUrl}/support/create`, {
        method: "POST",
        headers,
        body: JSON.stringify(ticketData),
      });

      const result = await response.json();

      if (response.ok && result.success) {
        this.showNotification(
          "Support ticket created successfully!",
          "success"
        );
        form.reset();
        this.loadMyTickets();
      } else {
        this.showNotification(
          result.error || "Failed to create ticket",
          "danger"
        );
      }
    } catch (error) {
      console.error("Error creating ticket:", error);
      this.showNotification("Network error. Please try again.", "danger");
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
    }
  }

  async toggleConversation(ticketId) {
    const container = document.getElementById(`conversation-${ticketId}`);
    const button = document.getElementById(`conv-btn-${ticketId}`);

    if (container.style.display === "none") {
      container.style.display = "block";
      button.textContent = "Hide Conversation";
      await this.loadConversation(ticketId);
    } else {
      container.style.display = "none";
      button.textContent = "View Conversation";
    }
  }

  async loadConversation(ticketId) {
    const container = document.getElementById(`conversation-${ticketId}`);

    try {
      const response = await fetch(
        `${this.baseUrl}/support/ticket/${ticketId}/replies`
      );
      const replies = await response.json();

      if (!replies.length) {
        container.innerHTML = `
          <div class="text-center py-3 text-muted">
            <i class="fas fa-comments me-2"></i>No replies yet
          </div>
        `;
        return;
      }

      const repliesHtml = replies
        .map(
          (reply) => `
        <div class="reply-item ${
          reply.is_admin ? "admin-reply" : "user-reply"
        }">
          <div class="reply-header">
            <strong class="${
              reply.is_admin ? "text-primary" : "text-secondary"
            }">
              <i class="fas fa-${
                reply.is_admin ? "user-shield" : "user"
              } me-1"></i>
              ${reply.is_admin ? "Support Team" : "You"}
            </strong>
            <small class="text-muted ms-2">${this.formatDate(
              reply.created_at
            )}</small>
          </div>
          <div class="reply-message">${this.escapeHtml(reply.message)}</div>
        </div>
      `
        )
        .join("");

      container.innerHTML = `
        <div class="conversation-header">
          <h6><i class="fas fa-comments me-2"></i>Conversation History</h6>
        </div>
        <div class="conversation-messages">
          ${repliesHtml}
        </div>
      `;
    } catch (error) {
      console.error("Failed to load conversation:", error);
      container.innerHTML = `
        <div class="text-center py-3 text-danger">
          <i class="fas fa-exclamation-triangle me-2"></i>Failed to load conversation
        </div>
      `;
    }
  }

  showReplyForm(ticketId) {
    const container = document.getElementById(`reply-form-${ticketId}`);
    container.style.display = "block";
    document.getElementById(`reply-message-${ticketId}`).focus();
  }

  hideReplyForm(ticketId) {
    const container = document.getElementById(`reply-form-${ticketId}`);
    container.style.display = "none";
    document.getElementById(`reply-message-${ticketId}`).value = "";
  }

  async sendReply(ticketId) {
    const messageInput = document.getElementById(`reply-message-${ticketId}`);
    const message = messageInput.value.trim();

    if (!message) {
      this.showNotification("Please enter a message", "warning");
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
        `${this.baseUrl}/support/reply/${ticketId}`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({ message }),
        }
      );

      const result = await response.json();

      if (result.success) {
        this.showNotification("Reply sent successfully!", "success");
        this.hideReplyForm(ticketId);
        this.loadMyTickets();

        // Reload conversation if it's open
        const convContainer = document.getElementById(
          `conversation-${ticketId}`
        );
        if (convContainer.style.display !== "none") {
          this.loadConversation(ticketId);
        }
      } else {
        this.showNotification(result.error || "Failed to send reply", "danger");
      }
    } catch (error) {
      console.error("Error sending reply:", error);
      this.showNotification("Network error. Please try again.", "danger");
    }
  }

  viewTicket(ticketId) {
    const ticket = this.tickets.find((t) => t.id === ticketId);
    if (!ticket) return;

    const modal = document.createElement("div");
    modal.className = "modal fade";
    modal.id = "ticketDetailModal";
    modal.innerHTML = `
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-ticket-alt me-2"></i>${this.escapeHtml(
                ticket.subject
              )}
            </h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <div class="row mb-3">
              <div class="col-md-6">
                <strong>Status:</strong> 
                <span class="badge bg-${this.getStatusColor(ticket.status)}">
                  ${ticket.status.replace("_", " ").toUpperCase()}
                </span>
              </div>
              <div class="col-md-6">
                <strong>Priority:</strong> 
                <span class="badge bg-${this.getPriorityColor(
                  ticket.priority
                )}">
                  ${ticket.priority.toUpperCase()}
                </span>
              </div>
            </div>
            <div class="row mb-3">
              <div class="col-md-6">
                <strong>Created:</strong> ${this.formatDate(ticket.created_at)}
              </div>
              <div class="col-md-6">
                <strong>Last Updated:</strong> ${this.formatDate(
                  ticket.updated_at
                )}
              </div>
            </div>
            <div class="mb-3">
              <strong>Your Message:</strong>
              <div class="bg-light p-3 rounded mt-2">
                ${this.escapeHtml(ticket.message).replace(/\n/g, "<br>")}
              </div>
            </div>
            ${
              ticket.admin_notes
                ? `
              <div class="mb-3">
                <strong>Admin Response:</strong>
                <div class="bg-primary bg-opacity-10 p-3 rounded mt-2">
                  ${this.escapeHtml(ticket.admin_notes).replace(/\n/g, "<br>")}
                </div>
              </div>
            `
                : ""
            }
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
    modal.addEventListener("hidden.bs.modal", () => modal.remove());
  }

  showError(message) {
    console.error("Support System Error:", message);
    this.showNotification(message, "danger");
  }

  showNotification(message, type = "info") {
    if (window.showNotification) {
      window.showNotification(message, type);
      return;
    }

    const notification = document.createElement("div");
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = `
      top: 20px; right: 20px; z-index: 10000; max-width: 400px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    notification.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(notification);
    setTimeout(() => {
      if (notification.parentNode) notification.remove();
    }, 5000);
  }

  escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  formatDate(dateString) {
    if (!dateString) return "N/A";
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
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

  getPriorityColor(priority) {
    const colors = {
      low: "secondary",
      medium: "info",
      high: "warning",
      urgent: "danger",
    };
    return colors[priority] || "secondary";
  }
}

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  window.supportSystem = new SupportSystem();
});
