/**
 * SaaS Brand Color Enforcer
 * Aggressively enforces brand colors throughout Odoo interface
 * Overrides inline styles and stubborn CSS
 */

odoo.define('saas_controller.brand_enforcer', function (require) {
    'use strict';

    var core = require('web.core');
    var session = require('web.session');

    // Your Beautiful Brand Colors
    var BRAND_COLORS = {
        // Primary Azure Colors
        primary: '#1a73e8',
        primaryDark: '#174ea6',
        primaryLight: '#4c9eff',
        
        // Secondary Teal Colors
        secondary: '#00bfa5',
        secondaryDark: '#00937a',
        secondaryLight: '#33e1c6',
        
        // Accent Coral Colors
        accent: '#ff6f61',
        accentDark: '#e05a4e',
        accentLight: '#ff8a7a',
        
        // Support Violet Colors
        support: '#9b51e0',
        supportDark: '#7a3eb0',
        supportLight: '#b76deb',
        
        // Text & Neutrals
        text: '#2e3a59',
        textSecondary: '#5c6b8a',
        textMuted: '#8a95aa',
        background: '#ffffff'
    };

    // Color mapping for different element types
    var COLOR_MAPPINGS = {
        // Navigation elements
        '.o_main_navbar, .navbar, .o_navbar': {
            background: `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
            color: 'white'
        },
        
        // Primary buttons
        '.btn-primary, .o_form_button_save, .o_form_button_create': {
            background: `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
            borderColor: BRAND_COLORS.primary,
            color: 'white'
        },
        
        // Secondary buttons
        '.btn-secondary': {
            background: `linear-gradient(135deg, ${BRAND_COLORS.secondary} 0%, ${BRAND_COLORS.secondaryDark} 100%)`,
            borderColor: BRAND_COLORS.secondary,
            color: 'white'
        },
        
        // Links
        'a, .o_form_uri, .o_field_url': {
            color: BRAND_COLORS.primary
        },
        
        // Table headers
        '.table thead th, .o_list_table thead th': {
            background: `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
            color: 'white'
        },
        
        // Card headers
        '.card-header, .panel-heading': {
            background: `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
            color: 'white'
        },
        
        // Progress bars
        '.progress-bar': {
            background: `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryLight} 100%)`
        },
        
        // Form controls
        '.form-control:focus, .o_input:focus': {
            borderColor: BRAND_COLORS.primary,
            boxShadow: `0 0 0 3px rgba(26, 115, 232, 0.1)`
        }
    };

    // Inline style color overrides that we need to force
    var INLINE_OVERRIDES = [
        'background-color',
        'background',
        'color',
        'border-color'
    ];

    var BrandEnforcer = {
        
        /**
         * Initialize the brand enforcer
         */
        init: function() {
            console.log('🎨 SaaS Brand Enforcer: Initializing...');
            
            // Apply initial styling
            this.applyCSSVariables();
            this.applyColorMappings();
            this.enforceInlineStyles();
            this.removeOdooBranding();
            
            // Set up observers for dynamic content
            this.setupMutationObserver();
            this.setupEventListeners();
            
            // Periodic enforcement for stubborn elements
            setInterval(this.enforceColors.bind(this), 2000);
            
            console.log('✅ SaaS Brand Enforcer: Ready!');
        },
        
        /**
         * Apply CSS variables globally
         */
        applyCSSVariables: function() {
            var root = document.documentElement;
            
            // Set CSS variables
            root.style.setProperty('--saas-primary-color', BRAND_COLORS.primary);
            root.style.setProperty('--saas-primary-dark', BRAND_COLORS.primaryDark);
            root.style.setProperty('--saas-primary-light', BRAND_COLORS.primaryLight);
            root.style.setProperty('--saas-secondary-color', BRAND_COLORS.secondary);
            root.style.setProperty('--saas-secondary-dark', BRAND_COLORS.secondaryDark);
            root.style.setProperty('--saas-accent-color', BRAND_COLORS.accent);
            root.style.setProperty('--saas-accent-dark', BRAND_COLORS.accentDark);
            root.style.setProperty('--saas-support-color', BRAND_COLORS.support);
            root.style.setProperty('--saas-text-color', BRAND_COLORS.text);
            root.style.setProperty('--saas-link-color', BRAND_COLORS.primary);
            
            // Override common CSS variables
            root.style.setProperty('--primary', BRAND_COLORS.primary);
            root.style.setProperty('--secondary', BRAND_COLORS.secondary);
            root.style.setProperty('--success', BRAND_COLORS.secondary);
            root.style.setProperty('--info', BRAND_COLORS.support);
            root.style.setProperty('--warning', BRAND_COLORS.accent);
            root.style.setProperty('--danger', BRAND_COLORS.accentDark);
        },
        
        /**
         * Apply color mappings to elements
         */
        applyColorMappings: function() {
            Object.keys(COLOR_MAPPINGS).forEach(selector => {
                var elements = document.querySelectorAll(selector);
                var styles = COLOR_MAPPINGS[selector];
                
                elements.forEach(element => {
                    Object.keys(styles).forEach(property => {
                        var value = styles[property];
                        element.style.setProperty(this.camelToKebab(property), value, 'important');
                    });
                });
            });
        },
        
        /**
         * Aggressively enforce colors on all elements
         */
        enforceColors: function() {
            // Force primary buttons
            this.forceElementColors('.btn-primary, .o_form_button_save, .o_form_button_create', {
                'background': `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
                'background-color': BRAND_COLORS.primary,
                'border-color': BRAND_COLORS.primary,
                'color': 'white'
            });
            
            // Force secondary buttons
            this.forceElementColors('.btn-secondary', {
                'background': `linear-gradient(135deg, ${BRAND_COLORS.secondary} 0%, ${BRAND_COLORS.secondaryDark} 100%)`,
                'background-color': BRAND_COLORS.secondary,
                'border-color': BRAND_COLORS.secondary,
                'color': 'white'
            });
            
            // Force navigation
            this.forceElementColors('.o_main_navbar, .navbar, .o_navbar', {
                'background': `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
                'background-color': BRAND_COLORS.primary,
                'color': 'white'
            });
            
            // Force links
            this.forceElementColors('a, .o_form_uri, .o_field_url', {
                'color': BRAND_COLORS.primary
            });
            
            // Force table headers
            this.forceElementColors('.table thead th, .o_list_table thead th', {
                'background': `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
                'background-color': BRAND_COLORS.primary,
                'color': 'white'
            });
            
            // Force progress bars
            this.forceElementColors('.progress-bar', {
                'background': `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryLight} 100%)`,
                'background-color': BRAND_COLORS.primary
            });
            
            // Force badges
            this.forceElementColors('.badge-primary, .label-primary', {
                'background-color': BRAND_COLORS.primary,
                'color': 'white'
            });
            
            this.forceElementColors('.badge-secondary, .label-secondary', {
                'background-color': BRAND_COLORS.secondary,
                'color': 'white'
            });
        },
        
        /**
         * Force colors on specific elements
         */
        forceElementColors: function(selector, styles) {
            var elements = document.querySelectorAll(selector);
            elements.forEach(element => {
                Object.keys(styles).forEach(property => {
                    element.style.setProperty(property, styles[property], 'important');
                });
            });
        },
        
        /**
         * Remove inline styles that override our colors
         */
        enforceInlineStyles: function() {
            var elementsWithInlineStyles = document.querySelectorAll('[style]');
            
            elementsWithInlineStyles.forEach(element => {
                var style = element.getAttribute('style');
                if (!style) return;
                
                // Remove problematic inline color styles
                INLINE_OVERRIDES.forEach(property => {
                    var regex = new RegExp(`${property}\\s*:[^;]+;?`, 'gi');
                    style = style.replace(regex, '');
                });
                
                element.setAttribute('style', style);
            });
        },
        
        /**
         * Remove Odoo branding elements
         */
        removeOdooBranding: function() {
            var brandingSelectors = [
                '.o_sub_menu_footer',
                '.powered_by',
                '[data-section="about"] .oe_instance_title',
                '.oe_instance_title',
                '.o_footer'
            ];
            
            brandingSelectors.forEach(selector => {
                var elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    element.style.display = 'none';
                });
            });
        },
        
        /**
         * Set up mutation observer for dynamic content
         */
        setupMutationObserver: function() {
            var observer = new MutationObserver(mutations => {
                mutations.forEach(mutation => {
                    if (mutation.type === 'childList') {
                        mutation.addedNodes.forEach(node => {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                this.processNewElement(node);
                            }
                        });
                    } else if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                        this.processStyleChange(mutation.target);
                    }
                });
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['style']
            });
        },
        
        /**
         * Process newly added elements
         */
        processNewElement: function(element) {
            // Apply brand colors to new elements
            this.applyColorMappings();
            this.enforceInlineStyles();
            this.removeOdooBranding();
        },
        
        /**
         * Process style changes
         */
        processStyleChange: function(element) {
            // Re-enforce colors when inline styles change
            setTimeout(() => {
                this.enforceColors();
            }, 100);
        },
        
        /**
         * Set up event listeners for form interactions
         */
        setupEventListeners: function() {
            // Listen for focus events to apply brand colors
            document.addEventListener('focus', (e) => {
                if (e.target.matches('input, textarea, select, .form-control, .o_input')) {
                    e.target.style.setProperty('border-color', BRAND_COLORS.primary, 'important');
                    e.target.style.setProperty('box-shadow', `0 0 0 3px rgba(26, 115, 232, 0.1)`, 'important');
                }
            }, true);
            
            // Listen for click events on buttons
            document.addEventListener('click', (e) => {
                if (e.target.matches('.btn-primary, .o_form_button_save, .o_form_button_create')) {
                    setTimeout(() => {
                        this.forceElementColors('.btn-primary, .o_form_button_save, .o_form_button_create', {
                            'background': `linear-gradient(135deg, ${BRAND_COLORS.primary} 0%, ${BRAND_COLORS.primaryDark} 100%)`,
                            'background-color': BRAND_COLORS.primary,
                            'color': 'white'
                        });
                    }, 50);
                }
            });
        },
        
        /**
         * Convert camelCase to kebab-case
         */
        camelToKebab: function(str) {
            return str.replace(/([a-z0-9]|(?=[A-Z]))([A-Z])/g, '$1-$2').toLowerCase();
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            BrandEnforcer.init();
        });
    } else {
        BrandEnforcer.init();
    }

    // Also initialize on web client ready
    core.bus.on('web_client_ready', null, function() {
        setTimeout(function() {
            BrandEnforcer.init();
        }, 1000);
    });

    return BrandEnforcer;
});
