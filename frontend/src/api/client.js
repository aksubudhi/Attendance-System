import axios from 'axios';

const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL,
    withCredentials: true,
    headers: {
        'Content-Type': 'application/x-www-form-urlencoded', // Default for Form data in this app
    }
});

// Helper to handle JSON payloads if needed (override header)
export const postJson = (url, data) => {
    return api.post(url, data, {
        headers: {
            'Content-Type': 'application/json'
        }
    });
};

api.interceptors.response.use(
    (response) => response.data,
    (error) => {
        if (error.response && error.response.status === 401) {
            if (!window.location.pathname.includes('/login')) {
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export default api;
