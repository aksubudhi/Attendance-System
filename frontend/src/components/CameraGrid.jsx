import React, { useEffect, useRef, useState } from 'react';
import { Play, Square, Video, AlertCircle, Wifi } from 'lucide-react';

export default function CameraGrid() {
    const [socket, setSocket] = useState(null);
    const [frames, setFrames] = useState({ entry: null, exit: null });
    const [status, setStatus] = useState('disconnected');
    const [monitoring, setMonitoring] = useState(false);
    const [activeUsers, setActiveUsers] = useState(0);

    // DYNAMIC WEBSOCKET URL CONSTRUCTION
    // Uses the API Base URL from .env (e.g., https://backend.onrender.com/api)
    // STRIPS '/api' suffix if present, then replaces http -> ws
    const getWsUrl = () => {
        let apiBase = import.meta.env.VITE_API_BASE_URL;

        // If no env var, fallback to safe default or window location
        if (!apiBase) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${protocol}//${window.location.host}/ws`;
        }

        // Remove trailing slash if present
        if (apiBase.endsWith('/')) {
            apiBase = apiBase.slice(0, -1);
        }

        // Remove '/api' suffix if present (because WS is at /ws, not /api/ws)
        if (apiBase.endsWith('/api')) {
            apiBase = apiBase.slice(0, -4);
        }

        // Replace http sequence with ws sequence
        return apiBase.replace(/^http/, 'ws') + '/ws';
    };

    const wsUrl = getWsUrl();

    useEffect(() => {
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('WS Connected');
            setStatus('connected');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'frame') {
                    setFrames(prev => ({
                        ...prev,
                        [data.camera]: data.image
                    }));
                } else if (data.type === 'status') {
                    if (data.camera_status === 'started' || data.camera_status === 'already_running') {
                        setMonitoring(true);
                    } else if (data.camera_status === 'stopped') {
                        setMonitoring(false);
                        // Clear frames on stop
                        setFrames({ entry: null, exit: null });
                    }
                    if (data.active_users) setActiveUsers(data.active_users);
                } else if (data.type === 'stats') {
                    if (data.active_users) setActiveUsers(data.active_users);
                } else if (data.type === 'connection_status') {
                    if (data.cameras_running) setMonitoring(true);
                    if (data.active_users) setActiveUsers(data.active_users);
                }
            } catch (e) {
                console.error('WS Parse Error', e);
            }
        };

        ws.onclose = () => {
            console.log('WS Disconnected');
            setStatus('disconnected');
        };

        setSocket(ws);

        return () => {
            ws.close();
        };
    }, []);

    const toggleCamera = () => {
        if (!socket) return;

        if (monitoring) {
            socket.send(JSON.stringify({ action: 'stop' }));
        } else {
            socket.send(JSON.stringify({ action: 'start' }));
            // Also request cached frames immediately
            socket.send(JSON.stringify({ action: 'get_cached_frames' }));
        }
    };

    const CameraBox = ({ title, image, id }) => (
        <div className="glass-card" style={{
            aspectRatio: '16/9',
            position: 'relative',
            overflow: 'hidden',
            background: '#000',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
            {image ? (
                <img
                    src={`data:image/jpeg;base64,${image}`}
                    alt={title}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
            ) : (
                <div style={{ color: 'var(--text-muted)', textAlign: 'center' }}>
                    <Video size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                    <p>{status === 'connected' ? (monitoring ? 'Waiting for signal...' : 'Cameras Off') : 'Disconnected'}</p>
                </div>
            )}

            {/* Overlay Badge */}
            <div style={{
                position: 'absolute', top: '1rem', left: '1rem',
                background: 'rgba(0,0,0,0.6)', padding: '0.25rem 0.75rem',
                borderRadius: 'var(--radius-full)', border: '1px solid rgba(255,255,255,0.1)',
                display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem'
            }}>
                {monitoring && image ? (
                    <>
                        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#EF4444', boxShadow: '0 0 10px #EF4444' }} />
                        LIVE
                    </>
                ) : (
                    <>
                        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#6B7280' }} />
                        OFFLINE
                    </>
                )}
            </div>

            <div style={{
                position: 'absolute', bottom: '1rem', left: '1rem',
                textShadow: '0 2px 4px rgba(0,0,0,0.8)',
                fontWeight: 600
            }}>
                {title}
            </div>
        </div>
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Live Feeds</h2>
                    {status === 'connected' && (
                        <span className="status-badge status-active">
                            <Wifi size={14} /> WebSocket Connected
                        </span>
                    )}
                    {status === 'disconnected' && (
                        <span className="status-badge status-inactive">
                            <AlertCircle size={14} /> Disconnected
                        </span>
                    )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                        Active Viewers: <b>{activeUsers}</b>
                    </span>
                    <button
                        onClick={toggleCamera}
                        className={`btn-primary`}
                        style={{
                            background: monitoring ? 'rgba(239, 68, 68, 0.1)' : undefined,
                            color: monitoring ? '#ef4444' : undefined,
                            border: monitoring ? '1px solid rgba(239, 68, 68, 0.2)' : undefined,
                            display: 'flex', alignItems: 'center', gap: '0.5rem'
                        }}
                    >
                        {monitoring ? <Square size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
                        {monitoring ? 'Stop Cameras' : 'Start Cameras'}
                    </button>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
                <CameraBox title="Entry Gate" image={frames.entry} id="entry" />
                <CameraBox title="Exit Gate" image={frames.exit} id="exit" />
            </div>
        </div>
    );
}
