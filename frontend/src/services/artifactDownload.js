import { apiClient } from './apiClient';

// Artifact routes require the Authorization header, which a plain navigation
// (<a href>) cannot send. Fetch through the authenticated client and save the
// returned blob instead.
export async function downloadArtifact(url, filename = 'artifact') {
  const response = await apiClient.get(url, { responseType: 'blob' });
  const objectUrl = URL.createObjectURL(response.data);
  try {
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  }
}
