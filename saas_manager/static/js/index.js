// Index Page JavaScript - Complete Functionality & Enhancements

(function () {
  "use strict";

  // Initialize when DOM is loaded
  document.addEventListener("DOMContentLoaded", function () {
    initScrollAnimations();
    initNavbarScroll();
    initCounterAnimations();
    initSmoothScrolling();
    initParallaxEffects();
    initMicroInteractions();

    // Enhanced features
    initParticleSystem();
    initInteractiveCards();
    initSectionDividers();
    initDynamicBackground();
    initAdvancedAnimations();
    initUniqueInteractions();
    initPerformanceOptimizations();
  });

  // Original Index Page JavaScript from HTML
  function initScrollAnimations() {
    const observerOptions = {
      threshold: 0.1,
      rootMargin: "0px 0px -50px 0px",
    };

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("revealed");

          // Stagger child animations
          const children = entry.target.querySelectorAll(
            ".feature-card-modern"
          );
          children.forEach((child, index) => {
            setTimeout(() => {
              child.style.animationDelay = index * 0.1 + "s";
              child.classList.add("revealed");
            }, index * 100);
          });
        }
      });
    }, observerOptions);

    document.querySelectorAll(".scroll-reveal").forEach((el) => {
      observer.observe(el);
    });
  }

  function initNavbarScroll() {
    const navbar = document.getElementById("mainNavbar");
    let lastScrollY = window.scrollY;

    window.addEventListener(
      "scroll",
      () => {
        const currentScrollY = window.scrollY;

        if (currentScrollY > 50) {
          navbar.classList.add("scrolled");
        } else {
          navbar.classList.remove("scrolled");
        }

        // Hide/show navbar on scroll
        if (currentScrollY > lastScrollY && currentScrollY > 200) {
          navbar.style.transform = "translateY(-100%)";
        } else {
          navbar.style.transform = "translateY(0)";
        }

        lastScrollY = currentScrollY;
      },
      { passive: true }
    );
  }

  function initCounterAnimations() {
    const counters = document.querySelectorAll(".stat-number[data-target]");

    const animateCounter = (counter, target) => {
      const duration = 2000;
      const start = 0;
      const increment = target / (duration / 16);
      let current = start;

      const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
          current = target;
          clearInterval(timer);
        }

        if (target === 99.9) {
          counter.textContent = current.toFixed(1);
        } else {
          counter.textContent = Math.floor(current).toLocaleString();
        }
      }, 16);
    };

    const statsObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            counters.forEach((counter) => {
              const target = parseFloat(counter.getAttribute("data-target"));
              animateCounter(counter, target);
            });
            statsObserver.disconnect();
          }
        });
      },
      { threshold: 0.5 }
    );

    const statsSection = document.getElementById("stats");
    if (statsSection) {
      statsObserver.observe(statsSection);
    }
  }

  function initSmoothScrolling() {
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener("click", function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute("href"));
        if (target) {
          const offsetTop = target.offsetTop - 80;
          window.scrollTo({
            top: offsetTop,
            behavior: "smooth",
          });
        }
      });
    });
  }

  function initParallaxEffects() {
    const floatingElements = document.querySelectorAll(".floating-element");

    window.addEventListener(
      "scroll",
      () => {
        const scrolled = window.pageYOffset;
        const rate = scrolled * -0.5;

        floatingElements.forEach((element, index) => {
          const speed = (index + 1) * 0.1;
          element.style.transform = `translateY(${rate * speed}px) rotate(${
            scrolled * 0.1
          }deg)`;
        });
      },
      { passive: true }
    );

    // Mouse parallax for hero elements
    document.addEventListener("mousemove", (e) => {
      const mouseX = e.clientX;
      const mouseY = e.clientY;
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;

      const moveX = (mouseX - centerX) * 0.01;
      const moveY = (mouseY - centerY) * 0.01;

      floatingElements.forEach((element, index) => {
        const multiplier = (index + 1) * 0.5;
        element.style.transform += ` translate(${moveX * multiplier}px, ${
          moveY * multiplier
        }px)`;
      });
    });
  }

  function initMicroInteractions() {
    // Enhanced button hover effects
    document
      .querySelectorAll(".btn-hero-primary, .btn-hero-secondary")
      .forEach((button) => {
        button.addEventListener("mouseenter", function () {
          this.style.transform = "translateY(-3px) scale(1.02)";
        });

        button.addEventListener("mouseleave", function () {
          this.style.transform = "translateY(0) scale(1)";
        });

        // Click ripple effect
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
      });

    // Feature card magnetic effect
    document.querySelectorAll(".feature-card-modern").forEach((card) => {
      card.addEventListener("mousemove", (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;

        const strength = 0.1;
        card.style.transform = `translateY(-10px) translate(${
          x * strength
        }px, ${y * strength}px)`;
      });

      card.addEventListener("mouseleave", () => {
        card.style.transform = "translateY(0) translate(0px, 0px)";
      });
    });

    // Dashboard preview interaction
    const dashboard = document.querySelector(".dashboard-preview");
    if (dashboard) {
      dashboard.addEventListener("mousemove", (e) => {
        const rect = dashboard.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const rotateX = (y - centerY) / 20;
        const rotateY = (centerX - x) / 20;

        dashboard.style.transform = `perspective(1000px) rotateY(${
          -5 + rotateY
        }deg) rotateX(${2 + rotateX}deg) translateY(-10px)`;
      });

      dashboard.addEventListener("mouseleave", () => {
        dashboard.style.transform =
          "perspective(1000px) rotateY(-5deg) rotateX(2deg) translateY(0)";
      });
    }
  }

  // Add ripple animation CSS
  const style = document.createElement("style");
  style.textContent = `
    @keyframes ripple {
      to {
        transform: scale(2);
        opacity: 0;
      }
    }
  `;
  document.head.appendChild(style);

  // Particle System for Background
  function initParticleSystem() {
    const hero = document.querySelector(".hero-modern");
    if (!hero) return;

    // Create particle container
    const particleContainer = document.createElement("div");
    particleContainer.className = "particle-container";
    hero.appendChild(particleContainer);

    // Create particles
    function createParticle() {
      const particle = document.createElement("div");
      particle.className = "particle";

      // Random size between 3-8px
      const size = Math.random() * 5 + 3;
      particle.style.width = size + "px";
      particle.style.height = size + "px";

      // Random starting position
      particle.style.left = Math.random() * 100 + "%";
      particle.style.top = "100%";

      // Random animation delay
      particle.style.animationDelay = Math.random() * 5 + "s";

      particleContainer.appendChild(particle);

      // Remove particle after animation
      setTimeout(() => {
        if (particle.parentNode) {
          particle.parentNode.removeChild(particle);
        }
      }, 25000);
    }

    // Create particles periodically
    const particleInterval = setInterval(() => {
      if (document.hidden || !document.querySelector(".hero-modern")) {
        clearInterval(particleInterval);
        return;
      }
      createParticle();
    }, 800);

    // Initial burst of particles
    for (let i = 0; i < 10; i++) {
      setTimeout(() => createParticle(), i * 200);
    }
  }

  // Enhanced Interactive Cards
  function initInteractiveCards() {
    const cards = document.querySelectorAll(
      ".feature-card-modern, .metric-card"
    );

    cards.forEach((card) => {
      // Add interactive feedback class
      card.classList.add("interactive-feedback");

      // Mouse tracking for dynamic effects
      card.addEventListener("mousemove", function (e) {
        const rect = this.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width) * 100;
        const y = ((e.clientY - rect.top) / rect.height) * 100;

        this.style.setProperty("--x", x + "%");
        this.style.setProperty("--y", y + "%");
      });

      // Enhanced hover effects
      card.addEventListener("mouseenter", function () {
        this.style.transform = "translateY(-8px) scale(1.02)";
        this.style.boxShadow = "0 20px 40px rgba(0,0,0,0.1)";
      });

      card.addEventListener("mouseleave", function () {
        this.style.transform = "translateY(0) scale(1)";
        this.style.boxShadow = "";
      });
    });
  }

  // Add Section Dividers
  function initSectionDividers() {
    const sections = document.querySelectorAll(
      ".features-modern, .stats-modern, .cta-modern"
    );

    sections.forEach((section, index) => {
      if (index > 0) {
        // Skip first section
        const divider = document.createElement("div");
        divider.className = "section-divider";
        section.parentNode.insertBefore(divider, section);

        // Animate divider on scroll
        const observer = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (entry.isIntersecting) {
                entry.target.style.opacity = "1";
                entry.target.style.transform = "scaleX(1)";
              }
            });
          },
          { threshold: 0.5 }
        );

        divider.style.opacity = "0";
        divider.style.transform = "scaleX(0)";
        divider.style.transition = "opacity 0.8s ease, transform 0.8s ease";
        observer.observe(divider);
      }
    });
  }

  // Dynamic Background Effects
  function initDynamicBackground() {
    const hero = document.querySelector(".hero-modern");
    if (!hero) return;

    // Mouse parallax effect
    document.addEventListener("mousemove", function (e) {
      const mouseX = (e.clientX / window.innerWidth) * 100;
      const mouseY = (e.clientY / window.innerHeight) * 100;

      // Update CSS custom properties for dynamic effects
      hero.style.setProperty("--mouse-x", mouseX + "%");
      hero.style.setProperty("--mouse-y", mouseY + "%");

      // Apply subtle parallax to floating elements
      const floatingElements = hero.querySelectorAll(".floating-element");
      floatingElements.forEach((element, index) => {
        const multiplier = (index + 1) * 0.02;
        const moveX = (mouseX - 50) * multiplier;
        const moveY = (mouseY - 50) * multiplier;

        element.style.transform = `translate(${moveX}px, ${moveY}px)`;
      });
    });

    // Dynamic color shifting based on scroll
    let scrollTimeout;
    window.addEventListener("scroll", function () {
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        const scrollPercent =
          window.scrollY /
          (document.documentElement.scrollHeight - window.innerHeight);
        const hue = 210 + scrollPercent * 60; // Shift from blue to purple

        document.documentElement.style.setProperty("--dynamic-hue", hue);
      }, 16);
    });
  }

  // Advanced Animations
  function initAdvancedAnimations() {
    // Staggered reveal animation for feature cards
    const featureCards = document.querySelectorAll(".feature-card-modern");

    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, index) => {
          if (entry.isIntersecting) {
            setTimeout(() => {
              entry.target.style.opacity = "1";
              entry.target.style.transform = "translateY(0)";
            }, index * 150);
          }
        });
      },
      { threshold: 0.1 }
    );

    featureCards.forEach((card, index) => {
      card.style.opacity = "0";
      card.style.transform = "translateY(30px)";
      card.style.transition = `opacity 0.6s ease ${
        index * 0.1
      }s, transform 0.6s ease ${index * 0.1}s`;
      revealObserver.observe(card);
    });

    // Text typing effect for hero subtitle
    const heroSubtitle = document.querySelector(".hero-subtitle");
    if (heroSubtitle) {
      const text = heroSubtitle.textContent;
      heroSubtitle.textContent = "";
      heroSubtitle.classList.add("typing-animation");

      let i = 0;
      const typeInterval = setInterval(() => {
        heroSubtitle.textContent += text.charAt(i);
        i++;
        if (i > text.length) {
          clearInterval(typeInterval);
          heroSubtitle.classList.remove("typing-animation");
        }
      }, 50);
    }
  }

  // Unique Interaction Effects
  function initUniqueInteractions() {
    // Button ripple effect enhancement
    const buttons = document.querySelectorAll(
      ".btn-hero-primary, .btn-hero-secondary"
    );

    buttons.forEach((button) => {
      button.addEventListener("click", function (e) {
        // Create custom ripple
        const ripple = document.createElement("span");
        const rect = this.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height) * 1.5;
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        ripple.style.cssText = `
          position: absolute;
          width: ${size}px;
          height: ${size}px;
          left: ${x}px;
          top: ${y}px;
          background: radial-gradient(circle, rgba(255,255,255,0.6) 0%, transparent 70%);
          border-radius: 50%;
          transform: scale(0);
          animation: customRipple 0.8s ease-out;
          pointer-events: none;
          z-index: 1;
        `;

        this.appendChild(ripple);

        setTimeout(() => {
          if (ripple.parentNode) {
            ripple.parentNode.removeChild(ripple);
          }
        }, 800);
      });
    });

    // Dashboard preview interactive enhancement
    const dashboardPreview = document.querySelector(".dashboard-preview");
    if (dashboardPreview) {
      dashboardPreview.addEventListener("mousemove", function (e) {
        const rect = this.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;

        const rotateY = (x - 0.5) * 20;
        const rotateX = (0.5 - y) * 10;

        this.style.transform = `
          perspective(1000px) 
          rotateY(${rotateY}deg) 
          rotateX(${rotateX}deg) 
          translateY(-10px) 
          scale(1.02)
        `;
      });

      dashboardPreview.addEventListener("mouseleave", function () {
        this.style.transform =
          "perspective(1000px) rotateY(0deg) rotateX(0deg) translateY(0) scale(1)";
      });
    }

    // Stats counter animation enhancement
    const statNumbers = document.querySelectorAll(".stat-number");

    const statsObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const target = parseFloat(entry.target.getAttribute("data-target"));
            animateValue(entry.target, 0, target, 2000);
            statsObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );

    statNumbers.forEach((stat) => {
      statsObserver.observe(stat);
    });

    function animateValue(element, start, end, duration) {
      const range = end - start;
      const minTimer = 50;
      const stepTime = Math.max(
        Math.abs(Math.floor(duration / range)),
        minTimer
      );
      const startTime = new Date().getTime();
      const endTime = startTime + duration;

      function run() {
        const now = new Date().getTime();
        const remaining = Math.max((endTime - now) / duration, 0);
        const value = Math.round(end - remaining * range);

        if (end === 99.9) {
          element.textContent = (value / 10).toFixed(1);
        } else {
          element.textContent = value.toLocaleString();
        }

        if (value === end) {
          // Add completion effect
          element.style.transform = "scale(1.1)";
          setTimeout(() => {
            element.style.transform = "scale(1)";
          }, 200);
        } else {
          setTimeout(run, stepTime);
        }
      }

      run();
    }
  }

  // Performance Optimizations
  function initPerformanceOptimizations() {
    // Throttle scroll events
    let scrollTimeout;

    // Intersection Observer for lazy animations
    const lazyAnimationObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("animate-in");
            lazyAnimationObserver.unobserve(entry.target);
          }
        });
      },
      {
        threshold: 0.1,
        rootMargin: "50px",
      }
    );

    // Observe elements for lazy animation
    document.querySelectorAll(".card, .metric-card").forEach((el) => {
      lazyAnimationObserver.observe(el);
    });

    // Debounced resize handler
    let resizeTimeout;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        // Recalculate any size-dependent calculations
        const particles = document.querySelectorAll(".particle");
        if (particles.length > 20) {
          // Remove excess particles for performance
          for (let i = 20; i < particles.length; i++) {
            particles[i].remove();
          }
        }
      }, 250);
    });

    // Pause animations when tab is not visible
    document.addEventListener("visibilitychange", function () {
      const particles = document.querySelectorAll(
        ".particle, .floating-element"
      );
      particles.forEach((particle) => {
        if (document.hidden) {
          particle.style.animationPlayState = "paused";
        } else {
          particle.style.animationPlayState = "running";
        }
      });
    });

    // Memory cleanup
    window.addEventListener("beforeunload", function () {
      // Clear any intervals or timeouts
      const particles = document.querySelectorAll(".particle");
      particles.forEach((particle) => particle.remove());
    });
  }

  // Performance optimization
  let ticking = false;
  function requestTick() {
    if (!ticking) {
      requestAnimationFrame(updateAnimations);
      ticking = true;
    }
  }

  function updateAnimations() {
    // Update any continuous animations here
    ticking = false;
  }

  // Intersection Observer polyfill for older browsers
  if (!window.IntersectionObserver) {
    const script = document.createElement("script");
    script.src =
      "https://polyfill.io/v3/polyfill.min.js?features=IntersectionObserver";
    document.head.appendChild(script);
  }

  // Add loading complete class
  window.addEventListener("load", () => {
    document.body.classList.add("loaded");
  });

  // Error handling
  window.addEventListener("error", (e) => {
    console.warn("Script error:", e.message);
  });

  // Add additional styles
  const additionalStyles = document.createElement("style");
  additionalStyles.textContent = `
    @keyframes customRipple {
      to {
        transform: scale(1);
        opacity: 0;
      }
    }
    
    .typing-animation::after {
      content: '|';
      animation: blink 1s infinite;
      color: var(--primary);
    }
    
    @keyframes blink {
      0%, 50% { opacity: 1; }
      51%, 100% { opacity: 0; }
    }
    
    .animate-in {
      opacity: 1 !important;
      transform: translateY(0) !important;
    }
    
    /* Enhanced button states */
    .btn-hero-primary, .btn-hero-secondary {
      position: relative;
      overflow: hidden;
    }
    
    /* Dark mode specific enhancements */
    @media (prefers-color-scheme: dark) {
      .particle {
        opacity: 0.15;
      }
      
      .section-divider {
        opacity: 0.7;
      }
    }
    
    /* Reduced motion support */
    @media (prefers-reduced-motion: reduce) {
      .particle,
      .floating-element,
      .typing-animation::after {
        animation: none !important;
      }
    }
    
    /* Accessibility Enhancements */
    @media (prefers-reduced-motion: reduce) {
      .particle,
      .floating-element::before,
      .navbar-modern::before,
      .hero-title::after,
      .footer-modern::before,
      .metric-card::before,
      .cta-container::after {
        animation: none !important;
      }

      .feature-card-modern::after {
        display: none;
      }
    }

    /* Loading states */
    .loading-shimmer {
      background: linear-gradient(
        90deg,
        var(--bg-tertiary) 25%,
        var(--bg-secondary) 50%,
        var(--bg-tertiary) 75%
      );
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
    }

    @keyframes shimmer {
      0% {
        background-position: 200% 0;
      }
      100% {
        background-position: -200% 0;
      }
    }
  `;
  document.head.appendChild(additionalStyles);
})(); // Index Page Specific JavaScript Enhancements

