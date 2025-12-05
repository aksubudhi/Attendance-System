
(function() {
    // Don't run auth check on login page itself
    if (window.location.pathname === '/login') {
        return;
    }
    
    // Check if user has valid session by calling API
    async function checkAuth() {
        try {
            const response = await fetch('/api/auth/check', {
                method: 'GET',
                credentials: 'include'
            });
            
            if (!response.ok) {
                // Not authenticated, redirect to login
                console.log('Not authenticated, redirecting to login...');
                window.location.href = '/login';
            }
        } catch (error) {
            // Error checking auth, redirect to login
            console.error('Auth check failed:', error);
            window.location.href = '/login';
        }
    }
    
    // Run auth check immediately
    checkAuth();
    
    // Re-check every 5 minutes
    setInterval(checkAuth, 5 * 60 * 1000);
})();
