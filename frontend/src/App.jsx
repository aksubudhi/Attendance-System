import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'

import Employees from './pages/Employees'

import Attendance from './pages/Attendance'
import Cameras from './pages/Cameras'

// Placeholder for other pages
const Placeholder = ({ title }) => (
    <div style={{ padding: '2rem' }}>
        <h1 className="text-gradient" style={{ fontSize: '2rem' }}>{title}</h1>
        <p style={{ color: 'var(--text-secondary)' }}>Coming soon...</p>
    </div>
);

function App() {
    return (
        <Routes>
            <Route path="/login" element={<Login />} />

            {/* Protected Routes */}
            <Route element={<Layout />}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/employees" element={<Employees />} />
                <Route path="/attendance" element={<Attendance />} />
                <Route path="/cameras" element={<Cameras />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    )
}

export default App
