/**
 * SaaS Navbar Styler
 * Simple navbar color enforcement
 */

(function() {
    'use strict';

    // Your Primary Brand Color
    var PRIMARY_COLOR = '#1a73e8';
    var PRIMARY_DARK = '#174ea6';

    var NavbarStyler = {
        
        /**
         * Initialize the navbar styler
         */
        init: function() {
            console.log('🎨 SaaS Navbar Styler: Initializing...');
            
            this.styleNavbar();
            this.setupMutationObserver();
            
            console.log('✅ SaaS Navbar Styler: Ready!');
        },
        
        /**
         * Apply navbar styling
         */
        styleNavbar: function() {
            var navbar = document.querySelector('.o_main_navbar');
            if (navbar) {
                navbar.style.setProperty('background', 'linear-gradient(135deg, ' + PRIMARY_COLOR + ' 0%, ' + PRIMARY_DARK + ' 100%)', 'important');
                navbar.style.setProperty('box-shadow', '0 2px 8px rgba(26, 115, 232, 0.15)', 'important');
            }
            
            // Style navbar items
            var navItems = document.querySelectorAll('.o_main_navbar .dropdown-toggle, .o_main_navbar .nav-link, .o_main_navbar .navbar-brand');
            navItems.forEach(function(item) {
                item.style.setProperty('color', 'white', 'important');
            });
        },
        
        /**
         * Set up mutation observer for dynamic navbar changes
         */
        setupMutationObserver: function() {
            var self = this;
            var observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.type === 'childList') {
                        mutation.addedNodes.forEach(function(node) {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                if (node.classList && node.classList.contains('o_main_navbar')) {
                                    setTimeout(function() {
                                        self.styleNavbar();
                                    }, 100);
                                }
                            }
                        });
                    }
                });
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    };

    // Initialize when DOM is ready
    function initializeNavbarStyler() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                setTimeout(function() {
                    NavbarStyler.init();
                }, 500);
            });
        } else {
            setTimeout(function() {
                NavbarStyler.init();
            }, 500);
        }
    }

    // Initialize immediately
    initializeNavbarStyler();

    // Global access
    window.SaaSNavbarStyler = NavbarStyler;

})();
