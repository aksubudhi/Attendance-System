import React, { useEffect, useState } from 'react';
import { Download, Filter, Calendar } from 'lucide-react';
import Table from '../components/Table';
import api from '../api/client';

export default function Attendance() {
    const [records, setRecords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [pagination, setPagination] = useState({ skip: 0, limit: 20, total: 0 });
    const [filters, setFilters] = useState({
        from_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0], // Last 7 days
        to_date: new Date().toISOString().split('T')[0]
    });

    const fetchAttendance = async (skip = 0) => {
        setLoading(true);
        try {
            const query = `?skip=${skip}&limit=${pagination.limit}&from_date=${filters.from_date}&to_date=${filters.to_date}`;
            const res = await api.get(`/attendance/summary${query}`);
            setRecords(res.records);
            setPagination(prev => ({ ...prev, ...res.pagination }));
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAttendance(0);
    }, [filters]); // Refetch when filters change

    const handleExport = async () => {
        try {
            const query = `?from_date=${filters.from_date}&to_date=${filters.to_date}`;
            // Trigger download by opening in new window/tab or using blob
            window.location.href = `/api/attendance/export${query}`;
        } catch (e) {
            alert('Export failed');
        }
    };

    const columns = [
        { header: 'Date', accessor: 'date' },
        { header: 'Employee ID', accessor: 'emp_id' },
        { header: 'Name', accessor: 'name' },
        { header: 'First In', accessor: 'first_in' },
        { header: 'Last Out', accessor: 'last_out' },
        {
            header: 'Duration',
            accessor: 'duration',
            render: (row) => row.duration || '-'
        },
    ];

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
                <div>
                    <h1 className="text-gradient" style={{ fontSize: '2rem', fontWeight: 700 }}>Attendance</h1>
                    <p style={{ color: 'var(--text-secondary)' }}>View and export attendance logs</p>
                </div>

                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <div className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem' }}>
                        <Calendar size={16} color="var(--text-muted)" />
                        <input
                            type="date"
                            value={filters.from_date}
                            onChange={(e) => setFilters({ ...filters, from_date: e.target.value })}
                            style={{ background: 'transparent', border: 'none', color: 'white', outline: 'none', fontFamily: 'inherit' }}
                        />
                        <span style={{ color: 'var(--text-muted)' }}>to</span>
                        <input
                            type="date"
                            value={filters.to_date}
                            onChange={(e) => setFilters({ ...filters, to_date: e.target.value })}
                            style={{ background: 'transparent', border: 'none', color: 'white', outline: 'none', fontFamily: 'inherit' }}
                        />
                    </div>

                    <button className="btn-primary" onClick={handleExport} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Download size={18} /> Export Excel
                    </button>
                </div>
            </div>

            <Table
                columns={columns}
                data={records}
                pagination={pagination}
                onPageChange={(p) => fetchAttendance((p - 1) * pagination.limit)}
            />
        </div>
    );
}
