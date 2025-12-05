let employees = [];
let currentPage = 1;
let itemsPerPage = 100;
let totalEmployees = 0;
let totalPages = 0;

async function loadEmployees(page = 1) {
    try {
        showLoader(true);
        currentPage = page;
        const skip = (page - 1) * itemsPerPage;
        
        const response = await fetch(`/api/employees/list?skip=${skip}&limit=${itemsPerPage}`);
        const data = await response.json();
        
        employees = data.employees || [];
        totalEmployees = data.pagination.total;
        totalPages = data.pagination.pages;
        
        render(employees);
        renderPagination();
        showLoader(false);
    } catch (e) {
        console.error('Error loading employees:', e);
        alert('Failed to load employees');
        showLoader(false);
    }
}

function showLoader(show) {
    const loader = document.getElementById('loader');
    if (loader) {
        loader.style.display = show ? 'flex' : 'none';
    }
}


function render(list) {
    const grid = document.getElementById('employee-grid');

    if (list.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">👥</div>
                <p>No employees found</p>
                <p style="margin-top: 1rem; font-size: 0.875rem;">Click "Add Employee" to register new employees</p>
            </div>
        `;
        document.getElementById('pagination').innerHTML = '';
        return;
    }

    grid.innerHTML = list.map(e => {
        const qualityPercent = (e.avg_quality * 100).toFixed(0);
        const faceStatus = e.face_count >= 6 ? '✓ Complete' : '⚠ Incomplete';
        const statusClass = e.face_count >= 6 ? 'status-complete' : 'status-incomplete';
        const qualityWidth = Math.min(qualityPercent, 100);

        return `
            <div class="employee-card">
                <div class="employee-card-top">
                    <div class="employee-avatar">👤</div>
                    <div class="employee-name">${e.name}</div>
                    <div class="status-badge ${statusClass}">
                        ${faceStatus}
                    </div>
                </div>

                <div class="employee-card-body">
                    <div class="card-row">
                        <span class="card-label">ID:</span>
                        <span class="card-value">${e.emp_id}</span>
                    </div>

                    <div class="card-row">
                        <span class="card-label">Department:</span>
                        <span class="card-value">${e.department || 'N/A'}</span>
                    </div>

                    <div class="card-row">
                        <span class="card-label">Position:</span>
                        <span class="card-value">${e.position || 'N/A'}</span>
                    </div>

                    <div class="card-row">
                        <span class="card-label">Face Images:</span>
                        <span class="face-badge">${e.face_count} / 8</span>
                    </div>

                    <div class="quality-section">
                        <div class="quality-header">
                            <span class="quality-label">Quality</span>
                            <span class="quality-percent">${qualityPercent}%</span>
                        </div>
                        <div class="quality-bar">
                            <div class="quality-bar-fill" style="width: ${qualityWidth}%"></div>
                        </div>
                    </div>
                </div>

                <div class="employee-card-footer">
                    <button class="btn btn-primary" onclick='editEmp(${JSON.stringify(e).replace(/'/g, "&#39;")})'>✏️ Edit</button>
                    <button class="btn btn-danger" onclick="deleteEmp('${e.emp_id}', '${e.name.replace(/'/g, "\\'")}')">🗑️ Delete</button>
                </div>
            </div>
        `;
    }).join('');

    // Render pagination after rendering grid
    renderPagination();
}

function renderPagination() {
    const paginationContainer = document.getElementById('pagination');
    if (!paginationContainer) return;

    let html = '';
    
    if (totalPages > 1) {
        html += '<div class="pagination">';
        
        // Previous button
        if (currentPage > 1) {
            html += `<button class="pagination-btn" onclick="loadEmployees(${currentPage - 1})">← Previous</button>`;
        } else {
            html += `<button class="pagination-btn" disabled>← Previous</button>`;
        }

        // Page numbers
        let startPage = Math.max(1, currentPage - 2);
        let endPage = Math.min(totalPages, currentPage + 2);

        if (startPage > 1) {
            html += `<button class="pagination-btn" onclick="loadEmployees(1)">1</button>`;
            if (startPage > 2) {
                html += `<span class="pagination-dots">...</span>`;
            }
        }

        for (let i = startPage; i <= endPage; i++) {
            if (i === currentPage) {
                html += `<button class="pagination-btn active">${i}</button>`;
            } else {
                html += `<button class="pagination-btn" onclick="loadEmployees(${i})">${i}</button>`;
            }
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                html += `<span class="pagination-dots">...</span>`;
            }
            html += `<button class="pagination-btn" onclick="loadEmployees(${totalPages})">${totalPages}</button>`;
        }

        // Next button
        if (currentPage < totalPages) {
            html += `<button class="pagination-btn" onclick="loadEmployees(${currentPage + 1})">Next →</button>`;
        } else {
            html += `<button class="pagination-btn" disabled>Next →</button>`;
        }

        html += '</div>';
        html += `<div class="pagination-info">Showing ${(currentPage - 1) * itemsPerPage + 1} - ${Math.min(currentPage * itemsPerPage, totalEmployees)} of ${totalEmployees} employees</div>`;
    }

    paginationContainer.innerHTML = html;
}
function filter() {
    const search = document.getElementById('search').value.toLowerCase();
    const filtered = employees.filter(e =>
        e.name.toLowerCase().includes(search) ||
        e.emp_id.toLowerCase().includes(search) ||
        (e.department && e.department.toLowerCase().includes(search))
    );
    
    // Show filtered results without pagination
    const grid = document.getElementById('employee-grid');
    if (filtered.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <p>No employees found matching your search</p>
            </div>
        `;
        document.getElementById('pagination').innerHTML = '';
    } else {
        render(filtered);
        document.getElementById('pagination').innerHTML = '';
    }
}


