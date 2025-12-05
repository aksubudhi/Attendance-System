import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Users, UserPlus, ClipboardList, Camera, LogOut } from 'lucide-react';
import api from '../api/client';

export default function Sidebar() {
    const navigate = useNavigate();

    const handleLogout = async () => {
        try {
            await api.get('/logout'); // Assumes logout route returns 200/JSON even if already logged out
            navigate('/login');
        } catch (e) {
            console.error(e);
            navigate('/login');
        }
    };

    const navItems = [
        { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
        { to: '/employees', icon: Users, label: 'Employees' },
        { to: '/attendance', icon: ClipboardList, label: 'Attendance' },
        { to: '/cameras', icon: Camera, label: 'Cameras' },
    ];

    return (
        <aside className="glass-panel" style={{
            width: '280px',
            height: '100vh',
            position: 'fixed',
            left: 0,
            top: 0,
            padding: '2rem 1.5rem',
            display: 'flex',
            flexDirection: 'column',
            borderRight: '1px solid var(--glass-border)',
            borderTop: 'none',
            borderBottom: 'none',
            borderLeft: 'none',
            borderRadius: 0,
            zIndex: 50
        }}>
            <div style={{ marginBottom: '3rem', paddingLeft: '0.75rem' }}>
                <h1 className="text-gradient" style={{ fontSize: '1.5rem', fontWeight: '700' }}>
                    FaceAuth
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Attendance System</p>
            </div>

            <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {navItems.map((item) => (
                    <NavLink
                        key={item.to}
                        to={item.to}
                        className={({ isActive }) => `
              glass-card
            `}
                        style={({ isActive }) => ({
                            display: 'flex',
                            alignItems: 'center',
                            gap: '1rem',
                            padding: '1rem',
                            borderRadius: 'var(--radius-md)',
                            color: isActive ? 'white' : 'var(--text-secondary)',
                            background: isActive ? 'rgba(99, 102, 241, 0.1)' : 'transparent',
                            border: isActive ? '1px solid rgba(99, 102, 241, 0.2)' : '1px solid transparent',
                            textDecoration: 'none',
                            transition: 'all 0.2s ease'
                        })}
                    >
                        <item.icon size={20} />
                        <span style={{ fontWeight: 500 }}>{item.label}</span>
                    </NavLink>
                ))}
            </nav>

            <button
                onClick={handleLogout}
                className="glass-card"
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1rem',
                    padding: '1rem',
                    width: '100%',
                    marginTop: 'auto',
                    color: '#f87171',
                    border: '1px solid rgba(239, 68, 68, 0.1)'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
                <LogOut size={20} />
                <span style={{ fontWeight: 500 }}>Sign Out</span>
            </button>
        </aside>
    );
}
