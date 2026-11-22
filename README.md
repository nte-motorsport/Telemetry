# Telemetry

NTE Motorsport telemetry app for Neverness to Everness: your car's telemetry while you drive, everyone in an online
race live, and recorded races to watch again.

The data is decoded from the game's own UDP traffic, read passively from the network. The game process is never
touched, so the Anti-Cheat Expert driver has nothing to see. No Wireshark or Npcap is needed: the app uses a Windows
raw socket, which requires administrator rights.

## Pages

- **Live**: your car as you drive: speed, longitudinal and lateral G, yaw rate, slope, altitude, heading, odometer
  and top speed, and the last minute on charts (speed, G-forces, trajectory, G-G diagram, altitude, yaw rate).
- **Multiplayer**: an online race as it goes: every car on one map and everyone's speed over the last minute, the
  racers with their cars and ranks, the timing (places and gaps) and each racer's sector times.
- **Replays**: online races, recorded on their own from start to finish. Each one on a map and a speed chart with a
  timeline to play or scrub, everyone's speed at that moment, the result and the sectors.
- **Settings**:
  - *Display*: which Live charts are shown and in what order; on Multiplayer and Replays, which side the panels'
    column is on, which panels are shown and in what order, and the order of the map and speed charts; the unit of
    speed (km/h, m/s, mph, knots, Mach); how racers are named on the map, and their trails.
  - *Network*: the network interface the game's traffic is read from.
  - *Recording*: recording online races, and optionally each race's raw network traffic (a `.pcap.gz` that
    Wireshark opens; it holds everything the computer sent and received during the race, so don't share it).
  - *Plugins*: map packs (see [Maps](#maps)).
  - *Account*: your name in the game and account ID. Not set by hand: the game sends them when it connects, and
    the app uses them to tell your car from the others'.

Settings, replays and map packs are kept in `%APPDATA%\NTE Telemetry`.

## Run

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python src\app.py
```

Run it from an administrator terminal, or use the "Relaunch as administrator" button in the app.

## Build

```
.venv\Scripts\python build.py
```

Produces `dist\NTE Telemetry.exe`: a single file that asks for administrator rights on start.

Installer (needs the [WiX Toolset](https://wixtoolset.org) v4 or later and its UI extension:
`wix extension add -g WixToolset.UI.wixext`):

```
.venv\Scripts\python build_msi.py [version]
```

Builds the exe, then `dist\NTE Telemetry-<version>.msi`: installs it to Program Files with Start menu and desktop
shortcuts. The version is the app's own, `VERSION` in `src/version.py`, unless one is given.

## Release

Change `VERSION` in `src/version.py` (to a higher one: an installer replaces only older versions) and push it to
`main`. The [Release workflow](.github/workflows/release.yml) then builds the installer on GitHub and publishes it as
release `v<version>`, with notes made from the commits since the last one. A version that already has its release
is not built again; to retry a failed build, run the workflow by hand from the Actions tab.

## Maps

The game's map can lie under the tracks on the Live, Multiplayer and Replays pages. Maps are plug-ins, not part
of the app: map packs (`.ntemap`) in `%APPDATA%\NTE Telemetry\maps`, installed from Settings > Plugins or copied
there by hand. Each pack says which game world it is the map of; the app reads the world from the game's
traffic and shows that world's map, if a pack for it is installed.

Making a pack from the game's map tiles (PNG, numbered left to right, top to bottom) in a folder:

1. Write `map.json` in the folder:
   `{"level": ["/Game/Maps/...", ...], "title": "...", "grid": [columns, rows], "tile": 512, "road_min": 45,
   "centre": [x, y], "edge": side}`. The levels are the worlds the map is for, as the status bar shows their
   last part while you drive there (a track's race level and its test drive copy can share a map). Centre and
   edge are where the game itself puts the map: its `DT_LevelMiniMap` table has them for each level, as
   `MiniMapCenterLocation` and `MiniMapEdgeSize`, in centimetres there and in metres here.
2. Without centre and edge, place the map by hand against a replay recorded there:
   `.venv\Scripts\python tools\align_map.py <folder> "%APPDATA%\NTE Telemetry\replays\<replay>.json.gz"`
   (right drag moves the drive, Ctrl + wheel scales it, S saves).
3. Build the pack into the maps folder: `.venv\Scripts\python tools\build_map.py <folder>`

## When a game update breaks it

If the app stops reading the game after an update, record the raw traffic of a race to look into what changed:

```
.venv\Scripts\python tools\record_traffic.py [seconds] [out.pcap.gz]
```

Run it from an administrator terminal, then race (Ctrl+C stops it early). Without `out` the file goes to
`%APPDATA%\NTE Telemetry\replays` as `capture_<date>_<time>.pcap.gz`. Like the raw traffic of a race, it holds
everything the computer's network connection carried meanwhile.
