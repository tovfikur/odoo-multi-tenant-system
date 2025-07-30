// Enhanced Error Page Interactions
document.addEventListener("DOMContentLoaded", function () {
  // Initialize all animations and interactions
  initializeParticleSystem();
  initializeScrollReveal();
  initializeButtonAnimations();
  initializeInteractiveElements();
  initializeMouseEffects();
  initializeKeyboardNavigation();
});

// Go back function
function goBack() {
  if (window.history.length > 1) {
    window.history.back();
  } else {
    window.location.href = "/";
  }
}

// Particle System for Background
function initializeParticleSystem() {
  const container = document.querySelector(".floating-bg");
  if (!container) return;

  // Create additional floating particles
  for (let i = 0; i < 8; i++) {
    const particle = document.createElement("div");
    particle.className = "floating-particle";
    particle.style.cssText = `
            position: absolute;
            width: ${Math.random() * 40 + 20}px;
            height: ${Math.random() * 40 + 20}px;
            background: rgba(255, 255, 255, ${Math.random() * 0.1 + 0.02});
            border-radius: 50%;
            backdrop-filter: blur(10px);
            animation: float ${Math.random() * 4 + 4}s ease-in-out infinite;
            animation-delay: ${Math.random() * 2}s;
            top: ${Math.random() * 100}%;
            left: ${Math.random() * 100}%;
        `;
    container.appendChild(particle);
  }
}

// Scroll Reveal Animation
function initializeScrollReveal() {
  const observerOptions = {
    threshold: 0.1,
    rootMargin: "0px 0px -50px 0px",
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
      }
    });
  }, observerOptions);

  // Observe elements that should animate on scroll
  document
    .querySelectorAll(".error-suggestions, .error-actions")
    .forEach((el) => {
      el.style.opacity = "0";
      el.style.transform = "translateY(30px)";
      el.style.transition = "all 0.6s cubic-bezier(0.4, 0, 0.2, 1)";
      observer.observe(el);
    });

  // Add visible class styles
  const style = document.createElement("style");
  style.textContent = `
        .visible {
            opacity: 1 !important;
            transform: translateY(0) !important;
        }
    `;
  document.head.appendChild(style);
}

// Enhanced Button Animations
function initializeButtonAnimations() {
  const buttons = document.querySelectorAll(".btn-primary, .btn-secondary");

  buttons.forEach((button) => {
    // Ripple effect
    button.addEventListener("click", function (e) {
      const ripple = document.createElement("span");
      const rect = this.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const x = e.clientX - rect.left - size / 2;
      const y = e.clientY - rect.top - size / 2;

      ripple.style.cssText = `
                position: absolute;
                width: ${size}px;
                height: ${size}px;
                left: ${x}px;
                top: ${y}px;
                background: rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                transform: scale(0);
                animation: ripple 0.6s linear;
                pointer-events: none;
            `;

      this.appendChild(ripple);

      setTimeout(() => {
        ripple.remove();
      }, 600);
    });

    // Hover sound effect (visual feedback)
    button.addEventListener("mouseenter", function () {
      this.style.transform = "translateY(-3px) scale(1.02)";
    });

    button.addEventListener("mouseleave", function () {
      this.style.transform = "translateY(0) scale(1)";
    });
  });

  // Add ripple animation to CSS
  const style = document.createElement("style");
  style.textContent = `
        @keyframes ripple {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
        .btn-primary, .btn-secondary {
            position: relative;
            overflow: hidden;
        }
    `;
  document.head.appendChild(style);
}

