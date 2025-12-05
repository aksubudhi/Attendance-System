let allRecords = [];

async function loadStats() {
    try {
        const response = await fetch('/api/dashboard/stats');
        const data = await response.json();

        document.getElementById('stat-total').textContent = data.total_employees || 0;
        document.getElementById('stat-present').textContent = data.present_today || 0;
        document.getElementById('stat-absent').textContent = data.absent_today || 0;
    } catch (e) {
        console.error('Error loading stats:', e);
    }
}

async function load() {
    const from = document.getElementById('date-from').value;
    const to = document.getElementById('date-to').value;

    if (!from || !to) {
        alert('Please select date range');
        return;
    }

    try {
        const response = await fetch(`/api/attendance/summary?from_date=${from}&to_date=${to}`);
        const data = await response.json();
        allRecords = data.records || [];
        filter();
        loadStats();
    } catch (e) {
        console.error('Error loading attendance:', e);
        alert('Failed to load attendance records');
    }
}

function convertTimeToMinutes(timeStr) {
    if (!timeStr || timeStr === '-') return 0;
    const [hours, minutes, seconds] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
}

function filter() {
    const search = document.getElementById('search').value.toLowerCase();
    const filtered = allRecords.filter(r =>
        r.name.toLowerCase().includes(search) ||
        r.emp_id.toLowerCase().includes(search)
    );

    // Sort by Last OUT time (LATEST/HIGHEST time first)
    filtered.sort((a, b) => {
        const timeA = convertTimeToMinutes(a.last_out);
        const timeB = convertTimeToMinutes(b.last_out);
        
        // Sort in descending order (highest time first = latest out)
        return timeB - timeA;
    });

    const tbody = document.getElementById('table-body');

    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 3rem; color: #64748b;">
                    No records found
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = filtered.map(r => `
        <tr>
            <td>${r.date}</td>
            <td>${r.emp_id}</td>
            <td><strong>${r.name}</strong></td>
            <td>${r.department || 'N/A'}</td>
            <td>${r.first_in || '-'}</td>
            <td>${r.last_out || '-'}</td>
            <td>${r.duration || '-'}</td>
        </tr>
    `).join('');
}

async function exportData() {
    const from = document.getElementById('date-from').value;
    const to = document.getElementById('date-to').value;

    if (!from || !to) {
        alert('Please select date range first');
        return;
    }

    const exportBtn = event.target;
    const originalHTML = exportBtn.innerHTML;
    exportBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/></svg> Downloading...';
    exportBtn.disabled = true;

    try {
        // Direct download - file is generated on demand
        window.location.href = `/api/attendance/export?from_date=${from}&to_date=${to}`;

        // Re-enable button after a delay
        setTimeout(() => {
            exportBtn.innerHTML = originalHTML;
            exportBtn.disabled = false;
        }, 2000);
        
    } catch (error) {
        console.error('Error:', error);
        alert('Error exporting data');
        exportBtn.innerHTML = originalHTML;
        exportBtn.disabled = false;
    }
}

// Set default dates (last 7 days)
const today = new Date();
const lastWeek = new Date(today);
lastWeek.setDate(lastWeek.getDate() - 7);

document.getElementById('date-to').valueAsDate = today;
document.getElementById('date-from').valueAsDate = today;

window.onload = () => {
    load();
    loadStats();
};