function editEmp(emp) {
    document.getElementById('edit-emp-id').value = emp.emp_id || '';
    document.getElementById('edit-name').value = emp.name || '';
    document.getElementById('edit-department').value = emp.department || '';
    document.getElementById('edit-position').value = emp.position || '';
    
    // Show modal
    document.getElementById('edit-modal').style.display = 'block';
}

async function saveEdit() {
    // Get all form values
    const empId = document.getElementById('edit-emp-id').value.trim();
    const name = document.getElementById('edit-name').value.trim();
    const department = document.getElementById('edit-department').value.trim();
    const position = document.getElementById('edit-position').value.trim();

    // Validate required field
    if (!name) {
        alert('Name is required');
        return;
    }

    try {
        showLoader(true);
        
        // Send PUT request with all 3 fields
        const response = await fetch(`/api/employee/${empId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                department: department,
                position: position
            })
        });

        const result = await response.json();
        showLoader(false);

        if (result.success) {
            alert('Employee updated successfully');
            closeModal();
            loadEmployees(currentPage);
        } else {
            alert('Update failed: ' + (result.message || 'Unknown error'));
        }
    } catch (e) {
        showLoader(false);
        console.error('Error updating employee:', e);
        alert('Failed to update employee: ' + e.message);
    }
}

function closeModal() {
    document.getElementById('edit-modal').style.display = 'none';
}
async function deleteEmp(empId, empName) {
    if (confirm(`Delete ${empName} (${empId})?\n\nThis will remove all face data and attendance records!`)) {
        try {
            const response = await fetch(`/api/employee/${empId}`, {method: 'DELETE'});
            const result = await response.json();

            if (result.success) {
                loadEmployees(currentPage);
            } else {
                alert('Delete failed: ' + result.message);
            }
        } catch (e) {
            console.error('Error deleting employee:', e);
            alert('Failed to delete employee');
        }
    }
}

window.onclick = (e) => {
    const modal = document.getElementById('edit-modal');
    if (e.target === modal) {
        closeModal();
    }
};

window.onload = () => loadEmployees(1);
