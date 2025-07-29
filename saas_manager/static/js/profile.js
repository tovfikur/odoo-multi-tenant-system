// Profile Edit JavaScript - Enhanced UX for profile management
(function () {
  "use strict";

  // Profile management class
  class ProfileManager {
    constructor() {
      this.form = document.getElementById("profileForm");
      this.avatarInput = document.getElementById("avatarInput");
      this.avatarPreview = document.getElementById("avatarPreview");
      this.avatarPlaceholder = document.getElementById("avatarPlaceholder");
      this.deleteAvatarBtn = document.getElementById("deleteAvatarBtn");
      this.bioTextarea = document.querySelector("#bio");
      this.bioCount = document.getElementById("bioCount");
      this.passwordInput = document.getElementById("newPassword");
      this.passwordStrength = document.getElementById("passwordStrength");
      this.strengthText = document.getElementById("strengthText");
      this.saveBtn = document.getElementById("saveBtn");

      // Initialize modals with error handling
      this.loadingModal = null;
      this.confirmModal = null;

      // Initialize modals only if the elements exist
      const loadingModalEl = document.getElementById("loadingModal");
      const confirmModalEl = document.getElementById("confirmModal");

      if (
        loadingModalEl &&
        typeof bootstrap !== "undefined" &&
        bootstrap.Modal
      ) {
        try {
          this.loadingModal = new bootstrap.Modal(loadingModalEl);
        } catch (e) {
          console.warn("Failed to initialize loading modal:", e);
        }
      }

      if (
        confirmModalEl &&
        typeof bootstrap !== "undefined" &&
        bootstrap.Modal
      ) {
        try {
          this.confirmModal = new bootstrap.Modal(confirmModalEl);
        } catch (e) {
          console.warn("Failed to initialize confirm modal:", e);
        }
      }

      this.originalFormData = {};
      this.isFormDirty = false;

      this.init();
    }

    init() {
      // Only initialize if form exists
      if (!this.form) {
        console.warn(
          "Profile form not found, skipping ProfileManager initialization"
        );
        return;
      }

      this.bindEvents();
      this.storeOriginalData();
      this.updateBioCount();
      this.setupFormValidation();
      this.setupBeforeUnloadWarning();
    }

    bindEvents() {
      // Avatar upload
      if (this.avatarInput) {
        this.avatarInput.addEventListener("change", (e) =>
          this.handleAvatarUpload(e)
        );
      }

      // Delete avatar
      if (this.deleteAvatarBtn) {
        this.deleteAvatarBtn.addEventListener("click", (e) =>
          this.handleDeleteAvatar(e)
        );
      }

      // Bio character count
      if (this.bioTextarea) {
        this.bioTextarea.addEventListener("input", () => this.updateBioCount());
      }

      // Password strength
      if (this.passwordInput) {
        this.passwordInput.addEventListener("input", () =>
          this.checkPasswordStrength()
        );
      }

      // Form submission
      if (this.form) {
        this.form.addEventListener("submit", (e) => this.handleFormSubmit(e));
      }

      // Track form changes
      this.form.querySelectorAll("input, textarea, select").forEach((field) => {
        field.addEventListener("input", () => this.markFormDirty());
        field.addEventListener("change", () => this.markFormDirty());
      });

      // Username validation
      const usernameField = document.getElementById("username");
      if (usernameField) {
        usernameField.addEventListener("blur", () => this.validateUsername());
      }

      // Email validation
      const emailField = document.getElementById("email");
      if (emailField) {
        emailField.addEventListener("blur", () => this.validateEmail());
      }

      // Website URL validation
      const websiteField = document.getElementById("website");
      if (websiteField) {
        websiteField.addEventListener("blur", () => this.validateWebsite());
      }
    }

    storeOriginalData() {
      if (!this.form) return;

      const formData = new FormData(this.form);
      for (let [key, value] of formData.entries()) {
        this.originalFormData[key] = value;
      }
    }

    markFormDirty() {
      this.isFormDirty = true;
      this.updateSaveButton();
    }

    updateSaveButton() {
      if (!this.saveBtn) return;

      if (this.isFormDirty) {
        this.saveBtn.classList.remove("btn-primary");
        this.saveBtn.classList.add("btn-warning");
        this.saveBtn.innerHTML =
          '<i class="fas fa-save me-2"></i>Save Changes*';
      } else {
        this.saveBtn.classList.remove("btn-warning");
        this.saveBtn.classList.add("btn-primary");
        this.saveBtn.innerHTML = '<i class="fas fa-save me-2"></i>Save Changes';
      }
    }

    setupBeforeUnloadWarning() {
      window.addEventListener("beforeunload", (e) => {
        if (this.isFormDirty) {
          e.preventDefault();
          e.returnValue =
            "You have unsaved changes. Are you sure you want to leave?";
          return e.returnValue;
        }
      });
    }

    async handleAvatarUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      // Validate file type
      const allowedTypes = [
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/gif",
        "image/webp",
      ];
      if (!allowedTypes.includes(file.type)) {
        this.showNotification(
          "Please select a valid image file (JPG, PNG, GIF, WebP)",
          "warning"
        );
        event.target.value = "";
        return;
      }

      // Validate file size (5MB max)
      if (file.size > 5 * 1024 * 1024) {
        this.showNotification("File size must be less than 5MB", "warning");
        event.target.value = "";
        return;
      }

      // Show preview
      const reader = new FileReader();
      reader.onload = (e) => {
        if (this.avatarPreview) {
          this.avatarPreview.src = e.target.result;
          this.avatarPreview.style.display = "block";
        } else if (this.avatarPlaceholder) {
          // Create new img element to replace placeholder
          const img = document.createElement("img");
          img.src = e.target.result;
          img.className = "profile-avatar";
          img.id = "avatarPreview";
          this.avatarPlaceholder.parentNode.replaceChild(
            img,
            this.avatarPlaceholder
          );
          this.avatarPreview = img;
        }

        // Show delete button if not already visible
        if (this.deleteAvatarBtn) {
          this.deleteAvatarBtn.style.display = "inline-block";
        }
      };
      reader.readAsDataURL(file);

      this.markFormDirty();
    }

    async handleDeleteAvatar(event) {
      event.preventDefault();

      const confirmMessage =
        "Are you sure you want to remove your profile picture?";

      // Use native confirm if bootstrap modal is not available
      if (!this.confirmModal) {
        if (!confirm(confirmMessage)) {
          return;
        }

        await this.deleteAvatarRequest();
        return;
      }

      // Use bootstrap modal if available
      const confirmMessageEl = document.getElementById("confirmMessage");
      if (confirmMessageEl) {
        confirmMessageEl.textContent = confirmMessage;
      }

      const confirmBtn = document.getElementById("confirmBtn");
      const modalInstance = this.confirmModal;

      if (confirmBtn) {
        confirmBtn.onclick = async () => {
          modalInstance.hide();
          await this.deleteAvatarRequest();
        };
      }

      modalInstance.show();
    }

    async deleteAvatarRequest() {
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

        const response = await fetch("/api/profile/delete-avatar", {
          method: "POST",
          headers,
        });

        const result = await response.json();

        if (result.success) {
          // Replace image with placeholder
          if (this.avatarPreview) {
            const placeholder = document.createElement("div");
            placeholder.className = "avatar-placeholder";
            placeholder.id = "avatarPlaceholder";
            const usernameField = document.getElementById("username");
            const username = usernameField ? usernameField.value : "U";
            placeholder.textContent = username[0].toUpperCase();
            this.avatarPreview.parentNode.replaceChild(
              placeholder,
              this.avatarPreview
            );
            this.avatarPlaceholder = placeholder;
            this.avatarPreview = null;
          }

          // Hide delete button
          if (this.deleteAvatarBtn) {
            this.deleteAvatarBtn.style.display = "none";
          }

          // Clear file input
          if (this.avatarInput) {
            this.avatarInput.value = "";
          }

          this.showNotification(result.message, "success");
        } else {
          throw new Error(result.error || "Failed to delete avatar");
        }
      } catch (error) {
        console.error("Delete avatar error:", error);
        this.showNotification(
          "Failed to delete avatar. Please try again.",
          "danger"
        );
      }
    }

    updateBioCount() {
      if (this.bioTextarea && this.bioCount) {
        const length = this.bioTextarea.value.length;
        this.bioCount.textContent = length;

        // Color coding
        if (length > 450) {
          this.bioCount.style.color = "var(--danger)";
        } else if (length > 350) {
          this.bioCount.style.color = "var(--warning)";
        } else {
          this.bioCount.style.color = "var(--text-muted)";
        }
      }
    }

    checkPasswordStrength() {
      if (!this.passwordInput) return;

      const password = this.passwordInput.value;
      const strength = this.calculatePasswordStrength(password);

      if (this.passwordStrength && this.strengthText) {
        // Update strength bar
        this.passwordStrength.className = `password-strength strength-${strength.level}`;
        this.passwordStrength.style.width = `${strength.score}%`;

        // Update strength text
        this.strengthText.textContent = strength.text;
        this.strengthText.className = `text-${strength.color}`;
      }
    }

    calculatePasswordStrength(password) {
      if (!password) {
        return { level: "none", score: 0, text: "-", color: "muted" };
      }

      let score = 0;
      let level = "weak";
      let color = "danger";

      // Length check
      if (password.length >= 8) score += 25;
      if (password.length >= 12) score += 15;

      // Character variety
      if (/[a-z]/.test(password)) score += 15;
      if (/[A-Z]/.test(password)) score += 15;
      if (/[0-9]/.test(password)) score += 15;
      if (/[^A-Za-z0-9]/.test(password)) score += 15;

      // Determine level
      if (score >= 80) {
        level = "strong";
        color = "success";
      } else if (score >= 50) {
        level = "medium";
        color = "warning";
      }

      return {
        level,
        score: Math.min(score, 100),
        text: level.charAt(0).toUpperCase() + level.slice(1),
        color,
      };
    }

    async validateUsername() {
      const usernameField = document.getElementById("username");
      if (!usernameField) return true;

      const username = usernameField.value.trim();

      if (username.length < 3) {
        this.setFieldError(
          usernameField,
          "Username must be at least 3 characters long"
        );
        return false;
      }

      if (!/^[a-zA-Z0-9_]+$/.test(username)) {
        this.setFieldError(
          usernameField,
          "Username can only contain letters, numbers, and underscores"
        );
        return false;
      }

      this.clearFieldError(usernameField);
      return true;
    }

    validateEmail() {
      const emailField = document.getElementById("email");
      if (!emailField) return true;

      const email = emailField.value.trim();
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

      if (!emailRegex.test(email)) {
        this.setFieldError(emailField, "Please enter a valid email address");
        return false;
      }

      this.clearFieldError(emailField);
      return true;
    }

    validateWebsite() {
      const websiteField = document.getElementById("website");
      if (!websiteField) return true;

      const website = websiteField.value.trim();

      if (website && !this.isValidUrl(website)) {
        this.setFieldError(
          websiteField,
          "Please enter a valid URL (e.g., https://example.com)"
        );
        return false;
      }

      this.clearFieldError(websiteField);
      return true;
    }

    isValidUrl(string) {
      try {
        new URL(string);
        return true;
      } catch (_) {
        return false;
      }
    }

    setFieldError(field, message) {
      this.clearFieldError(field);

      field.classList.add("is-invalid");
      const errorDiv = document.createElement("div");
      errorDiv.className = "invalid-feedback";
      errorDiv.textContent = message;
      field.parentNode.appendChild(errorDiv);
    }

    clearFieldError(field) {
      field.classList.remove("is-invalid");
      const errorDiv = field.parentNode.querySelector(".invalid-feedback");
      if (errorDiv) {
        errorDiv.remove();
      }
    }

    async handleFormSubmit(event) {
      event.preventDefault();

      // Validate all fields
      const isUsernameValid = await this.validateUsername();
      const isEmailValid = this.validateEmail();
      const isWebsiteValid = this.validateWebsite();

      if (!isUsernameValid || !isEmailValid || !isWebsiteValid) {
        this.showNotification(
          "Please fix the errors before submitting",
          "warning"
        );
        return;
      }

      // Check password requirements
      const newPasswordField = document.getElementById("newPassword");
      const currentPasswordField = document.getElementById("currentPassword");

      const newPassword = newPasswordField ? newPasswordField.value : "";
      const currentPassword = currentPasswordField
        ? currentPasswordField.value
        : "";

      if (newPassword && !currentPassword) {
        this.showNotification(
          "Current password is required to set a new password",
          "warning"
        );
        if (currentPasswordField) {
          currentPasswordField.focus();
        }
        return;
      }

      if (newPassword && newPassword.length < 6) {
        this.showNotification(
          "New password must be at least 6 characters long",
          "warning"
        );
        if (newPasswordField) {
          newPasswordField.focus();
        }
        return;
      }

      // Show loading
      if (this.loadingModal) {
        this.loadingModal.show();
      }

      if (this.saveBtn) {
        this.saveBtn.disabled = true;
      }

      try {
        // Handle avatar upload if needed
        if (this.avatarInput && this.avatarInput.files[0]) {
          await this.uploadAvatar(this.avatarInput.files[0]);
        }

        // Submit form
        this.form.submit();
      } catch (error) {
        console.error("Form submission error:", error);

        if (this.loadingModal) {
          this.loadingModal.hide();
        }

        if (this.saveBtn) {
          this.saveBtn.disabled = false;
        }

        this.showNotification(
          "An error occurred while saving. Please try again.",
          "danger"
        );
      }
    }

    async uploadAvatar(file) {
      const formData = new FormData();
      formData.append("avatar", file);

      const headers = {
        "X-Requested-With": "XMLHttpRequest",
      };
      
      // Add CSRF token
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                       document.querySelector('input[name="csrf_token"]')?.value;
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }

      const response = await fetch("/api/profile/upload-avatar", {
        method: "POST",
        body: formData,
        headers,
      });

      const result = await response.json();
      if (!result.success) {
        throw new Error(result.error || "Avatar upload failed");
      }

      return result;
    }

    setupFormValidation() {
      if (!this.form) return;

      // Real-time validation
      const requiredFields = this.form.querySelectorAll("[required]");
      requiredFields.forEach((field) => {
        field.addEventListener("blur", () => {
          if (!field.value.trim()) {
            this.setFieldError(field, "This field is required");
          } else {
            this.clearFieldError(field);
          }
        });

        field.addEventListener("input", () => {
          if (field.value.trim()) {
            this.clearFieldError(field);
          }
        });
      });

      // Password confirmation validation
      const confirmPassword = document.getElementById("confirmPassword");
      const newPassword = document.getElementById("newPassword");

      if (confirmPassword && newPassword) {
        const validatePasswordMatch = () => {
          if (
            confirmPassword.value &&
            confirmPassword.value !== newPassword.value
          ) {
            this.setFieldError(confirmPassword, "Passwords do not match");
          } else {
            this.clearFieldError(confirmPassword);
          }
        };

        confirmPassword.addEventListener("blur", validatePasswordMatch);
        confirmPassword.addEventListener("input", validatePasswordMatch);
        newPassword.addEventListener("input", validatePasswordMatch);
      }
    }

    showNotification(message, type = "info") {
      // Use the global notification system if available
      if (window.showNotification) {
        window.showNotification(message, type);
        return;
      }

      // Fallback notification
      const alertDiv = document.createElement("div");
      alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
      alertDiv.style.cssText =
        "top: 20px; right: 20px; z-index: 9999; max-width: 400px;";
      alertDiv.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;

      document.body.appendChild(alertDiv);

      // Auto remove after 5 seconds
      setTimeout(() => {
        if (alertDiv.parentNode) {
          alertDiv.remove();
        }
      }, 5000);
    }
  }

  // Utility functions
  window.resetForm = function () {
    const form = document.getElementById("profileForm");
    if (!form) return;

    if (
      confirm(
        "Are you sure you want to reset all changes? This will restore the original values."
      )
    ) {
      form.reset();

      // Reset avatar preview
      const avatarPreview = document.getElementById("avatarPreview");
      const avatarPlaceholder = document.getElementById("avatarPlaceholder");
      const avatarInput = document.getElementById("avatarInput");

      if (avatarInput) {
        avatarInput.value = "";
      }

      // Reset bio count
      const bioCount = document.getElementById("bioCount");
      const bioTextarea = document.getElementById("bio");
      if (bioCount && bioTextarea) {
        bioCount.textContent = bioTextarea.value.length;
      }

      // Reset password strength
      const passwordStrength = document.getElementById("passwordStrength");
      const strengthText = document.getElementById("strengthText");
      if (passwordStrength && strengthText) {
        passwordStrength.className = "password-strength";
        passwordStrength.style.width = "0%";
        strengthText.textContent = "-";
        strengthText.className = "text-muted";
      }

      // Clear all field errors
      form.querySelectorAll(".is-invalid").forEach((field) => {
        field.classList.remove("is-invalid");
      });
      form.querySelectorAll(".invalid-feedback").forEach((error) => {
        error.remove();
      });

      if (window.profileManager) {
        window.profileManager.isFormDirty = false;
        window.profileManager.updateSaveButton();
      }
    }
  };

  // Keyboard shortcuts
  document.addEventListener("keydown", function (e) {
    // Ctrl/Cmd + S to save
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      const saveBtn = document.getElementById("saveBtn");
      if (saveBtn && !saveBtn.disabled) {
        saveBtn.click();
      }
    }

    // Escape to reset form
    if (e.key === "Escape") {
      const activeModal = document.querySelector(".modal.show");
      if (!activeModal && window.resetForm) {
        window.resetForm();
      }
    }
  });

  // Initialize profile manager when DOM is ready
  document.addEventListener("DOMContentLoaded", function () {
    // Check if we're on a profile page before initializing
    const profileForm = document.getElementById("profileForm");
    if (!profileForm) {
      console.log(
        "Profile form not found, skipping ProfileManager initialization"
      );
      return;
    }

    try {
      window.profileManager = new ProfileManager();
    } catch (error) {
      console.error("Failed to initialize ProfileManager:", error);
      // Continue with basic functionality even if ProfileManager fails
    }

    // Add smooth scrolling to validation errors
    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        if (mutation.type === "childList") {
          const errorElement =
            mutation.target.querySelector(".invalid-feedback");
          if (errorElement) {
            errorElement.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
          }
        }
      });
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });

    // Auto-save draft functionality (optional) - Only if localStorage is available
    let autoSaveTimer;
    const form = document.getElementById("profileForm");

    if (form && typeof Storage !== "undefined") {
      form.addEventListener("input", function () {
        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(() => {
          // Save form data to localStorage as draft
          const formData = new FormData(form);
          const draftData = {};
          for (let [key, value] of formData.entries()) {
            draftData[key] = value;
          }

          try {
            localStorage.setItem("profile_draft", JSON.stringify(draftData));
          } catch (e) {
            // localStorage not available or full
            console.warn("Could not save draft:", e);
          }
        }, 2000); // Save draft after 2 seconds of inactivity
      });

      // Load draft on page load
      try {
        const savedDraft = localStorage.getItem("profile_draft");
        if (
          savedDraft &&
          confirm(
            "You have unsaved changes from a previous session. Would you like to restore them?"
          )
        ) {
          const draftData = JSON.parse(savedDraft);
          Object.keys(draftData).forEach((key) => {
            const field = form.querySelector(`[name="${key}"]`);
            if (field && field.value !== draftData[key]) {
              field.value = draftData[key];
              field.dispatchEvent(new Event("input", { bubbles: true }));
            }
          });
        }
      } catch (e) {
        console.warn("Could not load draft:", e);
      }

      // Clear draft when form is successfully submitted
      form.addEventListener("submit", function () {
        try {
          localStorage.removeItem("profile_draft");
        } catch (e) {
          // localStorage not available
        }
      });
    }

    // Add tooltips to form elements - Only if Bootstrap is available
    if (typeof bootstrap !== "undefined" && bootstrap.Tooltip) {
      const tooltipElements = [
        {
          selector: "#username",
          title:
            "Your unique username for login. Can contain letters, numbers and underscores.",
        },
        {
          selector: "#email",
          title: "Your email address for notifications and account recovery.",
        },
        {
          selector: "#bio",
          title:
            "Tell others about yourself. This will be visible on your profile.",
        },
        {
          selector: "#timezone",
          title: "Used for displaying dates and times in your local timezone.",
        },
        {
          selector: "#newPassword",
          title: "Choose a strong password with at least 6 characters.",
        },
      ];

      tooltipElements.forEach(({ selector, title }) => {
        const element = document.querySelector(selector);
        if (element) {
          element.setAttribute("title", title);
          element.setAttribute("data-bs-toggle", "tooltip");
          try {
            new bootstrap.Tooltip(element);
          } catch (e) {
            console.warn("Failed to initialize tooltip for", selector, e);
          }
        }
      });
    }
  });

  // Export for global access
  window.ProfileManager = ProfileManager;
})();
