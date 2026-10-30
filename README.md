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
