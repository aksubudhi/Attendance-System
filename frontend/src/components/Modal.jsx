import React, { useEffect } from 'react';
import { X } from 'lucide-react';

export default function Modal({ isOpen, onClose, title, children, footer }) {
    if (!isOpen) return null;

    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleEsc);
        return () => window.removeEventListener('keydown', handleEsc);
    }, [onClose]);

    return (
        <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            zIndex: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '1rem'
        }}>
            {/* Backdrop */}
            <div
                onClick={onClose}
                className="animate-fade-in"
                style={{
                    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0,0,0,0.6)',
                    backdropFilter: 'blur(4px)'
                }}
            />

            {/* Modal Content */}
            <div className="glass-panel animate-fade-in" style={{
                width: '100%',
                maxWidth: '500px',
                borderRadius: '16px',
                position: 'relative',
                zIndex: 101,
                maxHeight: '90vh',
                display: 'flex',
                flexDirection: 'column'
            }}>
                <div style={{
                    padding: '1.5rem',
                    borderBottom: '1px solid var(--glass-border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between'
                }}>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>{title}</h3>
                    <button onClick={onClose} className="btn-ghost" style={{ padding: '0.25rem' }}>
                        <X size={20} />
                    </button>
                </div>

                <div style={{ padding: '1.5rem', overflowY: 'auto' }}>
                    {children}
                </div>

                {footer && (
                    <div style={{
                        padding: '1rem 1.5rem',
                        borderTop: '1px solid var(--glass-border)',
                        background: 'rgba(0,0,0,0.2)',
                        display: 'flex', justifyContent: 'flex-end', gap: '0.75rem'
                    }}>
                        {footer}
                    </div>
                )}
            </div>
        </div>
    );
}
