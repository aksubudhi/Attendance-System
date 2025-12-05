const capturedAngles = new Set()
let stream = null
let currentEmployee = null

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("step1").classList.add("active")
})

function nextStep() {
  const nameInput = document.getElementById("name")
  const empIdInput = document.getElementById("emp-id")
  const departmentInput = document.getElementById("department")

  if (!nameInput || !empIdInput || !departmentInput) {
    console.error("[v0] Form elements not found in DOM")
    alert("Error: Form elements not found. Please refresh the page.")
    return
  }

  const name = nameInput.value.trim()
  const empId = empIdInput.value.trim()
  const department = departmentInput.value

  console.log("[v0] Form validation - Name:", name, "EmpId:", empId, "Department:", department)

  if (!name || !empId || !department) {
    showStatus("Please fill in all required fields (Name, Employee ID, and Department)", "error")
    return
  }

  const positionInput = document.getElementById("position")
  const position = positionInput ? positionInput.value.trim() : ""

  currentEmployee = {
    name,
    emp_id: empId,
    department,
    position,
  }

  createEmployee(currentEmployee)
}

async function createEmployee(employeeData) {
  try {
    showStatus("Creating employee record...", "info")

    const response = await fetch("/api/create-employee", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(employeeData),
    })

    const result = await response.json()

    if (result.success) {
      showStatus("Employee created! Ready for face capture", "success")
      setTimeout(() => {
        document.getElementById("step1").classList.remove("active")
        document.getElementById("step2").classList.add("active")
      }, 1000)
    } else {
      showStatus(result.message || "Failed to create employee", "error")
    }
  } catch (error) {
    console.error("Error creating employee:", error)
    showStatus("Error creating employee", "error")
  }
}

function prevStep() {
  document.getElementById("step2").classList.remove("active")
  document.getElementById("step1").classList.add("active")
  stopCamera()
}

function goBack() {
  if (confirm("Are you sure? Your data will not be saved.")) {
    window.location.href = "/employees"
  }
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
    })
    const video = document.getElementById("video")
    video.srcObject = stream
    document.getElementById("start-camera-btn").textContent = "📷 Camera Active"
    document.getElementById("start-camera-btn").disabled = true
    showStatus("Camera started! Capture different face angles", "success")
  } catch (err) {
    showStatus("Camera access denied: " + err.message, "error")
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
    stream = null
  }
}

async function captureAngle(angle) {
  const video = document.getElementById("video")
  const canvas = document.getElementById("canvas")

  if (!video.srcObject) {
    showStatus("Please start the camera first", "error")
    return
  }

  const ctx = canvas.getContext("2d")
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  ctx.drawImage(video, 0, 0)

  canvas.toBlob(
    async (blob) => {
      const formData = new FormData()
      formData.append("image", blob, "face.jpg")
      formData.append("angle", angle)
      formData.append("emp_id", currentEmployee.emp_id)

      try {
        showStatus(`Capturing ${angle}...`, "info")

        const response = await fetch("/api/capture-face", {
          method: "POST",
          body: formData,
        })

        const result = await response.json()

        if (result.success) {
          const card = document.querySelector(`[data-angle="${angle}"]`)
          card.classList.add("captured")

          if (!capturedAngles.has(angle)) {
            capturedAngles.add(angle)
          }

          updateProgress()

          const quality = Math.round((result.quality || 0) * 100)
          showQualityNotification(`${angle} captured!`, `Quality: ${quality}%`)
          showStatus(`${angle} captured! Quality: ${quality}%`, "success")

          if (capturedAngles.size >= 6) {
            document.getElementById("complete-btn").disabled = false
          }
        } else {
          showStatus(`Failed to capture ${angle}: ${result.message}`, "error")
        }
      } catch (error) {
        console.error("Error capturing angle:", error)
        showStatus(`Error capturing ${angle}`, "error")
      }
    },
    "image/jpeg",
    0.95,
  )
}

function updateProgress() {
  const total = 8
  const captured = capturedAngles.size
  const percentage = (captured / total) * 100

  const progressBar = document.getElementById("progress-bar")
  progressBar.style.width = percentage + "%"

  if (captured >= 6) {
    progressBar.style.background = "#10b981"
  } else {
    progressBar.style.background = "#2563eb"
  }

  document.getElementById("progress-text").textContent = `${captured}/${total} angles captured (min 6 required)`
}

function showQualityNotification(title, message) {
  const notification = document.getElementById("quality-notification")
  notification.innerHTML = `<strong>${title}</strong><br>${message}`
  notification.classList.add("show")

  setTimeout(() => {
    notification.classList.remove("show")
  }, 3000)
}

function showStatus(message, type) {
  const statusDiv = document.getElementById("status-message")
  statusDiv.textContent = message
  statusDiv.className = `status-message show ${type}`

  setTimeout(() => {
    statusDiv.classList.remove("show")
  }, 3000)
}

async function completeRegistration() {
  if (capturedAngles.size < 6) {
    showStatus("Please capture at least 6 angles", "error")
    return
  }

  try {
    showStatus("Finalizing registration...", "info")

    const response = await fetch("/api/finalize-registration", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        emp_id: currentEmployee.emp_id,
        captured_angles: Array.from(capturedAngles),
      }),
    })

    const result = await response.json()

    if (result.success) {
      stopCamera()
      showStatus("Registration completed successfully!", "success")

      setTimeout(() => {
        window.location.href = "/employees"
      }, 1500)
    } else {
      showStatus(result.message || "Failed to finalize registration", "error")
    }
  } catch (error) {
    console.error("Error finalizing registration:", error)
    showStatus("Error finalizing registration", "error")
  }
}

window.onbeforeunload = () => {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
  }
}

