import React, { useEffect, useState } from 'react';
import { Camera, Save } from 'lucide-react';
import api, { postJson } from '../api/client';
import { InputGroup } from '../components/Forms';

export default function Cameras() {
    const [urls, setUrls] = useState({ entry_url: '', exit_url: '' });
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState(null);

    useEffect(() => {
        const fetchUrls = async () => {
            try {
                const res = await api.get('/camera/urls');
                setUrls(res);
            } catch (e) {
                console.error(e);
            }
        };
        fetchUrls();
    }, []);

    const handleSave = async (e) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);
        try {
            const res = await postJson('/camera/urls', urls);
            setMessage({ type: res.success ? 'success' : 'error', text: res.message });
        } catch (e) {
            setMessage({ type: 'error', text: 'Failed to save URLs' });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ maxWidth: '600px', margin: '0 auto' }}>
            <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
                <h1 className="text-gradient" style={{ fontSize: '2rem', fontWeight: 700 }}>Camera Settings</h1>
                <p style={{ color: 'var(--text-secondary)' }}>Configure RTSP streams for Entry and Exit cameras</p>
            </div>

            <div className="glass-panel" style={{ padding: '2rem', borderRadius: '16px' }}>
                <form onSubmit={handleSave}>
                    {message && (
                        <div style={{
                            padding: '1rem', marginBottom: '1.5rem', borderRadius: '8px',
                            background: message.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                            border: `1px solid ${message.type === 'success' ? 'var(--success)' : 'var(--danger)'}`,
                            color: message.type === 'success' ? 'var(--success)' : '#f87171'
                        }}>
                            {message.text}
                        </div>
                    )}

                    <div style={{ marginBottom: '1.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--primary)' }}>
                            <Camera size={20} />
                            <h3 style={{ fontWeight: 600 }}>RTSP Configuration</h3>
                        </div>

                        <InputGroup
                            label="Entry Camera URL"
                            value={urls.entry_url}
                            onChange={e => setUrls({ ...urls, entry_url: e.target.value })}
                            placeholder="rtsp://admin:pass@192.168.1.100..."
                            required
                        />

                        <InputGroup
                            label="Exit Camera URL"
                            value={urls.exit_url}
                            onChange={e => setUrls({ ...urls, exit_url: e.target.value })}
                            placeholder="rtsp://admin:pass@192.168.1.101..."
                            required
                        />
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button className="btn-primary" type="submit" disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Save size={18} />
                            {loading ? 'Saving...' : 'Save Configuration'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