(function () {
  "use strict";

  // Wait for DOM to be ready
  document.addEventListener("DOMContentLoaded", function () {
    initParticleSystem();
    initInteractiveCards();
    initSectionDividers();
    initDynamicBackground();
    initAdvancedAnimations();
    initUniqueInteractions();
    initPerformanceOptimizations();
  });

  // Particle System for Background
  function initParticleSystem() {
    const hero = document.querySelector(".hero-modern");
    if (!hero) return;

    // Create particle container
    const particleContainer = document.createElement("div");
    particleContainer.className = "particle-container";
    hero.appendChild(particleContainer);

    // Create particles
    function createParticle() {
      const particle = document.createElement("div");
      particle.className = "particle";

      // Random size between 3-8px
      const size = Math.random() * 5 + 3;
      particle.style.width = size + "px";
      particle.style.height = size + "px";

      // Random starting position
      particle.style.left = Math.random() * 100 + "%";
      particle.style.top = "100%";

      // Random animation delay
      particle.style.animationDelay = Math.random() * 5 + "s";

      particleContainer.appendChild(particle);

      // Remove particle after animation
      setTimeout(() => {
        if (particle.parentNode) {
          particle.parentNode.removeChild(particle);
        }
      }, 25000);
    }

    // Create particles periodically
    const particleInterval = setInterval(() => {
      if (document.hidden || !document.querySelector(".hero-modern")) {
        clearInterval(particleInterval);
        return;
      }
      createParticle();
    }, 800);

    // Initial burst of particles
    for (let i = 0; i < 10; i++) {
      setTimeout(() => createParticle(), i * 200);
    }
  }

  // Enhanced Interactive Cards
  function initInteractiveCards() {
    const cards = document.querySelectorAll(
      ".feature-card-modern, .metric-card"
    );

    cards.forEach((card) => {
      // Add interactive feedback class
      card.classList.add("interactive-feedback");

      // Mouse tracking for dynamic effects
      card.addEventListener("mousemove", function (e) {
        const rect = this.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width) * 100;
        const y = ((e.clientY - rect.top) / rect.height) * 100;

        this.style.setProperty("--x", x + "%");
        this.style.setProperty("--y", y + "%");
      });

      // Enhanced hover effects
      card.addEventListener("mouseenter", function () {
        this.style.transform = "translateY(-8px) scale(1.02)";
        this.style.boxShadow = "0 20px 40px rgba(0,0,0,0.1)";
      });

      card.addEventListener("mouseleave", function () {
        this.style.transform = "translateY(0) scale(1)";
        this.style.boxShadow = "";
      });
    });
  }

  // Add Section Dividers
  function initSectionDividers() {
    const sections = document.querySelectorAll(
      ".features-modern, .stats-modern, .cta-modern"
    );

    sections.forEach((section, index) => {
      if (index > 0) {
        // Skip first section
        const divider = document.createElement("div");
        divider.className = "section-divider";
        section.parentNode.insertBefore(divider, section);

        // Animate divider on scroll
        const observer = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (entry.isIntersecting) {
                entry.target.style.opacity = "1";
                entry.target.style.transform = "scaleX(1)";
              }
            });
          },
          { threshold: 0.5 }
        );

        divider.style.opacity = "0";
        divider.style.transform = "scaleX(0)";
        divider.style.transition = "opacity 0.8s ease, transform 0.8s ease";
        observer.observe(divider);
      }
    });
  }

  // Dynamic Background Effects
  function initDynamicBackground() {
    const hero = document.querySelector(".hero-modern");
    if (!hero) return;

    // Mouse parallax effect
    document.addEventListener("mousemove", function (e) {
      const mouseX = (e.clientX / window.innerWidth) * 100;
      const mouseY = (e.clientY / window.innerHeight) * 100;

      // Update CSS custom properties for dynamic effects
      hero.style.setProperty("--mouse-x", mouseX + "%");
      hero.style.setProperty("--mouse-y", mouseY + "%");

      // Apply subtle parallax to floating elements
      const floatingElements = hero.querySelectorAll(".floating-element");
      floatingElements.forEach((element, index) => {
        const multiplier = (index + 1) * 0.02;
        const moveX = (mouseX - 50) * multiplier;
        const moveY = (mouseY - 50) * multiplier;

        element.style.transform = `translate(${moveX}px, ${moveY}px)`;
      });
    });

    // Dynamic color shifting based on scroll
    let scrollTimeout;
    window.addEventListener("scroll", function () {
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        const scrollPercent =
          window.scrollY /
          (document.documentElement.scrollHeight - window.innerHeight);
        const hue = 210 + scrollPercent * 60; // Shift from blue to purple

        document.documentElement.style.setProperty("--dynamic-hue", hue);
      }, 16);
    });
  }

  // Advanced Animations
  function initAdvancedAnimations() {
    // Staggered reveal animation for feature cards
    const featureCards = document.querySelectorAll(".feature-card-modern");

    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, index) => {
          if (entry.isIntersecting) {
            setTimeout(() => {
              entry.target.style.opacity = "1";
              entry.target.style.transform = "translateY(0)";
            }, index * 150);
          }
        });
      },
      { threshold: 0.1 }
    );

    featureCards.forEach((card, index) => {
      card.style.opacity = "0";
      card.style.transform = "translateY(30px)";
      card.style.transition = `opacity 0.6s ease ${
        index * 0.1
      }s, transform 0.6s ease ${index * 0.1}s`;
      revealObserver.observe(card);
    });

    // Text typing effect for hero subtitle
    const heroSubtitle = document.querySelector(".hero-subtitle");
    if (heroSubtitle) {
      const text = heroSubtitle.textContent;
      heroSubtitle.textContent = "";
      heroSubtitle.classList.add("typing-animation");

      let i = 0;
      const typeInterval = setInterval(() => {
        heroSubtitle.textContent += text.charAt(i);
        i++;
        if (i > text.length) {
          clearInterval(typeInterval);
          heroSubtitle.classList.remove("typing-animation");
        }
      }, 50);
    }
  }

  // Unique Interaction Effects
  function initUniqueInteractions() {
    // Button ripple effect enhancement
    const buttons = document.querySelectorAll(
      ".btn-hero-primary, .btn-hero-secondary"
    );

    buttons.forEach((button) => {
      button.addEventListener("click", function (e) {
        // Create custom ripple
        const ripple = document.createElement("span");
        const rect = this.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height) * 1.5;
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        ripple.style.cssText = `
                    position: absolute;
                    width: ${size}px;
                    height: ${size}px;
                    left: ${x}px;
                    top: ${y}px;
                    background: radial-gradient(circle, rgba(255,255,255,0.6) 0%, transparent 70%);
                    border-radius: 50%;
                    transform: scale(0);
                    animation: customRipple 0.8s ease-out;
                    pointer-events: none;
                    z-index: 1;
                `;

        this.appendChild(ripple);

        setTimeout(() => {
          if (ripple.parentNode) {
            ripple.parentNode.removeChild(ripple);
          }
        }, 800);
      });
    });

    // Dashboard preview interactive enhancement
    const dashboardPreview = document.querySelector(".dashboard-preview");
    if (dashboardPreview) {
      dashboardPreview.addEventListener("mousemove", function (e) {
        const rect = this.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;

        const rotateY = (x - 0.5) * 20;
        const rotateX = (0.5 - y) * 10;

        this.style.transform = `
                    perspective(1000px) 
                    rotateY(${rotateY}deg) 
                    rotateX(${rotateX}deg) 
                    translateY(-10px) 
                    scale(1.02)
                `;
      });

      dashboardPreview.addEventListener("mouseleave", function () {
        this.style.transform =
          "perspective(1000px) rotateY(0deg) rotateX(0deg) translateY(0) scale(1)";
      });
    }

    // Stats counter animation enhancement
    const statNumbers = document.querySelectorAll(".stat-number");

    const statsObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const target = parseFloat(entry.target.getAttribute("data-target"));
            animateValue(entry.target, 0, target, 2000);
            statsObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );

    statNumbers.forEach((stat) => {
      statsObserver.observe(stat);
    });

    function animateValue(element, start, end, duration) {
      const range = end - start;
      const minTimer = 50;
      const stepTime = Math.max(
        Math.abs(Math.floor(duration / range)),
        minTimer
      );
      const startTime = new Date().getTime();
      const endTime = startTime + duration;

      function run() {
        const now = new Date().getTime();
        const remaining = Math.max((endTime - now) / duration, 0);
        const value = Math.round(end - remaining * range);

        if (end === 99.9) {
          element.textContent = (value / 10).toFixed(1);
        } else {
          element.textContent = value.toLocaleString();
        }

        if (value === end) {
          // Add completion effect
          element.style.transform = "scale(1.1)";
          setTimeout(() => {
            element.style.transform = "scale(1)";
          }, 200);
        } else {
          setTimeout(run, stepTime);
        }
      }

      run();
    }
  }

  // Performance Optimizations
  function initPerformanceOptimizations() {
    // Throttle scroll events
    let scrollTimeout;
    const originalScrollHandlers = [];

    // Intersection Observer for lazy animations
    const lazyAnimationObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("animate-in");
            lazyAnimationObserver.unobserve(entry.target);
          }
        });
      },
      {
        threshold: 0.1,
        rootMargin: "50px",
      }
    );

    // Observe elements for lazy animation
    document.querySelectorAll(".card, .metric-card").forEach((el) => {
      lazyAnimationObserver.observe(el);
    });

    // Debounced resize handler
    let resizeTimeout;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        // Recalculate any size-dependent calculations
        const particles = document.querySelectorAll(".particle");
        if (particles.length > 20) {
          // Remove excess particles for performance
          for (let i = 20; i < particles.length; i++) {
            particles[i].remove();
          }
        }
      }, 250);
    });

    // Pause animations when tab is not visible
    document.addEventListener("visibilitychange", function () {
      const particles = document.querySelectorAll(
        ".particle, .floating-element"
      );
      particles.forEach((particle) => {
        if (document.hidden) {
          particle.style.animationPlayState = "paused";
        } else {
          particle.style.animationPlayState = "running";
        }
      });
    });

    // Memory cleanup
    window.addEventListener("beforeunload", function () {
      // Clear any intervals or timeouts
      const particles = document.querySelectorAll(".particle");
      particles.forEach((particle) => particle.remove());
    });
  }

  // Add custom ripple animation CSS
  const style = document.createElement("style");
  style.textContent = `
        @keyframes customRipple {
            to {
                transform: scale(1);
                opacity: 0;
            }
        }
        
        .typing-animation::after {
            content: '|';
            animation: blink 1s infinite;
            color: var(--primary);
        }
        
        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0; }
        }
        
        .animate-in {
            opacity: 1 !important;
            transform: translateY(0) !important;
        }
        
        /* Enhanced button states */
        .btn-hero-primary, .btn-hero-secondary {
            position: relative;
            overflow: hidden;
        }
        
        /* Dark mode specific enhancements */
        @media (prefers-color-scheme: dark) {
            .particle {
                opacity: 0.15;
            }
            
            .section-divider {
                opacity: 0.7;
            }
        }
        
        /* Reduced motion support */
        @media (prefers-reduced-motion: reduce) {
            .particle,
            .floating-element,
            .typing-animation::after {
                animation: none !important;
            }
        }
    `;
  document.head.appendChild(style);

  // Enhanced Theme Detection and Dynamic Adjustments
  function initThemeEnhancements() {
    // Detect system theme changes
    const darkModeQuery = window.matchMedia("(prefers-color-scheme: dark)");

    function handleThemeChange(e) {
      const isDark = e.matches;
      document.documentElement.setAttribute(
        "data-theme",
        isDark ? "dark" : "light"
      );

      // Adjust particle opacity for dark mode
      const particles = document.querySelectorAll(".particle");
      particles.forEach((particle) => {
        particle.style.opacity = isDark ? "0.15" : "0.1";
      });

      // Adjust section dividers
      const dividers = document.querySelectorAll(".section-divider");
      dividers.forEach((divider) => {
        divider.style.opacity = isDark ? "0.7" : "1";
      });
    }

    darkModeQuery.addListener(handleThemeChange);
    handleThemeChange(darkModeQuery); // Initial call
  }

  // Advanced Scroll Effects
  function initAdvancedScrollEffects() {
    let scrolled = 0;

    const scrollHandler = () => {
      scrolled = window.pageYOffset;

      // Parallax background
      const hero = document.querySelector(".hero-modern");
      if (hero) {
        const offset = scrolled * 0.5;
        hero.style.transform = `translateY(${offset}px)`;
      }

      // Navbar enhancement
      const navbar = document.querySelector(".navbar-modern");
      if (navbar) {
        if (scrolled > 100) {
          navbar.classList.add("scrolled");
          navbar.style.background = `rgba(${
            scrolled > 200 ? "15, 23, 42" : "255, 255, 255"
          }, 0.95)`;
        } else {
          navbar.classList.remove("scrolled");
          navbar.style.background = "";
        }
      }

      // Progressive blur effect on hero content
      const heroContent = document.querySelector(".hero-content");
      if (heroContent && scrolled > 0) {
        const blurAmount = Math.min(scrolled / 500, 1) * 3;
        heroContent.style.filter = `blur(${blurAmount}px)`;
        heroContent.style.opacity = Math.max(1 - scrolled / 800, 0.3);
      }
    };

    // Use requestAnimationFrame for smooth scrolling
    let ticking = false;
    window.addEventListener("scroll", () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          scrollHandler();
          ticking = false;
        });
        ticking = true;
      }
    });
  }

  // Interactive Cursor Effects
  function initCursorEffects() {
    // Create custom cursor
    const cursor = document.createElement("div");
    cursor.className = "custom-cursor";
    cursor.style.cssText = `
            position: fixed;
            width: 20px;
            height: 20px;
            background: radial-gradient(circle, var(--azure-light) 0%, transparent 70%);
            border-radius: 50%;
            pointer-events: none;
            z-index: 9999;
            mix-blend-mode: difference;
            transition: transform 0.1s ease;
            opacity: 0;
        `;
    document.body.appendChild(cursor);

    // Update cursor position
    document.addEventListener("mousemove", (e) => {
      cursor.style.left = e.clientX - 10 + "px";
      cursor.style.top = e.clientY - 10 + "px";
      cursor.style.opacity = "1";
    });

    // Hide cursor when leaving window
    document.addEventListener("mouseleave", () => {
      cursor.style.opacity = "0";
    });

    // Enhanced hover effects for interactive elements
    const interactiveElements = document.querySelectorAll(
      "button, a, .card, .feature-card-modern"
    );

    interactiveElements.forEach((element) => {
      element.addEventListener("mouseenter", () => {
        cursor.style.transform = "scale(2)";
        cursor.style.background =
          "radial-gradient(circle, var(--teal-light) 0%, transparent 70%)";
      });

      element.addEventListener("mouseleave", () => {
        cursor.style.transform = "scale(1)";
        cursor.style.background =
          "radial-gradient(circle, var(--azure-light) 0%, transparent 70%)";
      });
    });
  }

  // Audio Feedback System (Optional)
  function initAudioFeedback() {
    // Create audio context for subtle UI sounds
    let audioContext;

    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
      console.log("Audio not supported");
      return;
    }

    function playTone(frequency, duration, type = "sine") {
      if (!audioContext) return;

      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);

      oscillator.frequency.setValueAtTime(frequency, audioContext.currentTime);
      oscillator.type = type;

      gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(
        0.01,
        audioContext.currentTime + duration
      );

      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + duration);
    }

    // Add subtle sound feedback to buttons
    const buttons = document.querySelectorAll(
      ".btn-hero-primary, .btn-hero-secondary"
    );
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        playTone(800, 0.1);
      });
    });

    // Hover sounds for cards
    const cards = document.querySelectorAll(".feature-card-modern");
    cards.forEach((card) => {
      card.addEventListener("mouseenter", () => {
        playTone(600, 0.05);
      });
    });
  }

  // Initialize all enhancements
  initThemeEnhancements();
  initAdvancedScrollEffects();
  initCursorEffects();

  // Optional: Uncomment to enable audio feedback
  // initAudioFeedback();

  // Easter Egg: Konami Code
  function initEasterEgg() {
    const konamiCode = [
      "ArrowUp",
      "ArrowUp",
      "ArrowDown",
      "ArrowDown",
      "ArrowLeft",
      "ArrowRight",
      "ArrowLeft",
      "ArrowRight",
      "KeyB",
      "KeyA",
    ];
    let konamiIndex = 0;

    document.addEventListener("keydown", (e) => {
      if (e.code === konamiCode[konamiIndex]) {
        konamiIndex++;
        if (konamiIndex === konamiCode.length) {
          // Easter egg activated!
          document.body.style.animation = "rainbow 2s infinite";

          // Create celebration particles
          for (let i = 0; i < 50; i++) {
            setTimeout(() => {
              createCelebrationParticle();
            }, i * 50);
          }

          konamiIndex = 0;

          setTimeout(() => {
            document.body.style.animation = "";
          }, 10000);
        }
      } else {
        konamiIndex = 0;
      }
    });

    function createCelebrationParticle() {
      const particle = document.createElement("div");
      particle.style.cssText = `
                position: fixed;
                width: 10px;
                height: 10px;
                background: hsl(${Math.random() * 360}, 100%, 50%);
                border-radius: 50%;
                pointer-events: none;
                z-index: 10000;
                left: ${Math.random() * 100}vw;
                top: -10px;
                animation: celebrationFall 3s ease-out forwards;
            `;

      document.body.appendChild(particle);

      setTimeout(() => {
        particle.remove();
      }, 3000);
    }
  }

  initEasterEgg();

  // Add celebration animation CSS
  const celebrationStyle = document.createElement("style");
  celebrationStyle.textContent = `
        @keyframes rainbow {
            0% { filter: hue-rotate(0deg); }
            100% { filter: hue-rotate(360deg); }
        }
        
        @keyframes celebrationFall {
            to {
                transform: translateY(100vh) rotate(720deg);
                opacity: 0;
            }
        }
    `;
  document.head.appendChild(celebrationStyle);
})();
