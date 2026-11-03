# Telemetry

NTE Motorsport telemetry app for Neverness to Everness: speed, G-forces, trajectory and altitude.

The data is decoded from the game's own UDP traffic, read passively from the network. The game process is never
touched, so the Anti-Cheat Expert driver has nothing to see. No Wireshark or Npcap is needed: the app uses a Windows
raw socket, which requires administrator rights.

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

## Maps

The game's map can lie under the tracks on the Live, Multiplayer and Replays pages. Maps are plug-ins, not part
of the app: map packs (`.ntemap`) in `%APPDATA%\NTE Telemetry\maps`, installed from Settings > Maps or copied
there by hand. Each pack says which game world it is the map of; the app reads the world from the game's
traffic and shows that world's map, if a pack for it is installed.

Making a pack from the game's map tiles (PNG, numbered left to right, top to bottom) in a folder:

1. Write `map.json` in the folder: `{"level": "/Game/Maps/...", "title": "...", "grid": [columns, rows], "tile": 512,
   "road_min": 45}`. The level is the world's, as the status bar shows its last part while you drive there.
2. Place the map in the world against a replay recorded there:
   `.venv\Scripts\python tools\align_map.py <folder> "%APPDATA%\NTE Telemetry\replays\<replay>.json.gz"`
   (right drag moves the drive, Ctrl + wheel scales it, S saves).
3. Build the pack into the maps folder: `.venv\Scripts\python tools\build_map.py <folder>`
