/** @odoo-module **/

import { registry } from "@web/core/registry";
import { MenuItem } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Patch the MenuItem component to hide settings menu
patch(MenuItem.prototype, "hide_setting.MenuItem", {
    setup() {
        this._super();
        this.orm = useService("orm");
        this.hideSettings = false;
        this.checkHideSettings();
    },

    async checkHideSettings() {
        try {
            const result = await this.orm.call(
                'hide.setting.config',
                'is_settings_hidden',
                []
            );
            this.hideSettings = result;
        } catch (error) {
            console.warn('Could not check hide settings status:', error);
            this.hideSettings = false;
        }
    },

    get isVisible() {
        const originalVisible = this._super();
        
        // If this is a settings-related menu item and hide settings is active
        if (this.hideSettings && this.isSettingsMenu()) {
            return false;
        }
        
        return originalVisible;
    },

    isSettingsMenu() {
        // Check if this menu item is related to settings
        const item = this.props.item;
        if (!item) return false;
        
        // Check various ways settings might be identified
        const settingsIndicators = [
            'settings',
            'configuration',
            'config',
            'base.menu_administration',
            '/web/settings'
        ];
        
        const itemName = (item.name || '').toLowerCase();
        const itemXmlId = item.xmlid || '';
        const itemAction = item.action || '';
        
        return settingsIndicators.some(indicator => 
            itemName.includes(indicator) || 
            itemXmlId.includes(indicator) || 
            itemAction.includes(indicator)
        );
    }
});

// Alternative approach: CSS-based hiding
const hideSettingsService = {
    dependencies: ["orm"],
    
    start(env, { orm }) {
        this.checkAndHideSettings(orm);
        
        // Recheck periodically
        setInterval(() => {
            this.checkAndHideSettings(orm);
        }, 30000); // Check every 30 seconds
    },

    async checkAndHideSettings(orm) {
        try {
            const isHidden = await orm.call(
                'hide.setting.config',
                'is_settings_hidden',
                []
            );
            
            if (isHidden) {
                this.hideSettingsWithCSS();
            } else {
                this.showSettingsWithCSS();
            }
        } catch (error) {
            console.warn('Could not check hide settings status:', error);
        }
    },

    hideSettingsWithCSS() {
        // Add CSS to hide settings menu items
        let style = document.getElementById('hide-settings-style');
        if (!style) {
            style = document.createElement('style');
            style.id = 'hide-settings-style';
            document.head.appendChild(style);
        }
        
        style.textContent = `
            /* Hide settings menu items */
            .o_navbar_apps_menu a[data-menu-xmlid*="settings"],
            .o_navbar_apps_menu a[data-menu-xmlid*="configuration"],
            .o_navbar_apps_menu a[data-menu-xmlid*="admin"],
            .o_navbar_apps_menu a[href*="/web/settings"],
            .dropdown-item[data-menu*="settings"],
            .dropdown-item[data-menu*="configuration"],
            a[data-menu-xmlid="base.menu_administration"] {
                display: none !important;
            }
            
            /* Hide settings app icon */
            .o_app[data-menu-xmlid*="settings"],
            .o_app[data-menu-xmlid*="base.menu_administration"] {
                display: none !important;
            }
        `;
    },

    showSettingsWithCSS() {
        const style = document.getElementById('hide-settings-style');
        if (style) {
            style.remove();
        }
    }
};

registry.category("services").add("hide_settings", hideSettingsService);