/**
 * Lottie Preloader Usage Examples
 * Complete implementation examples for different platforms
 */

// ================= REACT NATIVE EXAMPLE =================

import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ScrollView,
} from 'react-native';
import LottiePreloader, { 
  usePreloader, 
  APIServiceWithPreloader 
} from './LottiePreloader';

// Example Screen Component
const ExampleScreen = () => {
  const preloader = usePreloader();
  const [apiService] = useState(new APIServiceWithPreloader(
    'https://your-api-domain.com', 
    preloader
  ));

  const handleLogin = async () => {
    try {
      const result = await apiService.login({
        username: 'demo@example.com',
        password: 'password123',
      });
      
      Alert.alert('Success', 'Login successful!');
    } catch (error) {
      Alert.alert('Error', error.message);
    }
  };

  const handleCreateTenant = async () => {
    try {
      const result = await apiService.createTenant({
        name: 'My New Company',
        subdomain: 'mynewcompany',
        plan: 'basic',
      });
      
      Alert.alert('Success', 'Tenant created successfully!');
    } catch (error) {
      Alert.alert('Error', error.message);
    }
  };

  const handleGetNotifications = async () => {
    try {
      const result = await apiService.getNotifications();
      Alert.alert('Notifications', `Found ${result.counts.total} notifications`);
    } catch (error) {
      Alert.alert('Error', error.message);
    }
  };

  const handleCustomLoading = () => {
    preloader.show('Processing your request...');
    
    // Simulate work
    setTimeout(() => {
      preloader.updateMessage('Almost done...');
      
      setTimeout(() => {
        preloader.hide();
        Alert.alert('Done', 'Custom loading completed!');
      }, 2000);
    }, 2000);
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Lottie Preloader Examples</Text>
      
      <TouchableOpacity style={styles.button} onPress={handleLogin}>
        <Text style={styles.buttonText}>Test Login</Text>
      </TouchableOpacity>
      
      <TouchableOpacity style={styles.button} onPress={handleCreateTenant}>
        <Text style={styles.buttonText}>Create Tenant</Text>
      </TouchableOpacity>
      
      <TouchableOpacity style={styles.button} onPress={handleGetNotifications}>
        <Text style={styles.buttonText}>Get Notifications</Text>
      </TouchableOpacity>
      
      <TouchableOpacity style={styles.button} onPress={handleCustomLoading}>
        <Text style={styles.buttonText}>Custom Loading</Text>
      </TouchableOpacity>

      {/* The preloader component */}
      <LottiePreloader
        visible={preloader.loading}
        message={preloader.message}
        onDismiss={() => {}}
        style={styles.customPreloader}
        textStyle={styles.customText}
      />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: '#f5f5f5',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 30,
    color: '#333',
  },
  button: {
    backgroundColor: '#007AFF',
    padding: 15,
    borderRadius: 10,
    marginBottom: 15,
    alignItems: 'center',
  },
  buttonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  customPreloader: {
    backgroundColor: '#f8f9fa',
    borderRadius: 15,
  },
  customText: {
    color: '#007AFF',
    fontSize: 14,
  },
});

export default ExampleScreen;

// ================= WEB JAVASCRIPT EXAMPLE =================

