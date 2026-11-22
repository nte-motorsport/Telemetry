# Website

The NTE Telemetry download page: one page in the design of the NTE Motorsport sites
(Site, Wiki, Rivals) with the app's yellow accent. Vite + React, like them.

The download button points at the `.msi` of the newest GitHub release, looked up in the
browser through the GitHub API on every visit — a new release shows up without a deploy.
If GitHub can't be reached, it links to the latest release's page instead. All outside
addresses are in `src/links.js`.

Under it, a lap of a race as the app's Replays page shows it: the map and the speed chart,
cross-fading every 10 s, and each car's speed. It is a real lap: `tools/make_lap.py` takes
one lap of every car from a recorded replay (its sectors tell where the lap starts and
ends), stretches them to one shared period so the loop closes, and draws the game map
under it from the installed map pack. Run it with the app's venv, from the Telemetry
folder:

```sh
.venv\Scripts\python website\tools\make_lap.py "%APPDATA%\NTE Telemetry\replays\<replay>.json.gz" [lap] [--spread s] [--you <replay>]
```

The rivals are pulled apart so they don't run in one bunch: each starts the loop `--spread`
seconds (10 by default) further back than the one that crossed the line before it.
`--you` takes the player's lap from another replay of the same track: the fastest full lap
there, from the finish line to the finish line.

It writes `src/lap.json` and `public/assets/ui/lap-map.webp`. The one on the site is lap 2
of the game's three bots in the Sunset Neon race of 2026-11-21 10:06, with the player's
cleanest lap on that track, from the race of 2026-11-15 10:29 (`--you`); the player shows
as "You".

The logo and background are copies of `../src/assets/logo.png` and `background.png`;
copy them again if those change.

## Development

```sh
npm install
npm run dev
```

## Deploy

Firebase Hosting, project `ntemotorsport`, site `ntemotorsport-telemetry`
(https://ntemotorsport-telemetry.web.app).

```sh
npm run deploy
```

On GitHub, `.github/workflows/website.yml` deploys it on every push to `main` that
changes `website/`; it needs the `FIREBASE_SERVICE_ACCOUNT` secret.
