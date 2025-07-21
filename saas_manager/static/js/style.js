// Enhanced UX JavaScript for Odoo SaaS Platform
// This file contains only UX enhancements, no functionality changes

(function () {
  "use strict";

  // Initialize when DOM is loaded
  document.addEventListener("DOMContentLoaded", function () {
    initializeTheme();
    initializeAnimations();
    initializeInteractiveElements();
    initializeTooltips();
    initializeParallax();
    initializePreloader();
  });

  // Theme Management
  function initializeTheme() {
    const themeToggle = createThemeToggle();
    document.body.appendChild(themeToggle);

    // Load saved theme
    const savedTheme =
      localStorage.getItem("theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light");

    applyTheme(savedTheme);

    // Listen for system theme changes
    window.matchMedia("(prefers-color-scheme: dark)").addListener((e) => {
      if (!localStorage.getItem("theme")) {
        applyTheme(e.matches ? "dark" : "light");
      }
    });
  }

  function createThemeToggle() {
    const toggle = document.createElement("div");
    toggle.className = "theme-toggle";
    toggle.innerHTML = `
            <button id="theme-toggle-btn" class="btn btn-sm btn-outline-secondary" 
                    title="Toggle dark/light mode" style="
                position: fixed;
                top: 80px;
                right: 20px;
                z-index: 1050;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                backdrop-filter: blur(10px);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: var(--shadow-lg);
                border: 2px solid var(--border-primary);
                background: rgba(255, 255, 255, 0.9);
            ">
                <i class="fas fa-sun" id="theme-icon"></i>
            </button>
        `;

    const button = toggle.querySelector("#theme-toggle-btn");
    button.addEventListener("click", toggleTheme);

    // Add hover effects
    button.addEventListener("mouseenter", function () {
      this.style.transform = "scale(1.1) rotate(5deg)";
      this.style.boxShadow = "var(--shadow-xl)";
    });

    button.addEventListener("mouseleave", function () {
      this.style.transform = "scale(1) rotate(0deg)";
      this.style.boxShadow = "var(--shadow-lg)";
    });

    return toggle;
  }

  function toggleTheme() {
    const currentTheme =
      document.documentElement.getAttribute("data-theme") || "light";
    const newTheme = currentTheme === "light" ? "dark" : "light";
    applyTheme(newTheme);
    localStorage.setItem("theme", newTheme);
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);

    const icon = document.getElementById("theme-icon");
    if (icon) {
      // Animate icon change
      icon.style.transform = "rotate(180deg) scale(0)";

      setTimeout(() => {
        icon.className = theme === "dark" ? "fas fa-moon" : "fas fa-sun";
        icon.style.transform = "rotate(0deg) scale(1)";
      }, 150);
    }

    // Animate theme transition
    document.body.style.transition =
      "background-color 0.5s ease, color 0.5s ease";
    setTimeout(() => {
      document.body.style.transition = "";
    }, 500);
  }

  // Animation Enhancements
  function initializeAnimations() {
    // Fade in animation for elements
    const observerOptions = {
      threshold: 0.1,
      rootMargin: "0px 0px -50px 0px",
    };

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("animate-in");
        }
      });
    }, observerOptions);

    // Observe elements for animation
    document
      .querySelectorAll(".card, .alert, .table, .metric-card")
      .forEach((el) => {
        el.style.opacity = "0";
        el.style.transform = "translateY(30px)";
        el.style.transition = "opacity 0.6s ease, transform 0.6s ease";
        observer.observe(el);
      });

    // Add CSS for animate-in class
    if (!document.getElementById("animate-styles")) {
      const style = document.createElement("style");
      style.id = "animate-styles";
      style.textContent = `
                .animate-in {
                    opacity: 1 !important;
                    transform: translateY(0) !important;
                }
                
                .page-transition {
                    animation: pageSlideIn 0.5s ease-out;
                }
                
                @keyframes pageSlideIn {
                    from {
                        opacity: 0;
                        transform: translateX(-30px);
                    }
                    to {
                        opacity: 1;
                        transform: translateX(0);
                    }
                }
                
                .float-animation {
                    animation: float 3s ease-in-out infinite;
                }
                
                @keyframes float {
                    0%, 100% { transform: translateY(0px); }
                    50% { transform: translateY(-10px); }
                }
                
                .pulse-animation {
                    animation: pulse 2s ease-in-out infinite;
                }
                
                @keyframes pulse {
                    0%, 100% { transform: scale(1); opacity: 1; }
                    50% { transform: scale(1.05); opacity: 0.8; }
                }
                
                .typing-animation::after {
                    content: '|';
                    animation: blink 1s infinite;
                }
                
                @keyframes blink {
                    0%, 50% { opacity: 1; }
                    51%, 100% { opacity: 0; }
                }
            `;
      document.head.appendChild(style);
    }
  }

  // Interactive Element Enhancements
  function initializeInteractiveElements() {
    // Enhanced button interactions
    enhanceButtons();

    // Enhanced form interactions
    enhanceForms();

    // Enhanced table interactions
    enhanceTables();

    // Enhanced card interactions
    enhanceCards();

    // Add loading states
    enhanceLoadingStates();

    // Add micro-interactions
    addMicroInteractions();
  }

  function enhanceButtons() {
    document.querySelectorAll(".btn").forEach((button) => {
      // Add ripple effect
      button.addEventListener("click", function (e) {
        const ripple = document.createElement("span");
        const rect = this.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        ripple.style.cssText = `
                    position: absolute;
                    border-radius: 50%;
                    background: rgba(255, 255, 255, 0.6);
                    transform: scale(0);
                    animation: ripple 0.6s linear;
                    width: ${size}px;
                    height: ${size}px;
                    left: ${x}px;
                    top: ${y}px;
                    pointer-events: none;
                `;

        this.style.position = "relative";
        this.style.overflow = "hidden";
        this.appendChild(ripple);

        setTimeout(() => ripple.remove(), 600);
      });

      // Add shine effect on hover
      button.addEventListener("mouseenter", function () {
        if (!this.querySelector(".shine")) {
          const shine = document.createElement("div");
          shine.className = "shine";
          shine.style.cssText = `
                        position: absolute;
                        top: 0;
                        left: -100%;
                        width: 100%;
                        height: 100%;
                        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                        transition: left 0.5s;
                        pointer-events: none;
                    `;
          this.style.position = "relative";
          this.style.overflow = "hidden";
          this.appendChild(shine);

          setTimeout(() => (shine.style.left = "100%"), 50);
          setTimeout(() => shine.remove(), 550);
        }
      });
    });

    // Add ripple animation CSS
    if (!document.getElementById("ripple-styles")) {
      const style = document.createElement("style");
      style.id = "ripple-styles";
      style.textContent = `
                @keyframes ripple {
                    to {
                        transform: scale(2);
                        opacity: 0;
                    }
                }
            `;
      document.head.appendChild(style);
    }
  }

  function enhanceForms() {
    // Floating labels effect
    document
      .querySelectorAll(".form-control, .form-select")
      .forEach((input) => {
        const label = input.previousElementSibling;
        if (label && label.tagName === "LABEL") {
          // Add floating label styles
          label.style.cssText += `
                    position: absolute;
                    top: 0.875rem;
                    left: 1rem;
                    color: var(--text-muted);
                    transition: all 0.2s ease;
                    pointer-events: none;
                    background: var(--bg-primary);
                    padding: 0 0.25rem;
                    z-index: 1;
                `;

          input.parentNode.style.position = "relative";

          const updateLabelPosition = () => {
            if (input.value || input === document.activeElement) {
              label.style.top = "-0.5rem";
              label.style.fontSize = "0.875rem";
              label.style.color = "var(--primary)";
            } else {
              label.style.top = "0.875rem";
              label.style.fontSize = "1rem";
              label.style.color = "var(--text-muted)";
            }
          };

          input.addEventListener("focus", updateLabelPosition);
          input.addEventListener("blur", updateLabelPosition);
          input.addEventListener("input", updateLabelPosition);
          updateLabelPosition();
        }

        // Add focus glow effect
        input.addEventListener("focus", function () {
          this.style.boxShadow =
            "0 0 0 3px rgba(113, 75, 103, 0.15), 0 0 20px rgba(113, 75, 103, 0.1)";
        });

        input.addEventListener("blur", function () {
          this.style.boxShadow = "";
        });
      });

    // Enhanced validation feedback
    document
      .querySelectorAll("input[required], select[required], textarea[required]")
      .forEach((field) => {
        field.addEventListener("invalid", function () {
          this.classList.add("shake-animation");
          setTimeout(() => this.classList.remove("shake-animation"), 500);
        });
      });

    // Add shake animation CSS
    if (!document.getElementById("shake-styles")) {
      const style = document.createElement("style");
      style.id = "shake-styles";
      style.textContent = `
                .shake-animation {
                    animation: shake 0.5s ease-in-out;
                }
                
                @keyframes shake {
                    0%, 100% { transform: translateX(0); }
                    10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
                    20%, 40%, 60%, 80% { transform: translateX(5px); }
                }
            `;
      document.head.appendChild(style);
    }
  }

  function enhanceTables() {
    document.querySelectorAll(".table tbody tr").forEach((row) => {
      // Add subtle hover animation
      row.addEventListener("mouseenter", function () {
        this.style.transform = "translateX(5px)";
        this.style.boxShadow = "var(--shadow-sm)";
      });

      row.addEventListener("mouseleave", function () {
        this.style.transform = "translateX(0)";
        this.style.boxShadow = "none";
      });
    });

    // Sortable column headers
    document
      .querySelectorAll(".table thead th[data-sortable]")
      .forEach((header) => {
        header.style.cursor = "pointer";
        header.style.userSelect = "none";

        const icon = document.createElement("i");
        icon.className = "fas fa-sort ms-2";
        icon.style.opacity = "0.5";
        header.appendChild(icon);

        header.addEventListener("mouseenter", function () {
          icon.style.opacity = "1";
          this.style.backgroundColor = "rgba(255, 255, 255, 0.1)";
        });

        header.addEventListener("mouseleave", function () {
          icon.style.opacity = "0.5";
          this.style.backgroundColor = "transparent";
        });
      });
  }

  function enhanceCards() {
    document.querySelectorAll(".card").forEach((card) => {
      // Add tilt effect on hover
      card.addEventListener("mouseenter", function (e) {
        const rect = this.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const rotateX = (y - centerY) / 20;
        const rotateY = (centerX - x) / 20;

        this.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(10px)`;
      });

      card.addEventListener("mousemove", function (e) {
        const rect = this.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const rotateX = (y - centerY) / 20;
        const rotateY = (centerX - x) / 20;

        this.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(10px)`;
      });

      card.addEventListener("mouseleave", function () {
        this.style.transform =
          "perspective(1000px) rotateX(0) rotateY(0) translateZ(0)";
      });

      // Add shimmer effect to metric cards
      if (card.classList.contains("metric-card")) {
        const shimmer = document.createElement("div");
        shimmer.className = "card-shimmer";
        shimmer.style.cssText = `
                    position: absolute;
                    top: 0;
                    left: -100%;
                    width: 100%;
                    height: 100%;
                    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
                    transition: left 0.8s ease;
                    pointer-events: none;
                    z-index: 1;
                `;

        card.style.position = "relative";
        card.style.overflow = "hidden";
        card.appendChild(shimmer);

        card.addEventListener("mouseenter", () => {
          shimmer.style.left = "100%";
        });

        card.addEventListener("mouseleave", () => {
          setTimeout(() => (shimmer.style.left = "-100%"), 100);
        });
      }
    });
  }

  function enhanceLoadingStates() {
    // Add loading skeleton for tables
    document.querySelectorAll(".table").forEach((table) => {
      if (table.querySelector(".loading-spinner")) {
        createLoadingSkeleton(table);
      }
    });

    // Enhance existing loading spinners
    document.querySelectorAll(".loading-spinner").forEach((spinner) => {
      spinner.style.cssText += `
                background: linear-gradient(45deg, var(--primary), var(--primary-light));
                background-size: 200% 200%;
                animation: spin 1s linear infinite, shimmer 2s ease-in-out infinite;
            `;
    });

    if (!document.getElementById("loading-styles")) {
      const style = document.createElement("style");
      style.id = "loading-styles";
      style.textContent = `
                @keyframes shimmer {
                    0% { background-position: 200% 200%; }
                    100% { background-position: -200% -200%; }
                }
                
                .skeleton {
                    background: linear-gradient(90deg, var(--bg-tertiary) 25%, var(--bg-secondary) 50%, var(--bg-tertiary) 75%);
                    background-size: 200% 100%;
                    animation: loading 1.5s infinite;
                }
                
                @keyframes loading {
                    0% { background-position: 200% 0; }
                    100% { background-position: -200% 0; }
                }
            `;
      document.head.appendChild(style);
    }
  }

  function createLoadingSkeleton(table) {
    const tbody = table.querySelector("tbody");
    if (!tbody) return;

    const skeletonRows = 5;
    const columns = table.querySelectorAll("thead th").length || 4;

    tbody.innerHTML = "";
    for (let i = 0; i < skeletonRows; i++) {
      const row = document.createElement("tr");
      for (let j = 0; j < columns; j++) {
        const cell = document.createElement("td");
        const skeleton = document.createElement("div");
        skeleton.className = "skeleton";
        skeleton.style.cssText = `
                    height: 20px;
                    border-radius: 4px;
                    width: ${Math.random() * 50 + 50}%;
                `;
        cell.appendChild(skeleton);
        row.appendChild(cell);
      }
      tbody.appendChild(row);
    }
  }

  function addMicroInteractions() {
    // Badge hover effects
    document.querySelectorAll(".badge").forEach((badge) => {
      badge.addEventListener("mouseenter", function () {
        this.style.transform = "scale(1.1) rotate(2deg)";
      });

      badge.addEventListener("mouseleave", function () {
        this.style.transform = "scale(1) rotate(0deg)";
      });
    });

    // Icon hover effects
    document.querySelectorAll(".fas, .far, .fab").forEach((icon) => {
      if (!icon.closest(".btn")) {
        // Skip icons in buttons
        icon.addEventListener("mouseenter", function () {
          this.style.transform = "scale(1.2) rotate(5deg)";
          this.style.color = "var(--primary)";
        });

        icon.addEventListener("mouseleave", function () {
          this.style.transform = "scale(1) rotate(0deg)";
          this.style.color = "";
        });
      }
    });

    // Progress bar animations
    document.querySelectorAll(".progress-bar").forEach((bar) => {
      const width = bar.style.width;
      bar.style.width = "0%";

      setTimeout(() => {
        bar.style.width = width;
      }, 300);
    });

    // Status indicator pulse
    document.querySelectorAll(".status-indicator").forEach((indicator) => {
      if (
        indicator.classList.contains("status-healthy") ||
        indicator.classList.contains("status-active")
      ) {
        indicator.classList.add("pulse-animation");
      }
    });
  }

  // Enhanced Tooltips
  function initializeTooltips() {
    // Create custom tooltip
    const tooltip = document.createElement("div");
    tooltip.id = "custom-tooltip";
    tooltip.style.cssText = `
            position: absolute;
            background: var(--gray-900);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            z-index: 9999;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: var(--shadow-lg);
            backdrop-filter: blur(10px);
            max-width: 200px;
            text-align: center;
            pointer-events: none;
        `;
    document.body.appendChild(tooltip);

    // Enhanced tooltip functionality
    document.querySelectorAll("[title], [data-tooltip]").forEach((element) => {
      const tooltipText =
        element.getAttribute("title") || element.getAttribute("data-tooltip");
      element.removeAttribute("title"); // Remove default tooltip

      element.addEventListener("mouseenter", function (e) {
        tooltip.textContent = tooltipText;
        tooltip.style.opacity = "1";
        tooltip.style.visibility = "visible";
        updateTooltipPosition(e);
      });

      element.addEventListener("mousemove", updateTooltipPosition);

      element.addEventListener("mouseleave", function () {
        tooltip.style.opacity = "0";
        tooltip.style.visibility = "hidden";
      });
    });

    function updateTooltipPosition(e) {
      const x = e.clientX;
      const y = e.clientY;
      const tooltipRect = tooltip.getBoundingClientRect();
      const windowWidth = window.innerWidth;
      const windowHeight = window.innerHeight;

      let left = x + 10;
      let top = y - tooltipRect.height - 10;

      // Adjust if tooltip goes off screen
      if (left + tooltipRect.width > windowWidth) {
        left = x - tooltipRect.width - 10;
      }

      if (top < 0) {
        top = y + 10;
      }

      tooltip.style.left = left + "px";
      tooltip.style.top = top + "px";
    }
  }

  // Parallax Effects
  function initializeParallax() {
    const parallaxElements = document.querySelectorAll(
      ".system-header, .metric-card"
    );

    window.addEventListener("scroll", () => {
      const scrolled = window.pageYOffset;
      const rate = scrolled * -0.3;

      parallaxElements.forEach((element) => {
        element.style.transform = `translateY(${rate}px)`;
      });
    });

    // Mouse parallax for cards
    document.addEventListener("mousemove", (e) => {
      const mouseX = e.clientX;
      const mouseY = e.clientY;
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;

      const moveX = (mouseX - centerX) * 0.01;
      const moveY = (mouseY - centerY) * 0.01;

      document.querySelectorAll(".float-animation").forEach((element) => {
        element.style.transform = `translateX(${moveX}px) translateY(${moveY}px)`;
      });
    });
  }

  // Preloader
  function initializePreloader() {
    // Create preloader
    const preloader = document.createElement("div");
    preloader.id = "preloader";
    preloader.innerHTML = `
            <div class="preloader-content">
                <div class="preloader-logo">
                    <i class="fas fa-cloud fa-3x text-primary"></i>
                    <h3 class="mt-3">Odoo SaaS</h3>
                </div>
                <div class="preloader-spinner">
                    <div class="spinner-ring"></div>
                    <div class="spinner-ring"></div>
                    <div class="spinner-ring"></div>
                </div>
            </div>
        `;

    preloader.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            z-index: 10000;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 1;
            visibility: visible;
            transition: all 0.5s ease;
        `;

    // Add preloader styles
    const preloaderStyles = document.createElement("style");
    preloaderStyles.textContent = `
            .preloader-content {
                text-align: center;
                color: white;
            }
            
            .preloader-logo {
                animation: float 2s ease-in-out infinite;
            }
            
            .preloader-spinner {
                position: relative;
                width: 60px;
                height: 60px;
                margin: 20px auto;
            }
            
            .spinner-ring {
                position: absolute;
                width: 100%;
                height: 100%;
                border: 3px solid transparent;
                border-top: 3px solid white;
                border-radius: 50%;
                animation: spin 1.5s linear infinite;
            }
            
            .spinner-ring:nth-child(2) {
                animation-delay: 0.2s;
                border-top-color: rgba(255, 255, 255, 0.7);
            }
            
            .spinner-ring:nth-child(3) {
                animation-delay: 0.4s;
                border-top-color: rgba(255, 255, 255, 0.4);
            }
        `;

    document.head.appendChild(preloaderStyles);
    document.body.appendChild(preloader);

    // Hide preloader when page is loaded
    window.addEventListener("load", () => {
      setTimeout(() => {
        preloader.style.opacity = "0";
        preloader.style.visibility = "hidden";

        setTimeout(() => {
          preloader.remove();
          preloaderStyles.remove();
        }, 500);
      }, 1000);
    });
  }

  // Notification System
  function createNotificationSystem() {
    const container = document.createElement("div");
    container.id = "notification-container";
    container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            max-width: 400px;
        `;
    document.body.appendChild(container);

    window.showNotification = function (
      message,
      type = "info",
      duration = 5000
    ) {
      const notification = document.createElement("div");
      notification.className = `notification notification-${type}`;
      notification.innerHTML = `
                <div class="notification-content">
                    <i class="fas ${getNotificationIcon(type)} me-2"></i>
                    <span>${message}</span>
                    <button class="notification-close ms-auto">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;

      notification.style.cssText = `
                background: var(--bg-primary);
                border: 1px solid var(--border-primary);
                border-radius: var(--border-radius);
                box-shadow: var(--shadow-lg);
                margin-bottom: 10px;
                padding: 15px;
                transform: translateX(100%);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                backdrop-filter: blur(10px);
            `;

      const colors = {
        success: "var(--success)",
        error: "var(--danger)",
        warning: "var(--warning)",
        info: "var(--info)",
      };

      notification.style.borderLeftColor = colors[type] || colors.info;

      container.appendChild(notification);

      // Animate in
      setTimeout(() => {
        notification.style.transform = "translateX(0)";
      }, 100);

      // Close functionality
      const closeBtn = notification.querySelector(".notification-close");
      closeBtn.addEventListener("click", () => closeNotification(notification));

      // Auto close
      setTimeout(() => closeNotification(notification), duration);

      return notification;
    };

    function closeNotification(notification) {
      notification.style.transform = "translateX(100%)";
      setTimeout(() => notification.remove(), 300);
    }

    function getNotificationIcon(type) {
      const icons = {
        success: "fa-check-circle",
        error: "fa-exclamation-circle",
        warning: "fa-exclamation-triangle",
        info: "fa-info-circle",
      };
      return icons[type] || icons.info;
    }
  }

  // Initialize notification system
  createNotificationSystem();

    // Enhanced Page Navigation
    function enhancePageNavigation() {
    // Add page transition effect
    document.body.classList.add("page-transition");

    // Smooth scroll for internal links
    document.querySelectorAll('a[href^="#"]').forEach((link) => {
        link.addEventListener("click", function (e) {
        const href = this.getAttribute("href");
        // Check if href is not just "#" and is a valid selector
        if (href && href !== "#" && href.length > 1) {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
            target.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
            }
        }
        });
    });

  // Add loading state to external links
  document.querySelectorAll('a[href^="http"]').forEach((link) => {
    link.addEventListener("click", function () {
      this.innerHTML += ' <i class="fas fa-spinner fa-spin ms-2"></i>';
    });
  });
};

    // Add loading state to external links
    document.querySelectorAll('a[href^="http"]').forEach((link) => {
      link.addEventListener("click", function () {
        this.innerHTML += ' <i class="fas fa-spinner fa-spin ms-2"></i>';
      });
    });
  }

  // Call enhance navigation
  enhancePageNavigation();

  // Add keyboard shortcuts
  document.addEventListener("keydown", function (e) {
    // Ctrl/Cmd + K for search (if search exists)
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
      e.preventDefault();
      const searchInput = document.querySelector(
        'input[type="search"], input[placeholder*="search" i]'
      );
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }

    // Ctrl/Cmd + D for theme toggle
    if ((e.ctrlKey || e.metaKey) && e.key === "d") {
      e.preventDefault();
      toggleTheme();
    }

    // ESC to close modals
    if (e.key === "Escape") {
      const modal = document.querySelector(".modal.show");
      if (modal) {
        const closeBtn = modal.querySelector(".btn-close");
        if (closeBtn) closeBtn.click();
      }
    }
  });

  // Performance optimization: Debounce scroll events
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // Add scroll-based animations with debouncing
  const debouncedScrollHandler = debounce(() => {
    const scrolled = window.pageYOffset;
    const navbar = document.querySelector(".navbar");

    if (navbar) {
      if (scrolled > 100) {
        navbar.style.backdropFilter = "blur(20px)";
        navbar.style.backgroundColor = "rgba(113, 75, 103, 0.9)";
      } else {
        navbar.style.backdropFilter = "blur(10px)";
        navbar.style.backgroundColor = "";
      }
    }
  }, 16); // ~60fps

  window.addEventListener("scroll", debouncedScrollHandler);
})();
