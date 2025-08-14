// ===== BRAND-ALIGNED UNIFIED NAVBAR JAVASCRIPT =====
// Khudroo Jewel + Neutral Brand Implementation

document.addEventListener('DOMContentLoaded', function() {
    const navbar = document.querySelector('.navbar-unified');
    const navLinks = document.querySelectorAll('.nav-link-unified');
    
    // Dark mode detection and handling
    const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    function handleColorSchemeChange(e) {
        // Add or remove dark mode class for additional styling if needed
        if (e.matches) {
            document.body.classList.add('dark-mode');
            console.log('🌙 Dark mode activated - Khudroo Navbar');
        } else {
            document.body.classList.remove('dark-mode');
            console.log('☀️ Light mode activated - Khudroo Navbar');
        }
        
        // Update any dynamic colors or elements
        updateBrandColorsForMode(e.matches);
    }
    
    // Initial color scheme check
    handleColorSchemeChange(darkModeQuery);
    
    // Listen for color scheme changes
    darkModeQuery.addListener(handleColorSchemeChange);
    
    function updateBrandColorsForMode(isDark) {
        // Dynamic brand color adjustments if needed
        const logo = document.querySelector('.logo-unified');
        if (logo && isDark) {
            // Enhance logo visibility in dark mode
            logo.style.filter = 'brightness(1.1) contrast(1.05)';
        } else if (logo) {
            logo.style.filter = 'none';
        }
    }
    
    // Enhanced navbar scroll effect with brand philosophy
    function handleNavbarScroll() {
        const scrolled = window.scrollY > 20;
        
        if (scrolled) {
            navbar.classList.add('scrolled');
            // Add subtle brand pulse effect when scrolled
            navbar.style.setProperty('--navbar-pulse', '1');
        } else {
            navbar.classList.remove('scrolled');
            navbar.style.setProperty('--navbar-pulse', '0');
        }
    }
    
    // Initial check
    handleNavbarScroll();
    
    // Throttled scroll listener for performance
    let scrollTimeout;
    window.addEventListener('scroll', function() {
        if (!scrollTimeout) {
            scrollTimeout = setTimeout(function() {
                handleNavbarScroll();
                scrollTimeout = null;
            }, 10);
        }
    });
    
    // Active page highlighting
    function setActiveNavLink() {
        const currentPath = window.location.pathname;
        
        navLinks.forEach(link => {
            link.classList.remove('current-page');
            
            const linkPath = new URL(link.href).pathname;
            
            // Exact match or homepage
            if (linkPath === currentPath || 
                (currentPath === '/' && linkPath.includes('#features')) ||
                (currentPath.startsWith('/about') && linkPath.includes('/about')) ||
                (currentPath.startsWith('/pricing') && linkPath.includes('/pricing')) ||
                (currentPath.startsWith('/contact') && linkPath.includes('/contact')) ||
                (currentPath.startsWith('/dashboard') && linkPath.includes('/dashboard')) ||
                (currentPath.startsWith('/tenant') && linkPath.includes('/create_tenant')) ||
                (currentPath.startsWith('/billing') && linkPath.includes('/billing')) ||
                (currentPath.startsWith('/support') && linkPath.includes('/support'))) {
                link.classList.add('current-page');
            }
        });
    }
    
    // Set active link on page load
    setActiveNavLink();
    
    // Smooth scrolling for anchor links
    navLinks.forEach(link => {
        if (link.href.includes('#')) {
            link.addEventListener('click', function(e) {
                const url = new URL(this.href);
                
                // Only handle same-page anchors
                if (url.pathname === window.location.pathname) {
                    e.preventDefault();
                    
                    const targetId = url.hash.slice(1);
                    const targetElement = document.getElementById(targetId);
                    
                    if (targetElement) {
                        const navbarHeight = navbar.offsetHeight;
                        const targetPosition = targetElement.offsetTop - navbarHeight - 20;
                        
                        window.scrollTo({
                            top: targetPosition,
                            behavior: 'smooth'
                        });
                    }
                }
            });
        }
    });
    
    // Mobile menu auto-close
    const navbarToggler = document.querySelector('.navbar-toggler');
    const navbarCollapse = document.querySelector('.navbar-collapse');
    
    if (navbarToggler && navbarCollapse) {
        // Close mobile menu when clicking on links
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (navbarCollapse.classList.contains('show')) {
                    navbarToggler.click();
                }
            });
        });
        
        // Close mobile menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!navbar.contains(e.target) && navbarCollapse.classList.contains('show')) {
                navbarToggler.click();
            }
        });
    }
    
    // User dropdown functionality (for custom dropdown)
    const userDropdown = document.querySelector('.navbar-user-dropdown');
    if (userDropdown) {
        const userAvatar = userDropdown.querySelector('.user-avatar');
        const dropdownMenu = userDropdown.querySelector('.user-dropdown-menu');
        
        if (userAvatar && dropdownMenu) {
            let dropdownTimeout;
            
            userDropdown.addEventListener('mouseenter', () => {
                clearTimeout(dropdownTimeout);
                dropdownMenu.style.opacity = '1';
                dropdownMenu.style.visibility = 'visible';
                dropdownMenu.style.transform = 'translateY(0)';
            });
            
            userDropdown.addEventListener('mouseleave', () => {
                dropdownTimeout = setTimeout(() => {
                    dropdownMenu.style.opacity = '0';
                    dropdownMenu.style.visibility = 'hidden';
                    dropdownMenu.style.transform = 'translateY(-10px)';
                }, 150);
            });
        }
    }
    
    // Simplified theme handling (system preference only)
    function handleSystemTheme(isDark) {
        if (isDark) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        updateBrandColorsForMode(isDark);
    }
    
    // Initialize with system preference
    handleSystemTheme(darkModeQuery.matches);
    
    // Add loading states to action buttons
    const actionButtons = document.querySelectorAll('.btn-navbar-primary, .btn-navbar-secondary');
    actionButtons.forEach(button => {
        button.addEventListener('click', function() {
            if (!this.classList.contains('loading')) {
                const originalContent = this.innerHTML;
                this.classList.add('loading');
                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
                
                // Remove loading state after navigation (fallback)
                setTimeout(() => {
                    this.classList.remove('loading');
                    this.innerHTML = originalContent;
                }, 3000);
            }
        });
    });
    
    // Notification badge animation (if present)
    const notificationBadges = document.querySelectorAll('.notification-badge');
    notificationBadges.forEach(badge => {
        // Add pulse animation for new notifications
        if (parseInt(badge.textContent) > 0) {
            badge.style.animation = 'pulse 2s infinite';
        }
    });
    
    // Keyboard navigation support
    navbar.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            // Close any open dropdowns
            const openDropdowns = navbar.querySelectorAll('.show');
            openDropdowns.forEach(dropdown => {
                dropdown.classList.remove('show');
            });
            
            // Close mobile menu
            if (navbarCollapse && navbarCollapse.classList.contains('show')) {
                navbarToggler.click();
            }
        }
    });
    
    // Add focus indicators for accessibility
    navLinks.forEach(link => {
        link.addEventListener('focus', function() {
            this.style.outline = '2px solid #1a73e8';
            this.style.outlineOffset = '2px';
        });
        
        link.addEventListener('blur', function() {
            this.style.outline = 'none';
        });
    });
});

// CSS animations for JavaScript-triggered effects
const style = document.createElement('style');
style.textContent = `
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
    }
    
    .btn-navbar-primary.loading,
    .btn-navbar-secondary.loading {
        opacity: 0.7;
        cursor: not-allowed;
        pointer-events: none;
    }
    
    .nav-link-unified:focus {
        outline: 2px solid #1a73e8 !important;
        outline-offset: 2px !important;
    }
`;
document.head.appendChild(style);