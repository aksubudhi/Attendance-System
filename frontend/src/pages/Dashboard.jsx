import React, { useEffect, useState } from 'react';
import CameraGrid from '../components/CameraGrid';
import { Users, UserCheck, Clock, ArrowUp, ArrowDown } from 'lucide-react';
import api from '../api/client';

export default function Dashboard() {
    const [stats, setStats] = useState({
        total_in: 0,
        total_out: 0,
        unique_employees: 0,
        date: ''
    });

    const fetchStats = async () => {
        try {
            const res = await api.get('/attendance/stats/today');
            if (res.success) {
                setStats(res);
            }
        } catch (e) {
            console.error("Failed to fetch stats", e);
        }
    };

    useEffect(() => {
        fetchStats();
        const interval = setInterval(fetchStats, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, []);

    const StatCard = ({ icon: Icon, label, value, color, subtext }) => (
        <div className="glass-card" style={{ padding: '1.5rem', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '0.5rem' }}>{label}</p>
                <h3 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.25rem' }}>{value}</h3>
                {subtext && <p style={{ fontSize: '0.75rem', color: color, display: 'flex', alignItems: 'center', gap: '0.25rem' }}>{subtext}</p>}
            </div>
            <div style={{
                padding: '0.75rem',
                borderRadius: '12px',
                background: `rgba(${color}, 0.1)`,
                color: `rgb(${color})`
            }}>
                <Icon size={24} />
            </div>
        </div>
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <header>
                <h1 className="text-gradient" style={{ fontSize: '2rem', fontWeight: 700 }}>Dashboard</h1>
                <p style={{ color: 'var(--text-secondary)' }}>
                    Real-time monitoring and attendance overview
                </p>
            </header>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem' }}>
                <StatCard
                    icon={Users}
                    label="Unique Visitors Today"
                    value={stats.unique_employees}
                    color="99, 102, 241"
                    subtext={<><ArrowUp size={12} /> Active Today</>}
                />
                <StatCard
                    icon={UserCheck}
                    label="Total Check-Ins"
                    value={stats.total_in}
                    color="16, 185, 129"
                />
                <StatCard
                    icon={Clock}
                    label="Total Check-Outs"
                    value={stats.total_out}
                    color="245, 158, 11"
                />
            </div>

            <CameraGrid />
        </div>
    );
}
