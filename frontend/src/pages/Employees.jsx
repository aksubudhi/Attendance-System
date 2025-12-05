import React, { useEffect, useState, useRef } from 'react';
import { Plus, Edit2, Trash2, Search, User, Briefcase, UserPlus, Camera, Check, X, RefreshCw } from 'lucide-react';
import Table from '../components/Table';
import Modal from '../components/Modal';
import { InputGroup } from '../components/Forms';
import api, { postJson } from '../api/client';

const ANGLES = [
    { id: 'front', label: 'Front View' },
    { id: 'left', label: 'Look Left' },
    { id: 'right', label: 'Look Right' },
    { id: 'looking_up', label: 'Look Up' },
    { id: 'up_left', label: 'Up Left' },
    { id: 'up_right', label: 'Up Right' },
    // Optional if you want 8: { id: 'tilt_left', label: 'Tilt Left' }, { id: 'tilt_right', label: 'Tilt Right' }
];

export default function Employees() {
    const [employees, setEmployees] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [pagination, setPagination] = useState({ skip: 0, limit: 10, total: 0 });

    const [isModalOpen, setIsModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState('create'); // 'create', 'edit', 'face'
    const [formData, setFormData] = useState({ emp_id: '', name: '', department: '', position: '' });

    // Face Capture State
    const [currentEmp, setCurrentEmp] = useState(null);
    const [capturedAngles, setCapturedAngles] = useState({}); // { front: true, left: true, ... }
    const [cameraStream, setCameraStream] = useState(null);
    const videoRef = useRef(null);
    const [capturing, setCapturing] = useState(false);
    const [currentAngle, setCurrentAngle] = useState(ANGLES[0].id);

    const fetchEmployees = async (skip = 0) => {
        setLoading(true);
        try {
            const res = await api.get(`/employees/list?skip=${skip}&limit=${pagination.limit}`);
            setEmployees(res.employees);
            setPagination(prev => ({ ...prev, ...res.pagination }));
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchEmployees();
    }, []);

    const handleCreate = () => {
        setModalMode('create');
        setFormData({ emp_id: '', name: '', department: '', position: '' });
        setIsModalOpen(true);
    };

    const handleEdit = (emp) => {
        setModalMode('edit');
        setFormData({
            emp_id: emp.emp_id,
            name: emp.name,
            department: emp.department,
            position: emp.position
        });
        setIsModalOpen(true);
    };

    const handleFaceRegister = async (emp) => {
        setCurrentEmp(emp);
        setModalMode('face');
        setCapturedAngles({}); // Reset
        setCurrentAngle(ANGLES[0].id);
        setIsModalOpen(true);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            setCameraStream(stream);
        } catch (e) {
            alert('Cannot access camera. Please allow camera permissions.');
        }
    };

    const closeFaceModal = () => {
        if (cameraStream) {
            cameraStream.getTracks().forEach(track => track.stop());
            setCameraStream(null);
        }
        setIsModalOpen(false);
        fetchEmployees(pagination.skip);
    };

    const captureFrame = async () => {
        if (!videoRef.current || !currentEmp) return;

        setCapturing(true);
        try {
            const canvas = document.createElement('canvas');
            canvas.width = videoRef.current.videoWidth;
            canvas.height = videoRef.current.videoHeight;
            canvas.getContext('2d').drawImage(videoRef.current, 0, 0);

            // Convert to blob
            canvas.toBlob(async (blob) => {
                const fd = new FormData();
                fd.append('image', blob, 'capture.jpg');
                fd.append('emp_id', currentEmp.emp_id);
                fd.append('angle', currentAngle);

                try {
                    const res = await api.post('/capture-face', fd, {
                        headers: { 'Content-Type': 'multipart/form-data' }
                    });

                    if (res.success) {
                        setCapturedAngles(prev => ({ ...prev, [currentAngle]: true }));
                        // Auto advance to next incomplete angle
                        const next = ANGLES.find(a => a.id !== currentAngle && !capturedAngles[a.id]);
                        if (next) setCurrentAngle(next.id);
                    } else {
                        alert('Face not detected or low quality. Please try again.');
                    }
                } catch (e) {
                    alert('Upload failed: ' + e.message);
                } finally {
                    setCapturing(false);
                }
            }, 'image/jpeg', 0.95);
        } catch (e) {
            setCapturing(false);
        }
    };

    const handleDelete = async (empId) => {
        if (!confirm('Are you sure you want to delete this employee?')) return;
        try {
            await api.delete(`/employee/${empId}`);
            fetchEmployees(pagination.skip);
        } catch (e) {
            alert('Failed to delete employee');
        }
    };

    const handleSubmit = async () => {
        try {
            if (modalMode === 'create') {
                const res = await postJson('/create-employee', formData);
                if (res.success) {
                    setIsModalOpen(false);
                    fetchEmployees(0); // Reset to first page
                } else {
                    alert(res.message);
                }
            } else {
                const res = await api.put(`/employee/${formData.emp_id}`, formData);
                if (res.success) {
                    setIsModalOpen(false);
                    fetchEmployees(pagination.skip);
                } else {
                    alert(res.message);
                }
            }
        } catch (e) {
            console.error(e);
            alert('Operation failed');
        }
    };

    const columns = [
        { header: 'ID', accessor: 'emp_id' },
        {
            header: 'Name',
            accessor: 'name',
            render: (row) => (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{
                        width: '32px', height: '32px', borderRadius: '50%',
                        background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '0.875rem', fontWeight: 600
                    }}>
                        {row.name.charAt(0).toUpperCase()}
                    </div>
                    {row.name}
                </div>
            )
        },
        { header: 'Department', accessor: 'department' },
        { header: 'Position', accessor: 'position' },
        {
            header: 'Face Data',
            accessor: 'face_count',
            render: (row) => (
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <span className={row.face_count >= 6 ? "status-badge status-active" : "status-badge status-inactive"}>
                        {row.face_count >= 6 ? 'Registered' : `${row.face_count}/6 Angles`}
                    </span>
                    <button
                        className="btn-ghost"
                        onClick={() => handleFaceRegister(row)}
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', border: '1px solid var(--glass-border)' }}
                    >
                        <Camera size={14} style={{ marginRight: '4px' }} />
                        {row.face_count >= 6 ? 'Retake' : 'Register'}
                    </button>
                </div>
            )
        },
    ];

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
                <div>
                    <h1 className="text-gradient" style={{ fontSize: '2rem', fontWeight: 700 }}>Employees</h1>
                    <p style={{ color: 'var(--text-secondary)' }}>Manage workforce and face registration</p>
                </div>
                <button className="btn-primary" onClick={handleCreate} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Plus size={18} /> Add Employee
                </button>
            </div>

            <Table
                columns={columns}
                data={employees}
                pagination={pagination}
                onPageChange={(p) => fetchEmployees((p - 1) * pagination.limit)}
                actions={(row) => (
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button className="btn-ghost" onClick={() => handleEdit(row)} title="Edit">
                            <Edit2 size={16} />
                        </button>
                        <button className="btn-ghost" onClick={() => handleDelete(row.emp_id)} title="Delete" style={{ color: 'var(--danger)' }}>
                            <Trash2 size={16} />
                        </button>
                    </div>
                )}
            />

            <Modal
                isOpen={isModalOpen}
                onClose={modalMode === 'face' ? closeFaceModal : () => setIsModalOpen(false)}
                title={modalMode === 'create' ? 'Add New Employee' : (modalMode === 'face' ? `Register Face: ${currentEmp?.name}` : 'Edit Employee')}
                footer={
                    modalMode !== 'face' && (
                        <>
                            <button className="btn-ghost" onClick={() => setIsModalOpen(false)}>Cancel</button>
                            <button className="btn-primary" onClick={handleSubmit}>Save Changes</button>
                        </>
                    )
                }
            >
                {modalMode === 'face' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                        {/* Camera View */}
                        <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', background: '#000', aspectRatio: '4/3' }}>
                            {cameraStream ? (
                                <video
                                    ref={(ref) => {
                                        videoRef.current = ref;
                                        if (ref) ref.srcObject = cameraStream;
                                    }}
                                    autoPlay
                                    playsInline
                                    muted
                                    style={{ width: '100%', height: '100%', objectFit: 'cover', transform: 'scaleX(-1)' }}
                                />
                            ) : (
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
                                    Requesting camera...
                                </div>
                            )}

                            {/* Guidelines Overlay */}
                            <div style={{
                                position: 'absolute', top: '10%', left: '20%', right: '20%', bottom: '20%',
                                border: '2px dashed rgba(255,255,255,0.3)', borderRadius: '50%',
                                boxShadow: '0 0 0 9999px rgba(0,0,0,0.5)'
                            }} />
                        </div>

                        {/* Controls */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', maxWidth: '60%' }}>
                                {ANGLES.map(angle => (
                                    <button
                                        key={angle.id}
                                        onClick={() => setCurrentAngle(angle.id)}
                                        className={`btn-ghost`}
                                        style={{
                                            fontSize: '0.75rem', padding: '0.25rem 0.5rem',
                                            background: capturedAngles[angle.id] ? 'var(--success)' : (currentAngle === angle.id ? 'var(--primary)' : 'rgba(255,255,255,0.1)'),
                                            color: 'white', opacity: (currentAngle === angle.id || capturedAngles[angle.id]) ? 1 : 0.6
                                        }}
                                    >
                                        {capturedAngles[angle.id] && <Check size={12} style={{ marginRight: '4px' }} />}
                                        {angle.label}
                                    </button>
                                ))}
                            </div>

                            <button
                                className="btn-primary"
                                onClick={captureFrame}
                                disabled={capturing || !cameraStream}
                                style={{ minWidth: '120px' }}
                            >
                                {capturing ? 'Scanning...' : 'Capture'}
                            </button>
                        </div>

                        <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                            <p>Position face in oval and look <strong>{ANGLES.find(a => a.id === currentAngle)?.label}</strong></p>
                        </div>
                    </div>
                ) : (
                    <>
                        <InputGroup
                            label="Employee ID"
                            value={formData.emp_id}
                            onChange={e => setFormData({ ...formData, emp_id: e.target.value })}
                            // Disable ID editing
                            {...(modalMode === 'edit' ? { disabled: true, style: { opacity: 0.5 } } : {})}
                            required
                        />
                        <InputGroup
                            label="Full Name"
                            value={formData.name}
                            onChange={e => setFormData({ ...formData, name: e.target.value })}
                            required
                        />
                        <InputGroup
                            label="Department"
                            value={formData.department}
                            onChange={e => setFormData({ ...formData, department: e.target.value })}
                        />
                        <InputGroup
                            label="Position"
                            value={formData.position}
                            onChange={e => setFormData({ ...formData, position: e.target.value })}
                        />
                    </>
                )}
            </Modal>
        </div>
    );
}