// Interactive Elements
function initializeInteractiveElements() {
  // Shake error logo on click
  const errorLogo = document.querySelector(".error-logo i");
  if (errorLogo) {
    errorLogo.addEventListener("click", function () {
      this.style.animation = "none";
      setTimeout(() => {
        this.style.animation = "";
        this.style.animation = "shake 0.5s ease-in-out";
      }, 10);
    });
  }

  // Pulse error code on hover
  const errorCode = document.querySelector(".error-code");
  if (errorCode) {
    errorCode.addEventListener("mouseenter", function () {
      this.style.transform = "scale(1.05)";
      this.style.transition = "transform 0.3s ease";
    });

    errorCode.addEventListener("mouseleave", function () {
      this.style.transform = "scale(1)";
    });
  }

  // Interactive suggestions
  const suggestionItems = document.querySelectorAll(".error-suggestions li");
  suggestionItems.forEach((item, index) => {
    item.addEventListener("mouseenter", function () {
      this.style.transform = "translateX(10px)";
      this.style.transition = "transform 0.3s ease";
      this.style.backgroundColor = "rgba(255, 255, 255, 0.1)";
      this.style.borderRadius = "8px";
      this.style.padding = "8px";
    });

    item.addEventListener("mouseleave", function () {
      this.style.transform = "translateX(0)";
      this.style.backgroundColor = "transparent";
      this.style.padding = "0";
    });
  });
}

// Mouse Movement Effects
function initializeMouseEffects() {
  const errorContainer = document.querySelector(".error-container");
  if (!errorContainer) return;

  let mouseX = 0;
  let mouseY = 0;
  let isMoving = false;

  document.addEventListener("mousemove", function (e) {
    mouseX = e.clientX;
    mouseY = e.clientY;
    isMoving = true;

    clearTimeout(window.mouseTimeout);
    window.mouseTimeout = setTimeout(() => {
      isMoving = false;
    }, 100);

    // Parallax effect for floating elements
    const floatingElements = document.querySelectorAll(
      ".floating-element, .floating-particle"
    );
    floatingElements.forEach((element, index) => {
      const speed = (index + 1) * 0.02;
      const x = (mouseX - window.innerWidth / 2) * speed;
      const y = (mouseY - window.innerHeight / 2) * speed;

      element.style.transform = `translate(${x}px, ${y}px)`;
    });

    // Subtle tilt effect for error content
    const errorContent = document.querySelector(".error-content");
    if (errorContent) {
      const tiltX =
        ((mouseY - window.innerHeight / 2) / window.innerHeight) * 5;
      const tiltY = ((mouseX - window.innerWidth / 2) / window.innerWidth) * 5;

      errorContent.style.transform = `perspective(1000px) rotateX(${tiltX}deg) rotateY(${tiltY}deg)`;
    }
  });

  // Reset on mouse leave
  document.addEventListener("mouseleave", function () {
    const errorContent = document.querySelector(".error-content");
    if (errorContent) {
      errorContent.style.transform =
        "perspective(1000px) rotateX(0deg) rotateY(0deg)";
    }
  });
}

// Keyboard Navigation and Accessibility
function initializeKeyboardNavigation() {
  // Enable keyboard navigation for buttons
  const buttons = document.querySelectorAll(".btn-primary, .btn-secondary");

  buttons.forEach((button) => {
    button.addEventListener("keydown", function (e) {
      if (e.code === "Space" || e.code === "Enter") {
        e.preventDefault();
        this.click();
      }
    });

    // Focus styles
    button.addEventListener("focus", function () {
      this.style.outline = "2px solid rgba(102, 126, 234, 0.5)";
      this.style.outlineOffset = "2px";
    });

    button.addEventListener("blur", function () {
      this.style.outline = "none";
    });
  });

  // Global keyboard shortcuts
  document.addEventListener("keydown", function (e) {
    switch (e.code) {
      case "Escape":
        // Go back on escape
        goBack();
        break;
      case "KeyR":
        if (e.ctrlKey || e.metaKey) {
          // Prevent default refresh and use custom reload
          e.preventDefault();
          location.reload();
        }
        break;
      case "KeyG":
        if (e.altKey) {
          // Alt+G to go home
          e.preventDefault();
          window.location.href = "/";
        }
        break;
    }
  });
}

// Dynamic Background Color Based on Error Type
function setErrorTheme() {
  const title = document.title;
  const body = document.body;

  const themes = {
    400: { primary: "#f59e0b", secondary: "#fbbf24" },
    401: { primary: "#ef4444", secondary: "#f87171" },
    403: { primary: "#dc2626", secondary: "#ef4444" },
    404: { primary: "#8b5cf6", secondary: "#a78bfa" },
    500: { primary: "#f59e0b", secondary: "#fbbf24" },
    502: { primary: "#06b6d4", secondary: "#22d3ee" },
    503: { primary: "#10b981", secondary: "#34d399" },
    504: { primary: "#8b5cf6", secondary: "#a78bfa" },
  };

  // Extract error code from title
  const errorCode = title.match(/\d{3}/)?.[0];
  if (errorCode && themes[errorCode]) {
    const theme = themes[errorCode];
    body.style.setProperty("--accent-color", theme.primary);
    body.style.setProperty("--accent-secondary", theme.secondary);
  }
}

