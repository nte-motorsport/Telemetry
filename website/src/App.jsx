import { IconChartLine, IconDownload, IconHistory, IconUsers } from '@tabler/icons-react';
import { LINKS } from './links.js';
import RaceSim from './RaceSim.jsx';
import { formatDate, formatSize, useLatestRelease } from './useLatestRelease.js';

// The app's pages (see the Telemetry README), each as a card.
const FEATURES = [
  {
    key: 'live',
    name: 'Live',
    description:
      'Your car as you drive: speed, G-forces, yaw rate, slope, altitude and heading, with the last minute on charts.',
    Icon: IconChartLine,
  },
  {
    key: 'multiplayer',
    name: 'Multiplayer',
    description: 'An online race as it goes: every car on one map, the timing, the gaps and everyone’s sector times.',
    Icon: IconUsers,
  },
  {
    key: 'replays',
    name: 'Replays',
    description: 'Online races are recorded on their own. Watch them again on the map, scrub the timeline, compare sectors.',
    Icon: IconHistory,
  },
];

function DownloadPanel() {
  const release = useLatestRelease();

  return (
    <section className="download" aria-label="Download">
      <a className="btn btn-primary" href={release ? release.url : LINKS.latestRelease}>
        <IconDownload className="icon" size={24} stroke={2} aria-hidden="true" />
        <span className="btn-label">Download for Windows</span>
      </a>
      <p className="muted-text download-meta">
        The program never interferes with the game process or its memory. It simply monitors network traffic from the sidelines.
      </p>
    </section>
  );
}

function FeatureCard({ feature: { name, description, Icon } }) {
  return (
    <div className="panel feature-card">
      <Icon className="icon feature-icon" size={32} stroke={1.5} aria-hidden="true" />
      <div className="feature-text">
        <p className="section-title">{name}</p>
        <p className="muted-text">{description}</p>
      </div>
    </div>
  );
}

export default function App() {
  // A lap of a race as the app shows it on the left; on the right the logo and name, the download and what the
  // app does.
  return (
    <main className="landing">
      <div className="showcase">
        <header className="intro">
          <img className="hero-logo" src="/assets/ui/logo-mark.png" alt="" />
          <h1 className="site-title">NTE Telemetry</h1>
          <p className="muted-text hero-text">
            Your car’s live telemetry
            for{' '}
            <a className="text-link" href={LINKS.game} target="_blank" rel="noreferrer">
              Neverness to Everness
            </a>
            .
          </p>
          <DownloadPanel />
        </header>

        <RaceSim />

        <div className="features">
          {FEATURES.map((feature) => (
            <FeatureCard key={feature.key} feature={feature} />
          ))}
        </div>
      </div>
    </main>
  );
}
