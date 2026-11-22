import { memo, useEffect, useMemo, useState } from 'react';
import { IconEye } from '@tabler/icons-react';
import LAP from './lap.json';

// A race lap, looped, as the app's Replays page shows it: the map with every car and its trail, and the speed
// chart with the timeline's cursor, one after the other, the cars' speeds under them. The lap is real
// (tools/make_lap.py makes lap.json from a recorded replay), each car's stretched to one shared period.

const SWITCH_MS = 10000; // each chart is shown this long
const TRAIL_S = 20; // seconds of trail behind each car on the map
const [VIEW_W, VIEW_H] = LAP.view; // the map's plot area, px; the speed chart's is the same size
const AXIS_W = 40; // the speed chart's left axis (its plot area is that much narrower)
const AXIS_H = 24; // under both: the time axis, the map's scale bar
const GRID = '#2e2e2e';
const MUTED = '#999';
const N = LAP.cars[0].speed.length; // samples per lap, the same for every car

function clock(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function niceStep(span, n) {
  const raw = span / n;
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
}

// The map's name for a racer, as the app's "three letters, as in races".
function shortName(name) {
  return (name.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 3) || name.slice(0, 3)).toUpperCase();
}

const CARS = LAP.cars.map((car) => ({
  ...car,
  you: car.name === 'You',
  label: shortName(car.name),
  // the sample the car is at when the loop starts: it crosses the line `offset` s after the first car
  shift: Math.round(car.offset * LAP.rate),
}));

// The car's sample index (fractional) at loop time t.
function at(car, t) {
  return (((t * LAP.rate - car.shift) % N) + N) % N;
}

function lerp(values, i) {
  const a = Math.floor(i);
  const b = (a + 1) % N;
  return values[a] + (values[b] - values[a]) * (i - a);
}

// ---------- The map ----------

const SCALE_M = niceStep(VIEW_W * LAP.metresPerPx * 0.8, 4); // the scale bar's length, m, as the app picks it

function trail(car, i) {
  const back = TRAIL_S * LAP.rate;
  const points = [];
  for (let k = Math.ceil(i - back); k <= Math.floor(i); k += 1) {
    const j = ((k % N) + N) % N;
    points.push(`${car.x[j]},${car.y[j]}`);
  }
  points.push(`${lerp(car.x, i)},${lerp(car.y, i)}`);
  return points.join(' ');
}

