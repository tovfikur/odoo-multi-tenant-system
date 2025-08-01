/**
 * SaaS Navbar Styler
 * Simple navbar color enforcement
 */

(function() {
    'use strict';

    // Your Brand Colors
    var PRIMARY_COLOR = '#1a73e8';
    var PRIMARY_DARK = '#174ea6';
    var COMPLEMENTARY_COLOR = '#ff6f61';

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
            
            // Style menu sections container
            var menuSectionsContainer = document.querySelector('.o_main_navbar .o_menu_sections');
            if (menuSectionsContainer) {
                menuSectionsContainer.style.setProperty('gap', '8px', 'important');
                menuSectionsContainer.style.setProperty('display', 'flex', 'important');
            }
            
            // Style specific menu sections
            var menuSections = document.querySelectorAll('.o_main_navbar .o_menu_sections .o_nav_entry, .o_main_navbar .o_menu_sections .dropdown-toggle');
            menuSections.forEach(function(item) {
                item.style.setProperty('background-color', PRIMARY_COLOR, 'important');
                item.style.setProperty('color', 'white', 'important');
                item.style.setProperty('border-radius', '6px', 'important');
                item.style.setProperty('margin', '0', 'important');
                item.style.setProperty('border', 'none', 'important');
                item.style.setProperty('font-weight', 'normal', 'important');
            });
            
            // Style dropdown items
            var dropdownItems = document.querySelectorAll('.dropdown-item');
            dropdownItems.forEach(function(item) {
                item.style.setProperty('color', PRIMARY_COLOR, 'important');
                item.style.setProperty('border-radius', '4px', 'important');
                item.style.setProperty('margin', '2px 4px', 'important');
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
