# Copilot Instructions for PlasmaMirrors GUI

## Overview
This project is a PyQt6-based GUI for controlling Zaber motorized stages and related hardware in a plasma mirror experimental setup. The codebase is modular, with clear separation between device I/O, UI panels, and shared widgets.

## Architecture & Key Components
- **Entry Point:** `main.py` launches the PyQt6 application and loads `MainWindow`.
- **Main Window:** `main_window.py` orchestrates the UI, instantiates panels, and manages motor info. It wires up signals/slots for device I/O and UI updates.
- **Panels:** All UI panels are in `panels/` (e.g., `motor_status_panel.py`, `stage_control_panel.py`, `PM_panel.py`). Each panel is a QWidget subclass, often composed of custom widgets.
- **Device I/O:** Hardware communication is in `device_io/` (e.g., `zaber_stage_io.py`). Device classes emit Qt signals for status, errors, and data updates.
- **Widgets:** Reusable UI elements (e.g., `motor_row.py`, `round_light.py`) are in `widgets/`.
- **Motor Metadata:** `MotorInfo.py` defines the `MotorInfo` dataclass, used throughout for motor configuration.
- **Imports Helper:** `imports.py` provides flexible import logic for interactive and script-based use.

## Developer Workflows
- **Run the GUI:**
  ```sh
  python PlasmaMirrors/main.py
  ```
- **Device Emulation:** If hardware is unavailable, comment out device I/O in `main_window.py` and use simulated data.
- **Panel Development:** Add new panels as QWidget subclasses in `panels/` and register them in `main_window.py`.
- **Motor Definitions:** Update the `motors` list in `MainWindow` for new/changed hardware.

## Patterns & Conventions
- **Signals/Slots:** All cross-thread/device communication uses Qt signals (see `ZaberStageIO`, `MainWindow`).
- **UI Layout:** Main window uses a 2x3 grid layout for panel placement. Panels are responsible for their own internal layout.
- **Styling:** Custom widgets (e.g., `RoundLight`, `MotorRow`) use inline stylesheets for appearance.
- **Imports:** Use `from ... import ...` for intra-project imports. Use the `imports.py` pattern for interactive work.
- **No Central Settings File:** Hardware ports, baud rates, etc., are hardcoded in `main_window.py` and device I/O files.

## External Dependencies
- **PyQt6** for GUI
- **zaber_motion** for Zaber device control
- **Thorlabs Kinesis** and **nidaqmx** (see `ELMIL_NI_KSC101_bridge.py`) for additional hardware

## Examples
- **Adding a new motor:**
  - Update the `motors` list in `MainWindow` (`main_window.py`).
  - Add any new UI elements to the relevant panel in `panels/`.
- **Handling device errors:**
  - Connect to the `error` signal in device I/O classes and display/log in the UI.

## References
- `main.py`, `main_window.py`, `device_io/zaber_stage_io.py`, `panels/`, `widgets/`, `MotorInfo.py`, `imports.py`

---
For questions or unclear patterns, review the above files for concrete examples.