// Initialize theme
setErrorTheme();

// Add custom cursor trail effect
function initializeCursorTrail() {
  const trail = [];
  const trailLength = 10;

  for (let i = 0; i < trailLength; i++) {
    const dot = document.createElement("div");
    dot.className = "cursor-trail";
    dot.style.cssText = `
            position: fixed;
            width: 4px;
            height: 4px;
            background: rgba(102, 126, 234, ${0.8 - i * 0.08});
            border-radius: 50%;
            pointer-events: none;
            z-index: 9999;
            transition: all 0.1s ease;
        `;
    document.body.appendChild(dot);
    trail.push(dot);
  }

  let mouseX = 0;
  let mouseY = 0;

  document.addEventListener("mousemove", (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  });

  function animateTrail() {
    let x = mouseX;
    let y = mouseY;

    trail.forEach((dot, index) => {
      const nextDot = trail[index + 1] || trail[0];

      dot.style.left = x - 2 + "px";
      dot.style.top = y - 2 + "px";

      if (nextDot) {
        x += (nextDot.offsetLeft - x) * 0.3;
        y += (nextDot.offsetTop - y) * 0.3;
      }
    });

    requestAnimationFrame(animateTrail);
  }

  animateTrail();
}

// Initialize cursor trail on non-touch devices
if (!("ontouchstart" in window)) {
  initializeCursorTrail();
}

// Performance optimization: Throttle heavy animations
function throttle(func, limit) {
  let inThrottle;
  return function () {
    const args = arguments;
    const context = this;
    if (!inThrottle) {
      func.apply(context, args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

// Optimize mouse move events
const optimizedMouseMove = throttle(function (e) {
  // Heavy mouse move operations here
}, 16); // ~60fps

document.addEventListener("mousemove", optimizedMouseMove);

// Clean up on page unload
window.addEventListener("beforeunload", function () {
  // Remove event listeners and clean up
  document.querySelectorAll(".cursor-trail").forEach((el) => el.remove());
});

// Add loading animation
window.addEventListener("load", function () {
  document.body.classList.add("loaded");

  // Add loaded class styles
  const style = document.createElement("style");
  style.textContent = `
        body {
            opacity: 0;
            transition: opacity 0.5s ease;
        }
        body.loaded {
            opacity: 1;
        }
    `;
  document.head.appendChild(style);
});

// Mobile-Optimized Error Page Interactions
document.addEventListener("DOMContentLoaded", function () {
  // Prevent horizontal scrolling
  preventHorizontalScroll();

  // Set proper viewport height
  setViewportHeight();

  // Initialize core functionality
  initializeButtonAnimations();
  initializeInteractiveElements();
  initializeKeyboardNavigation();

  // Initialize visual effects only on larger screens
  if (window.innerWidth > 768) {
    initializeParticleSystem();
    initializeMouseEffects();
  }

  // Initialize scroll reveal with better performance
  initializeScrollReveal();

  // Initialize mobile-specific features
  initializeMobileFeatures();

  // Set loading state
  document.body.classList.add("loaded");
});

// Prevent horizontal scrolling and ensure proper sizing
function preventHorizontalScroll() {
  // Prevent horizontal overflow
  document.documentElement.style.overflowX = "hidden";
  document.body.style.overflowX = "hidden";
  document.body.style.maxWidth = "100vw";
  document.body.style.width = "100%";

  // Handle window resize
  let resizeTimeout;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(function () {
      setViewportHeight();
      // Reinitialize effects on larger screens after resize
      if (
        window.innerWidth > 768 &&
        !document.querySelector(".floating-particle")
      ) {
        initializeParticleSystem();
      }
    }, 250);
  });
}
