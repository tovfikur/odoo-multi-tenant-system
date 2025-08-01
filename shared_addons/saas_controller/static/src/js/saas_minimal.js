/**
 * SaaS Controller - Minimal Icon Replacement
 * Only handles icon replacement without breaking design
 */

odoo.define('saas_controller.minimal', function (require) {
    'use strict';

    var core = require('web.core');
    var session = require('web.session');

    var SaaSMinimal = {
        
        init: function() {
            this.replaceAppsIcon();
            this.checkDebrandingConfig();
        },

        /**
         * Replace oi-apps icon with Font Awesome brain icon
         */
        replaceAppsIcon: function() {
            // Wait for DOM to be ready
            $(document).ready(function() {
                // Create style tag for icon replacement
                var style = document.createElement('style');
                style.innerHTML = `
                    .oi.oi-apps:before {
                        content: "\\f5dc" !important;
                        font-family: "Font Awesome 6 Free" !important;
                        font-weight: 900 !important;
                    }
                `;
                document.head.appendChild(style);
            });
        },

        /**
         * Check and apply debranding configuration
         */
        checkDebrandingConfig: function() {
            var self = this;
            
            // Only apply if user has access
            if (session.is_admin || session.is_system) {
                this._rpc({
                    model: 'saas.controller',
                    method: 'get_or_create_config',
                    args: []
                }).then(function(config) {
                    if (config && config.remove_odoo_branding) {
                        self.applyDebranding();
                    }
                }).catch(function(error) {
                    console.log('SaaS Controller: Config not available');
                });
            }
        },

        /**
         * Apply minimal debranding
         */
        applyDebranding: function() {
            $(document).ready(function() {
                $('body').addClass('saas-debrand');
            });
        }
    };

    // Initialize when core is ready
    core.bus.on('web_client_ready', null, function() {
        SaaSMinimal.init();
    });

    return SaaSMinimal;
});
