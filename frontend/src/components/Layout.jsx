import React, { useEffect, useState } from 'react';
import Sidebar from './Sidebar';
import { Outlet, useNavigate } from 'react-router-dom';
import api from '../api/client';

export default function Layout() {
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        // Check auth status
        const checkAuth = async () => {
            try {
                await api.get('/auth/check');
                setLoading(false);
            } catch (err) {
                navigate('/login');
            }
        };

        checkAuth();
    }, [navigate]);

    if (loading) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
                <div className="animate-pulse" style={{ color: 'var(--primary)' }}>Loading System...</div>
            </div>
        );
    }

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{
                flex: 1,
                marginLeft: '280px',
                padding: '2rem',
                width: 'calc(100% - 280px)'
            }}>
                <div className="animate-fade-in">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
