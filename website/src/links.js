// Every outside address the site links to, in one place.
export const REPO = 'nte-motorsport/Telemetry';

export const LINKS = {
  releases: `https://github.com/${REPO}/releases`,
  // Always the newest release's page: the download falls back to it while (or if) the
  // installer's own address can't be looked up.
  latestRelease: `https://github.com/${REPO}/releases/latest`,
  latestReleaseApi: `https://api.github.com/repos/${REPO}/releases/latest`,
  game: 'https://nte.perfectworld.com/',
};
