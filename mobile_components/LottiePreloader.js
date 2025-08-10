/**
 * React Native Lottie Preloader Component
 * Beautiful loading animation for mobile app API calls
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  Modal,
  StyleSheet,
  Animated,
  Dimensions,
} from 'react-native';
import LottieView from 'lottie-react-native'; // npm install lottie-react-native

const { width, height } = Dimensions.get('window');

const LottiePreloader = ({
  visible = false,
  message = 'Loading...',
  onDismiss,
  style = {},
  textStyle = {},
}) => {
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.8)).current;

  useEffect(() => {
    if (visible) {
      // Animate in
      Animated.parallel([
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 300,
          useNativeDriver: true,
        }),
        Animated.spring(scaleAnim, {
          toValue: 1,
          tension: 100,
          friction: 8,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      // Animate out
      Animated.parallel([
        Animated.timing(fadeAnim, {
          toValue: 0,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(scaleAnim, {
          toValue: 0.8,
          duration: 200,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible]);

  return (
    <Modal
      transparent
      visible={visible}
      animationType="none"
      onRequestClose={onDismiss}
      statusBarTranslucent
    >
      <Animated.View
        style={[
          styles.overlay,
          {
            opacity: fadeAnim,
          },
        ]}
      >
        <Animated.View
          style={[
            styles.container,
            style,
            {
              transform: [{ scale: scaleAnim }],
            },
          ]}
        >
          <LottieView
            source={{
              uri: 'https://lottie.host/2ca5e67b-55b9-4f90-8bd5-8c536ebfb522/6r2AmJ81Et.lottie',
            }}
            style={styles.lottie}
            autoPlay
            loop
            speed={1}
          />
          
          <Text style={[styles.message, textStyle]}>
            {message}
          </Text>
        </Animated.View>
      </Animated.View>
    </Modal>
  );
};

// Hook for managing preloader state
export const usePreloader = () => {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('Loading...');

  const show = (customMessage = 'Loading...') => {
    setMessage(customMessage);
    setLoading(true);
  };

  const hide = () => {
    setLoading(false);
  };

  const updateMessage = (newMessage) => {
    setMessage(newMessage);
  };

  return {
    loading,
    message,
    show,
    hide,
    updateMessage,
  };
};

// API Service with integrated preloader
export class APIServiceWithPreloader {
  constructor(baseURL, preloaderHook) {
    this.baseURL = baseURL;
    this.preloader = preloaderHook;
  }

  async request(endpoint, options = {}, loadingMessage) {
    try {
      // Show preloader with custom message
      const message = loadingMessage || this.getLoadingMessage(endpoint);
      this.preloader.show(message);

      const response = await fetch(`${this.baseURL}${endpoint}`, {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      });

      const data = await response.json();
      
      if (!data.success) {
        throw new Error(data.error || 'Request failed');
      }

      return data;
    } finally {
      // Hide preloader
      this.preloader.hide();
    }
  }

  getLoadingMessage(endpoint) {
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
      '/status': 'Checking status...',
    };

    for (const [path, message] of Object.entries(messages)) {
      if (endpoint.includes(path)) {
        return message;
      }
    }

    return 'Loading...';
  }

  // Convenience methods for different API calls
  async register(userData) {
    return this.request('/api/public/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    }, 'Creating your account...');
  }

  async login(credentials) {
    return this.request('/api/public/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    }, 'Signing you in...');
  }

  async createTenant(tenantData) {
    return this.request('/api/tenant/create', {
      method: 'POST',
      body: JSON.stringify(tenantData),
    }, 'Setting up your tenant...');
  }

  async getTenants() {
    return this.request('/api/user/tenants', {}, 'Loading your tenants...');
  }

  async getNotifications() {
    return this.request('/api/user/notifications', {}, 'Checking notifications...');
  }

  async createSupportTicket(ticketData) {
    return this.request('/api/support/tickets', {
      method: 'POST',
      body: JSON.stringify(ticketData),
    }, 'Creating support ticket...');
  }

  async getBillingPlans() {
    return this.request('/api/billing/plans', {}, 'Loading billing plans...');
  }
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'transparent',
    justifyContent: 'center',
    alignItems: 'center',
    background: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 50%, #c026d3 100%)',
  },
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
    borderRadius: 25,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    shadowColor: '#000',
    shadowOffset: {
      width: 0,
      height: 8,
    },
    shadowOpacity: 0.25,
    shadowRadius: 20,
    elevation: 8,
    minWidth: 340,
    maxWidth: width * 0.9,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  lottie: {
    width: 300,
    height: 300,
  },
  message: {
    marginTop: 20,
    fontSize: 16,
    color: '#333',
    textAlign: 'center',
    fontWeight: '500',
  },
});

export default LottiePreloader;