import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function Table({ columns, data, actions, pagination, onPageChange }) {
    return (
        <div className="glass-panel" style={{ overflow: 'hidden', padding: 0 }}>
            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid var(--glass-border)', background: 'rgba(255,255,255,0.02)' }}>
                            {columns.map((col, idx) => (
                                <th key={idx} style={{ padding: '1rem 1.5rem', fontWeight: 600, color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                                    {col.header}
                                </th>
                            ))}
                            {actions && <th style={{ padding: '1rem 1.5rem' }}></th>}
                        </tr>
                    </thead>
                    <tbody>
                        {data.length > 0 ? (
                            data.map((row, rIdx) => (
                                <tr key={rIdx} style={{ borderBottom: '1px solid var(--glass-border)', transition: 'background 0.2s' }}
                                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                                    {columns.map((col, cIdx) => (
                                        <td key={cIdx} style={{ padding: '1rem 1.5rem', color: 'var(--text-main)', fontSize: '0.925rem' }}>
                                            {col.render ? col.render(row) : row[col.accessor]}
                                        </td>
                                    ))}
                                    {actions && (
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'right' }}>
                                            {actions(row)}
                                        </td>
                                    )}
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan={columns.length + (actions ? 1 : 0)} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                                    No records found
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            {pagination && (
                <div style={{ padding: '1rem 1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--glass-border)' }}>
                    <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                        Showing {pagination.skip + 1} to {Math.min(pagination.skip + pagination.limit, pagination.total)} of {pagination.total} entries
                    </span>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                            className="btn-ghost"
                            disabled={pagination.current_page <= 1}
                            onClick={() => onPageChange(pagination.current_page - 1)}
                            style={{ opacity: pagination.current_page <= 1 ? 0.5 : 1 }}
                        >
                            <ChevronLeft size={18} />
                        </button>
                        <button
                            className="btn-ghost"
                            disabled={pagination.current_page >= pagination.pages}
                            onClick={() => onPageChange(pagination.current_page + 1)}
                            style={{ opacity: pagination.current_page >= pagination.pages ? 0.5 : 1 }}
                        >
                            <ChevronRight size={18} />
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
