import { useEffect, useState } from 'react';
import { LINKS } from './links.js';

// The installer of the newest GitHub release (published by .github/workflows/release.yml
// as "NTE Telemetry-<version>.msi"). Looked up on every visit, so a new release shows up
// here without rebuilding the site. Null until it's known, or if GitHub can't be reached
// — the page then links to the release page instead.
export function useLatestRelease() {
  const [release, setRelease] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    fetch(LINKS.latestReleaseApi, {
      headers: { Accept: 'application/vnd.github+json' },
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((data) => {
        const installer = data.assets?.find((asset) => asset.name.toLowerCase().endsWith('.msi'));
        if (!installer) return;

        setRelease({
          version: data.tag_name.replace(/^v/, ''),
          date: data.published_at ? new Date(data.published_at) : null,
          url: installer.browser_download_url,
          size: installer.size,
          page: data.html_url,
        });
      })
      .catch(() => {});

    return () => controller.abort();
  }, []);

  return release;
}

export function formatSize(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(0)} MB`;
}

export function formatDate(date) {
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}
