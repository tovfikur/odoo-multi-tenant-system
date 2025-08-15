// Modal Test Bookmarklet
// Copy this code and create a browser bookmark with it as the URL (prefix with javascript:)

(function() {
    // Create a floating test panel
    const testPanel = document.createElement('div');
    testPanel.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        width: 300px;
        background: #ffffff;
        border: 2px solid #007bff;
        border-radius: 8px;
        padding: 15px;
        z-index: 10000;
        font-family: monospace;
        font-size: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        max-height: 400px;
        overflow-y: auto;
    `;
    
    testPanel.innerHTML = `
        <div style="font-weight: bold; margin-bottom: 10px; color: #007bff;">
            🧪 Modal Test Panel
        </div>
        <div id="testResults" style="margin-bottom: 10px;">
            <div>Testing modal functionality...</div>
        </div>
        <button onclick="this.parentElement.remove()" style="float: right; background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">
            Close
        </button>
        <div style="clear: both;"></div>
    `;
    
    document.body.appendChild(testPanel);
    
    const results = document.getElementById('testResults');
    
    function addResult(message, status = 'info') {
        const colors = {
            'pass': '#28a745',
            'fail': '#dc3545', 
            'info': '#17a2b8',
            'warn': '#ffc107'
        };
        
        results.innerHTML += `<div style="color: ${colors[status]}; margin: 2px 0;">${message}</div>`;
    }
    
    // Test 1: Check if fixes are loaded
    addResult('🔍 Checking if modal fixes are loaded...');
    
    if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        addResult('✅ Bootstrap Modal class found', 'pass');
        
        // Check if our patches are applied
        if (bootstrap.Modal.toString().includes('element')) {
            addResult('✅ Bootstrap Modal patches detected', 'pass');
        } else {
            addResult('❌ Bootstrap Modal patches not detected', 'fail');
        }
    } else {
        addResult('❌ Bootstrap Modal class not found', 'fail');
    }
    
    // Test 2: Check for restore modal
    const restoreModal = document.getElementById('restoreModal');
    if (restoreModal) {
        addResult('✅ restoreModal found in DOM', 'pass');
        addResult(`   - Classes: ${restoreModal.className}`, 'info');
        addResult(`   - Parent: ${restoreModal.parentElement?.tagName}`, 'info');
    } else {
        addResult('❌ restoreModal NOT found in DOM', 'fail');
        
        // Check for any modals
        const allModals = document.querySelectorAll('.modal');
        addResult(`   - Total modals found: ${allModals.length}`, 'info');
        if (allModals.length > 0) {
            const modalIds = Array.from(allModals).map(m => m.id).join(', ');
            addResult(`   - Modal IDs: ${modalIds}`, 'info');
        }
    }
    
    // Test 3: Check for modal trigger buttons
    const triggers = document.querySelectorAll('[data-bs-toggle="modal"]');
    addResult(`🔍 Found ${triggers.length} modal triggers`, 'info');
    
    const restoreTrigger = document.querySelector('[data-bs-target="#restoreModal"]');
    if (restoreTrigger) {
        addResult('✅ Restore modal trigger found', 'pass');
        addResult(`   - Text: "${restoreTrigger.textContent?.trim()}"`, 'info');
    } else {
        addResult('❌ Restore modal trigger NOT found', 'fail');
    }
    
    // Test 4: Try creating modal instance
    if (restoreModal) {
        try {
            const testInstance = new bootstrap.Modal(restoreModal, {
                backdrop: true,
                keyboard: true,
                focus: true
            });
            addResult('✅ Modal instance creation: SUCCESS', 'pass');
            addResult(`   - Has _config: ${!!testInstance._config}`, 'info');
            addResult(`   - Has _element: ${!!testInstance._element}`, 'info');
            
            // Clean up
            testInstance.dispose();
        } catch (error) {
            addResult(`❌ Modal instance creation: FAILED`, 'fail');
            addResult(`   - Error: ${error.message}`, 'fail');
        }
    }
    
    // Test 5: Check console for our initialization
    addResult('🔍 Check browser console for detailed logs', 'info');
    addResult('   Look for: "🔧 Initializing page-specific modal fixes..."', 'info');
    
    // Final summary
    setTimeout(() => {
        const failCount = results.innerHTML.split('❌').length - 1;
        const passCount = results.innerHTML.split('✅').length - 1;
        
        if (failCount === 0) {
            addResult('🎉 ALL TESTS PASSED - Modal fix working!', 'pass');
        } else {
            addResult(`⚠️ ${failCount} issues found, ${passCount} tests passed`, 'warn');
        }
    }, 100);
    
})();

// To use this bookmarklet:
// 1. Copy the entire code above
// 2. Create a new bookmark in your browser
// 3. Set the URL to: javascript:(paste the code here)
// 4. Visit the tenant management page
// 5. Click the bookmark to run the tests