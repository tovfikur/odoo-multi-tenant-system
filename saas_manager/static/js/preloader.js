/**
 * Lottie Preloader Integration
 * Provides loading states for API calls with beautiful Lottie animation
 */

class LottiePreloader {
    constructor() {
        this.isLoaded = false;
        this.activeRequests = 0;
        this.preloaderElement = null;
        this.init();
    }

    init() {
        // Create preloader container
        this.createPreloaderElement();
        
        // Load Lottie web component
        this.loadLottieScript();
        
        // Set up API interceptors
        this.setupAPIInterceptors();
    }

    createPreloaderElement() {
        // Create preloader overlay
        const overlay = document.createElement('div');
        overlay.id = 'lottie-preloader-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(5px);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
        `;

        // Create Lottie animation container
        const animationContainer = document.createElement('div');
        animationContainer.innerHTML = `
            <dotlottie-wc 
                src="https://lottie.host/2ca5e67b-55b9-4f90-8bd5-8c536ebfb522/6r2AmJ81Et.lottie" 
                style="width: 300px; height: 300px;" 
                speed="1" 
                autoplay 
                loop>
            </dotlottie-wc>
        `;

        // Create loading text
        const loadingText = document.createElement('div');
        loadingText.id = 'loading-text';
        loadingText.style.cssText = `
            margin-top: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 16px;
            color: #333;
            text-align: center;
        `;
        loadingText.textContent = 'Loading...';

        // Assemble preloader
        overlay.appendChild(animationContainer);
        overlay.appendChild(loadingText);
        document.body.appendChild(overlay);

        this.preloaderElement = overlay;
        this.loadingTextElement = loadingText;
    }

    loadLottieScript() {
        // Load Lottie web component if not already loaded
        if (!document.querySelector('script[src*="dotlottie-wc"]')) {
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/@lottiefiles/dotlottie-wc@0.6.2/dist/dotlottie-wc.js';
            script.type = 'module';
            document.head.appendChild(script);
        }
    }

    show(message = 'Loading...') {
        if (this.preloaderElement) {
            this.loadingTextElement.textContent = message;
            this.preloaderElement.style.opacity = '1';
            this.preloaderElement.style.visibility = 'visible';
            document.body.style.overflow = 'hidden';
        }
    }

    hide() {
        if (this.preloaderElement) {
            this.preloaderElement.style.opacity = '0';
            this.preloaderElement.style.visibility = 'hidden';
            document.body.style.overflow = '';
        }
    }

    setupAPIInterceptors() {
        // Intercept fetch requests
        const originalFetch = window.fetch;
        
        window.fetch = async (...args) => {
            const url = args[0];
            
            // Only show preloader for API calls
            if (typeof url === 'string' && url.includes('/api/')) {
                this.startRequest(this.getLoadingMessage(url));
            }
            
            try {
                const response = await originalFetch(...args);
                return response;
            } finally {
                if (typeof url === 'string' && url.includes('/api/')) {
                    this.endRequest();
                }
            }
        };

        // Intercept XMLHttpRequests
        const originalOpen = XMLHttpRequest.prototype.open;
        const originalSend = XMLHttpRequest.prototype.send;

        XMLHttpRequest.prototype.open = function(method, url, ...args) {
            this._url = url;
            return originalOpen.call(this, method, url, ...args);
        };

        XMLHttpRequest.prototype.send = function(...args) {
            if (this._url && this._url.includes('/api/')) {
                window.lottiePreloader.startRequest(
                    window.lottiePreloader.getLoadingMessage(this._url)
                );
                
                this.addEventListener('loadend', () => {
                    window.lottiePreloader.endRequest();
                });
            }
            
            return originalSend.call(this, ...args);
        };
    }

    startRequest(message = 'Loading...') {
        this.activeRequests++;
        if (this.activeRequests === 1) {
            this.show(message);
        } else {
            // Update message if already showing
            this.loadingTextElement.textContent = message;
        }
    }

    endRequest() {
        this.activeRequests = Math.max(0, this.activeRequests - 1);
        if (this.activeRequests === 0) {
            // Add slight delay to prevent flickering
            setTimeout(() => {
                if (this.activeRequests === 0) {
                    this.hide();
                }
            }, 200);
        }
    }

    getLoadingMessage(url) {
        // Return specific loading messages based on API endpoint
        const messages = {
            '/api/public/register': 'Creating your account...',
            '/api/public/login': 'Signing you in...',
            '/api/tenant/create': 'Setting up your tenant...',
            '/api/tenant/': 'Loading tenant information...',
            '/api/billing/': 'Processing billing information...',
            '/api/support/tickets': 'Loading support tickets...',
            '/api/user/notifications': 'Checking notifications...',
            '/api/user/profile': 'Loading your profile...',
            '/api/user/tenants': 'Loading your tenants...',
            '/backup': 'Creating backup...',
            '/status': 'Checking status...'
        };

        for (const [path, message] of Object.entries(messages)) {
            if (url.includes(path)) {
                return message;
            }
        }

        return 'Loading...';
    }

    // Utility methods for manual control
    showWithCustomMessage(message, duration = null) {
        this.show(message);
        if (duration) {
            setTimeout(() => this.hide(), duration);
        }
    }

    destroy() {
        if (this.preloaderElement) {
            this.preloaderElement.remove();
        }
        
        // Restore original fetch (if needed)
        // Note: In production, you might want to keep the interceptor
    }
}

// Initialize preloader when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.lottiePreloader = new LottiePreloader();
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LottiePreloader;
}