// HTML Integration Example
const webExample = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API with Lottie Preloader</title>
    <script src="https://unpkg.com/@lottiefiles/dotlottie-wc@0.6.2/dist/dotlottie-wc.js" type="module"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .button {
            background: #007AFF;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            margin: 10px;
            transition: background 0.2s;
        }
        .button:hover {
            background: #0056CC;
        }
        .button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Lottie Preloader Web Example</h1>
        
        <button class="button" onclick="testLogin()">Test Login</button>
        <button class="button" onclick="testTenantCreation()">Create Tenant</button>
        <button class="button" onclick="testNotifications()">Get Notifications</button>
        <button class="button" onclick="testCustomLoading()">Custom Loading</button>
        
        <div id="results" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 5px; display: none;">
            <h3>Results:</h3>
            <pre id="result-content"></pre>
        </div>
    </div>

    <script src="/static/js/preloader.js"></script>
    <script>
        // API Service Class
        class APIService {
            constructor(baseURL) {
                this.baseURL = baseURL;
            }

            async request(endpoint, options = {}) {
                const response = await fetch(this.baseURL + endpoint, {
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
            }
        }

        const apiService = new APIService('http://localhost:5000');

        function showResults(data) {
            document.getElementById('results').style.display = 'block';
            document.getElementById('result-content').textContent = JSON.stringify(data, null, 2);
        }

        async function testLogin() {
            try {
                const result = await apiService.request('/api/public/login', {
                    method: 'POST',
                    body: JSON.stringify({
                        username: 'demo@example.com',
                        password: 'password123',
                    }),
                });
                showResults(result);
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function testTenantCreation() {
            try {
                const result = await apiService.request('/api/tenant/create', {
                    method: 'POST',
                    body: JSON.stringify({
                        name: 'Web Test Company',
                        subdomain: 'webtestco' + Date.now(),
                        plan: 'basic',
                    }),
                });
                showResults(result);
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function testNotifications() {
            try {
                const result = await apiService.request('/api/user/notifications');
                showResults(result);
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        function testCustomLoading() {
            window.lottiePreloader.show('Custom loading message...');
            
            setTimeout(() => {
                window.lottiePreloader.loadingTextElement.textContent = 'Processing...';
                
                setTimeout(() => {
                    window.lottiePreloader.hide();
                    alert('Custom loading completed!');
                }, 2000);
            }, 2000);
        }
    </script>
</body>
</html>
`;

// ================= FLUTTER EXAMPLE =================

const flutterExample = `
// pubspec.yaml
dependencies:
  flutter:
    sdk: flutter
  lottie: ^2.7.0
  http: ^1.1.0

// lib/preloader.dart
import 'package:flutter/material.dart';
import 'package:lottie/lottie.dart';

class LottiePreloader extends StatelessWidget {
  final bool isVisible;
  final String message;
  final VoidCallback? onDismiss;

  const LottiePreloader({
    Key? key,
    required this.isVisible,
    this.message = 'Loading...',
    this.onDismiss,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    if (!isVisible) return const SizedBox.shrink();

    return Container(
      color: Colors.white.withOpacity(0.9),
      child: Center(
        child: Container(
          padding: const EdgeInsets.all(30),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.1),
                blurRadius: 10,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Lottie.network(
                'https://lottie.host/2ca5e67b-55b9-4f90-8bd5-8c536ebfb522/6r2AmJ81Et.lottie',
                width: 300,
                height: 300,
                fit: BoxFit.cover,
              ),
              const SizedBox(height: 20),
              Text(
                message,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                  color: Colors.black87,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// Usage in Flutter app
class ExampleScreen extends StatefulWidget {
  @override
  _ExampleScreenState createState() => _ExampleScreenState();
}

class _ExampleScreenState extends State<ExampleScreen> {
  bool _isLoading = false;
  String _loadingMessage = 'Loading...';

  void _showPreloader(String message) {
    setState(() {
      _isLoading = true;
      _loadingMessage = message;
    });
  }

  void _hidePreloader() {
    setState(() {
      _isLoading = false;
    });
  }

  Future<void> _testLogin() async {
    _showPreloader('Signing you in...');
    
    try {
      // Simulate API call
      await Future.delayed(const Duration(seconds: 2));
      // Your API logic here
    } finally {
      _hidePreloader();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Lottie Preloader Example')),
      body: Stack(
        children: [
          // Your main content
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              children: [
                ElevatedButton(
                  onPressed: _testLogin,
                  child: const Text('Test Login'),
                ),
                // More buttons...
              ],
            ),
          ),
          // Preloader overlay
          LottiePreloader(
            isVisible: _isLoading,
            message: _loadingMessage,
          ),
        ],
      ),
    );
  }
}
`;

// ================= IOS SWIFT EXAMPLE =================

const swiftExample = `
// Add Lottie to your iOS project via CocoaPods or SPM
// pod 'lottie-ios'

import UIKit
import Lottie

class LottiePreloader: UIView {
    private let animationView = LottieAnimationView()
    private let messageLabel = UILabel()
    private let containerView = UIView()
    
    override init(frame: CGRect) {
        super.init(frame: frame)
        setupUI()
    }
    
    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupUI()
    }
    
    private func setupUI() {
        backgroundColor = UIColor.white.withAlphaComponent(0.9)
        
        // Container
        containerView.backgroundColor = .white
        containerView.layer.cornerRadius = 20
        containerView.layer.shadowColor = UIColor.black.cgColor
        containerView.layer.shadowOpacity = 0.1
        containerView.layer.shadowOffset = CGSize(width: 0, height: 4)
        containerView.layer.shadowRadius = 10
        containerView.translatesAutoresizingMaskIntoConstraints = false
        addSubview(containerView)
        
        // Animation
        animationView.animation = LottieAnimation.named("your_animation") // or from URL
        animationView.loopMode = .loop
        animationView.contentMode = .scaleAspectFit
        animationView.translatesAutoresizingMaskIntoConstraints = false
        containerView.addSubview(animationView)
        
        // Message label
        messageLabel.text = "Loading..."
        messageLabel.textAlignment = .center
        messageLabel.font = UIFont.systemFont(ofSize: 16, weight: .medium)
        messageLabel.textColor = .darkGray
        messageLabel.translatesAutoresizingMaskIntoConstraints = false
        containerView.addSubview(messageLabel)
        
        // Constraints
        NSLayoutConstraint.activate([
            containerView.centerXAnchor.constraint(equalTo: centerXAnchor),
            containerView.centerYAnchor.constraint(equalTo: centerYAnchor),
            containerView.widthAnchor.constraint(equalToConstant: 200),
            containerView.heightAnchor.constraint(equalToConstant: 200),
            
            animationView.topAnchor.constraint(equalTo: containerView.topAnchor, constant: 20),
            animationView.centerXAnchor.constraint(equalTo: containerView.centerXAnchor),
            animationView.widthAnchor.constraint(equalToConstant: 120),
            animationView.heightAnchor.constraint(equalToConstant: 120),
            
            messageLabel.topAnchor.constraint(equalTo: animationView.bottomAnchor, constant: 10),
            messageLabel.leadingAnchor.constraint(equalTo: containerView.leadingAnchor, constant: 16),
            messageLabel.trailingAnchor.constraint(equalTo: containerView.trailingAnchor, constant: -16),
            messageLabel.bottomAnchor.constraint(equalTo: containerView.bottomAnchor, constant: -20)
        ])
    }
    
    func show(with message: String = "Loading...") {
        messageLabel.text = message
        animationView.play()
        
        alpha = 0
        transform = CGAffineTransform(scaleX: 0.8, y: 0.8)
        isHidden = false
        
        UIView.animate(withDuration: 0.3, delay: 0, usingSpringWithDamping: 0.8, initialSpringVelocity: 0, options: .curveEaseOut) {
            self.alpha = 1
            self.transform = .identity
        }
    }
    
    func hide() {
        UIView.animate(withDuration: 0.2) {
            self.alpha = 0
            self.transform = CGAffineTransform(scaleX: 0.8, y: 0.8)
        } completion: { _ in
            self.isHidden = true
            self.animationView.stop()
        }
    }
    
    func updateMessage(_ message: String) {
        messageLabel.text = message
    }
}

// Usage in ViewController
class ViewController: UIViewController {
    private let preloader = LottiePreloader()
    
    override func viewDidLoad() {
        super.viewDidLoad()
        setupPreloader()
    }
    
    private func setupPreloader() {
        preloader.isHidden = true
        preloader.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(preloader)
        
        NSLayoutConstraint.activate([
            preloader.topAnchor.constraint(equalTo: view.topAnchor),
            preloader.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            preloader.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            preloader.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
    }
    
    @IBAction func testLogin(_ sender: UIButton) {
        preloader.show(with: "Signing you in...")
        
        // Simulate API call
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            self.preloader.hide()
        }
    }
}
`;

// ================= USAGE DOCUMENTATION =================

const usageDocumentation = `
# Lottie Preloader Integration Guide

## Overview
The Lottie preloader provides beautiful loading animations for all API calls across different platforms.

## Features
- ✅ Automatic API call detection
- ✅ Custom loading messages per endpoint
- ✅ Smooth animations with fade in/out
- ✅ Multi-platform support (Web, React Native, iOS, Android)
- ✅ Customizable styling
- ✅ Manual control options

## Installation

### Web
1. Include the Lottie web component script
2. Include the preloader.js script
3. The preloader will automatically initialize

### React Native
\`\`\`bash
npm install lottie-react-native
# For iOS: cd ios && pod install
\`\`\`

### iOS
Add to Podfile:
\`\`\`ruby
pod 'lottie-ios'
\`\`\`

### Android
Add to app/build.gradle:
\`\`\`gradle
implementation 'com.airbnb.android:lottie:6.1.0'
\`\`\`

## API Endpoints with Custom Messages

The preloader automatically shows contextual messages:

- Registration: "Creating your account..."
- Login: "Signing you in..."
- Tenant Creation: "Setting up your tenant..."
- Billing: "Processing billing information..."
- Support: "Loading support tickets..."
- Notifications: "Checking notifications..."
- Backups: "Creating backup..."

## Manual Control

### Web
\`\`\`javascript
// Show with custom message
window.lottiePreloader.show('Processing your request...');

// Hide
window.lottiePreloader.hide();

// Show with auto-hide after duration
window.lottiePreloader.showWithCustomMessage('Done!', 2000);
\`\`\`

### React Native
\`\`\`javascript
const preloader = usePreloader();

preloader.show('Custom message...');
preloader.updateMessage('Updated message...');
preloader.hide();
\`\`\`

## Customization

### Styling
You can customize the appearance by modifying the styles in each platform's implementation.

### Animation
Replace the Lottie URL with your custom animation:
\`\`\`
https://lottie.host/your-animation-id/animation.lottie
\`\`\`

## Best Practices

1. **Keep messages short and descriptive**
2. **Use consistent messaging across platforms** 
3. **Don't show preloader for very quick operations (<100ms)**
4. **Always hide preloader in finally blocks**
5. **Test on slow networks to ensure good UX**

## Troubleshooting

### Preloader not showing
- Check if Lottie script is loaded
- Verify API endpoints include '/api/'
- Check console for JavaScript errors

### Animation not playing
- Verify Lottie URL is accessible
- Check network connectivity
- Ensure proper Lottie library version

### Performance issues
- Consider using cached animations
- Implement lazy loading for heavy animations
- Optimize animation file size
`;

module.exports = {
  ExampleScreen,
  webExample,
  flutterExample,
  swiftExample,
  usageDocumentation,
};