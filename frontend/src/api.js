const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, options);
  } catch {
    throw new Error('Could not reach the ECOVISSION backend. Make sure FastAPI is running at http://127.0.0.1:8000.');
  }

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null
      ? payload.detail || payload.message
      : payload;
    throw new Error(detail || `Backend request failed (${response.status}).`);
  }
  return payload;
}

export function analyzeSingleImage(file) {
  const form = new FormData();
  form.append('file', file);
  return request('/api/analyze/single', { method: 'POST', body: form });
}

export function analyzeImageComparison({
  earlierFile,
  laterFile,
  monitoringArea = 'Unspecified area',
  earlierLabel = 'Earlier',
  laterLabel = 'Later',
  sensitivity = 35,
}) {
  const form = new FormData();
  form.append('earlier_file', earlierFile);
  form.append('later_file', laterFile);
  form.append('monitoring_area', monitoringArea);
  form.append('earlier_label', earlierLabel);
  form.append('later_label', laterLabel);
  form.append('sensitivity', String(sensitivity));
  return request('/api/analyze/compare', { method: 'POST', body: form });
}

export function getBackendHealth() {
  return request('/api/health');
}

export function getAnalysisHistory(limit = 50) {
  return request(`/api/analyses?limit=${encodeURIComponent(limit)}`);
}
