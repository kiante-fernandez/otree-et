let videoStream = null;

function cleanup() {
  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
  }
}

async function testCamera() {
  const statusDiv = docQuerySelectorStrict('#camera-status');
  const videoElement = docQuerySelectorStrict('#camera-preview');
  const nextSection = docQuerySelectorStrict('#next-section');
  const testBtn = docQuerySelectorStrict('#test-camera-btn');

  try {
    statusDiv.textContent = 'Requesting camera access...';
    videoStream = await navigator.mediaDevices.getUserMedia({ video: true });

    videoElement.srcObject = videoStream;
    videoElement.classList.remove('hidden');
    statusDiv.innerHTML = '<span class="text-success">Camera access granted!</span>';
    testBtn.classList.add('hidden');

    sessionStorage.setItem('eyetrack_consent', 'true');
    // BooleanField expects '1' / '0' from a hidden input.
    const consentInput = document.getElementById('eyetrack_consent');
    if (consentInput) {
      consentInput.value = '1';
    }
    nextSection.classList.remove('hidden');
  } catch (error) {
    statusDiv.innerHTML = '<span class="text-danger">Camera access denied. Please grant camera permission to continue.</span>';
    console.error('Camera error:', error);
  }
}

docQuerySelectorStrict('#test-camera-btn').addEventListener('click', testCamera);
window.addEventListener('beforeunload', cleanup);