function MapChart({ t }) {
  // the player last, so their trail and marker are on top
  const cars = [...CARS].sort((a, b) => a.you - b.you);
  const where = cars.map((car) => [car, at(car, t)]);

  return (
    <div className="chart">
      <div className="plot" style={{ aspectRatio: `${VIEW_W} / ${VIEW_H}` }}>
        <img className="plot-map" src="/assets/ui/lap-map.webp" alt="" />
        <svg className="plot-svg" viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} aria-hidden="true">
          {where.map(([car, i]) => (
            <polyline
              key={car.name}
              points={trail(car, i)}
              fill="none"
              stroke={car.color}
              strokeWidth={car.you ? 3 : 2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {where.map(([car, i]) => {
            const x = lerp(car.x, i);
            const y = lerp(car.y, i);
            const w = car.label.length * 8 + 6;
            return (
              <g key={car.name}>
                <circle cx={x} cy={y} r="6" fill={car.color} stroke="#060607" strokeWidth="2" />
                <g transform={`translate(${Math.min(Math.max(x, w / 2 + 2), VIEW_W - w / 2 - 2)} ${y - 12})`}>
                  <rect x={-w / 2} y="-17" width={w} height="16" fill="rgba(10, 11, 13, 0.82)" stroke={car.color} strokeWidth="1.5" />
                  <text className="map-label" x="0" y="-5" textAnchor="middle">
                    {car.label}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="scale" aria-hidden="true">
        <span className="scale-bar" style={{ width: `${(SCALE_M / LAP.metresPerPx / VIEW_W) * 100}%` }} />
        <span>{SCALE_M >= 1000 ? `${SCALE_M / 1000} km` : `${SCALE_M} m`}</span>
      </div>
    </div>
  );
}

// ---------- The speed chart ----------

const PLOT_W = VIEW_W - AXIS_W;
const V_MAX = Math.max(...CARS.flatMap((car) => car.speed)) * 1.08;
const V_STEP = niceStep(V_MAX, 5);
const T_STEP = niceStep(LAP.period, 6);

function sx(t) {
  return AXIS_W + (t / LAP.period) * PLOT_W;
}

function sy(v) {
  return VIEW_H - (v / V_MAX) * VIEW_H;
}

function ticks(max, step) {
  const out = [];
  for (let v = step; v < max; v += step) out.push(v);
  return out;
}

// Everything but the cursor: drawn once.
const SpeedLines = memo(function SpeedLines() {
  const cars = [...CARS].sort((a, b) => a.you - b.you);
  return (
    <>
      {ticks(V_MAX, V_STEP / 5).map((v) => (
        <line key={`v${v}`} x1={AXIS_W} x2={VIEW_W} y1={sy(v)} y2={sy(v)} stroke={GRID} strokeOpacity="0.4" />
      ))}
      {ticks(LAP.period, T_STEP / 5).map((t) => (
        <line key={`t${t}`} x1={sx(t)} x2={sx(t)} y1="0" y2={VIEW_H} stroke={GRID} strokeOpacity="0.4" />
      ))}
      {ticks(V_MAX, V_STEP).map((v) => (
        <g key={`V${v}`}>
          <line x1={AXIS_W} x2={VIEW_W} y1={sy(v)} y2={sy(v)} stroke={GRID} />
          <text className="tick" x={AXIS_W - 6} y={sy(v) + 4} textAnchor="end">
            {v}
          </text>
        </g>
      ))}
      <text className="tick" x={AXIS_W - 6} y={VIEW_H} textAnchor="end">
        0
      </text>
      {ticks(LAP.period, T_STEP).map((t) => (
        <g key={`T${t}`}>
          <line x1={sx(t)} x2={sx(t)} y1="0" y2={VIEW_H} stroke={GRID} />
          <text className="tick" x={sx(t)} y={VIEW_H + 18} textAnchor="middle">
            {clock(t)}
          </text>
        </g>
      ))}
      {cars.map((car) => {
        // the car's speed over the loop's time, starting where it is when the loop starts
        const points = [];
        for (let k = 0; k <= N; k += 1) {
          const v = car.speed[(((k - car.shift) % N) + N) % N];
          points.push(`${sx((k / N) * LAP.period).toFixed(1)},${sy(v).toFixed(1)}`);
        }
        return (
          <polyline
            key={car.name}
            points={points.join(' ')}
            fill="none"
            stroke={car.color}
            strokeWidth={car.you ? 2 : 1.6}
            strokeLinejoin="round"
          />
        );
      })}
      <rect x={AXIS_W + 0.5} y="0.5" width={PLOT_W - 1} height={VIEW_H - 1} fill="none" stroke={GRID} />
    </>
  );
});

function SpeedChart({ t }) {
  const x = sx(t);
  return (
    <div className="chart">
      <svg className="plot-svg speed-svg" viewBox={`0 0 ${VIEW_W} ${VIEW_H + AXIS_H}`} aria-hidden="true">
        <SpeedLines />
        <line x1={x} x2={x} y1="0" y2={VIEW_H} stroke="#fff" strokeOpacity="0.6" strokeDasharray="4 3" />
      </svg>
    </div>
  );
}

// ---------- The simulation ----------

function useLoopTime() {
  const [t, setT] = useState(0);

  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setT(LAP.period * 0.4); // a still moment of the lap, not a moving one
      return undefined;
    }
    let frame;
    const start = performance.now();
    const tick = (now) => {
      setT((((now - start) / 1000) % LAP.period + LAP.period) % LAP.period);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  return t;
}

function useView() {
  const [view, setView] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setView((v) => 1 - v), SWITCH_MS);
    return () => clearInterval(timer);
  }, []);
  return view;
}

function CarChip({ car, t }) {
  const v = Math.round(lerp(car.speed, at(car, t)));
  return (
    <div className="chip">
      <span className="chip-eye" style={{ borderColor: car.color }}>
        <IconEye size={20} stroke={2} color={car.color} aria-hidden="true" />
      </span>
      <span className="chip-text">
        <span className="chip-name">{car.name}</span>
        <span className="chip-value">
          {v}
          <span className="chip-unit"> km/h</span>
        </span>
      </span>
    </div>
  );
}

export default function RaceSim() {
  const t = useLoopTime();
  const view = useView();

  return (
    <section className="sim" aria-label="A lap of a race, as the app shows it">
      <div className="panel sim-panel">
        <div className={view === 0 ? 'sim-pane sim-pane-shown' : 'sim-pane'}>
          <p className="section-title">Map</p>
          <MapChart t={t} />
        </div>
        <div className={view === 1 ? 'sim-pane sim-pane-shown' : 'sim-pane'}>
          <p className="section-title">Speed</p>
          <SpeedChart t={t} />
        </div>
      </div>
      <div className="chips">
        {CARS.map((car) => (
          <CarChip key={car.name} car={car} t={t} />
        ))}
      </div>
    </section>
  );
}
