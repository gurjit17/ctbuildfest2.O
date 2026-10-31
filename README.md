# Smart Mobile Robotic Waste Segregation System

Software around your EXISTING prototype. Starts in **DRY-RUN**: nothing is actuated and no data is invented.

## 1. Install (Python 3.10+, VS Code)
```bash
cd smart_waste_robot
python -m venv .venv
.venv\Scripts\activate          # Windows      (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/Mac: cp .env.example .env
```
Edit `.env`: set `CONTROL_TOKEN` to any secret (needed for dashboard buttons) and `CAMERA_SOURCE`.

## 2. Run (dry-run)
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000. Tests: `python -m pytest`.
Chart.js loads from a CDN, so the PC needs internet for the charts only.

## 3. Camera (`CAMERA_SOURCE`)
USB webcam `0` (try `1` if wrong); on Windows numeric camera indexes try DirectShow first and Media Foundation if needed. IP/ESP32-CAM stream `http://<ip>:81/stream` (use YOUR camera's URL) · test video file path.
Check first: `python training/predict.py --source 0` (needs a trained model).

## 4. Trained model and future training
The configured `models/best.pt` is the project's trained waste model. Its loaded class names are:
`fruit_peel`, `vegetable_peel`, `food_waste`, `cotton`, `paper`, `cardboard`, `cloth`,
`plastic_bottle`, `plastic_packet`, `glass`, `bangle_glass`, `bangle_plastic`, `bangle_metal`,
`metal_object`, `watch`, `electronic_waste`, `special_item`, and `needle`.
Coal and wood are not present in this model; detecting them requires labeled training examples and new weights.

To improve or extend YOUR model:
1. Photograph each waste type in the real gripper position, varied lighting/backgrounds, ~150+ images per class (more for glass/plastic/metal bangles, watch, needle).
2. Label boxes (Roboflow, CVAT or labelImg) using the class names in `training/dataset.yaml`; export YOLO format.
3. Put files in `datasets/waste/images|labels/{train,val,test}` (about 70/20/10 split, test photos never used for training).
4. `python training/train.py --epochs 100 --device cpu` (or `--device 0` for a GPU) -> copies weights to `models/best.pt`.
5. `python training/validate.py` for test-set mAP/precision/recall. Restart the server.
Sorting accuracy on the dashboard comes only from your own Yes/No clicks on verified sorts, never from mAP.

## 5. What you must calibrate
| Item | How |
|---|---|
| Bin distances | Empty each bin, read `bin_distance_cm` (shown in `/api/state` after telemetry works), set `BINx_EMPTY_CM`; fill to its limit, set `BINx_FULL_CM`. Uncalibrated = level UNKNOWN. |
| Moisture | Read dry and wet cotton raw values, set `MOISTURE_WET_THRESHOLD` and `MOISTURE_HIGH_IS_WET`. Blank = cotton goes to manual inspection. |
| Car protocol | Fill `CAR_URL_TEMPLATE` and `CAR_COMMANDS` with what your existing app/module already uses. Blank = drive buttons hidden. |

## 6. Arduino link
`TRANSPORT=serial` + `SERIAL_PORT=COM3` (Linux `/dev/ttyUSB0`) + `BAUD_RATE=115200`, or `TRANSPORT=http` + `HTTP_COMMAND_URL` / `HTTP_TELEMETRY_URL`.
Keep `DRY_RUN=true`: telemetry is READ, but no command is sent. `firmware/arduino_controller.ino` is a template (all pins/angles are blank, `CONFIGURED 0`): merge it into your sketch, keep your car code untouched, fill the TODOs, then set `CONFIGURED 1`.

Protocol (compact JSON lines). PC->Arduino `{"id":7,"command":"ARM_HOME"}`; commands: `PING STOP ESTOP ARM_APPROACH GRIPPER_CLOSE ARM_ROTATE(bin,sub) GRIPPER_RELEASE ARM_HOME SEAL(bin)`.
Arduino->PC: `{"ack":"ARM_HOME","id":7,"ok":true}` after the action finishes, and telemetry:
`{"robot_status":"online","bin_distance_cm":{"bin_1":12.4,"bin_2":null,"bin_3":9.0},"moisture":650,"metal_detected":false,"object_gripped":true,"deposit_confirmed":true}`
(`bin_weights_kg` optional; only used when `HAS_LOAD_CELL=true`). Firmware must reset `object_gripped`/`deposit_confirmed` to false when a new pick starts.

## 7. Hardware bring-up (in order; stop at the first failure)
1. Dry-run, no hardware: dashboard loads, WebSocket shows Live, tests pass.
2. Camera shows in the dashboard; model status `ready`; boxes appear on a held-up item.
3. Serial/HTTP telemetry arrives (Robot ONLINE, last-communication updating); unplug USB: goes OFFLINE within `COMM_TIMEOUT_S` and an ERROR event is logged.
4. Bin sensors calibrated; levels move correctly; cover a sensor: level becomes UNKNOWN.
5. Wheels OFF the ground: car buttons work; Stop works; drive is refused while the arm is extended.
6. Arm unloaded, servo supply switch within reach: set `ANG_*`, `CONFIGURED 1`, `DRY_RUN=false`, run each command by hand.
7. Implement and test `readGripSensor`, `readDepositSensor`, `sealBin`. Until then no sort is ever marked verified.
8. Test E-STOP, heartbeat loss (unplug PC) and manual-intervention flow.
9. Auto mode with one light item. Mark results Yes/No to build real accuracy.
Measure the real arm clearance before programming motion (the "100 mm" figure is unconfirmed).

## 8. Troubleshooting
| Symptom | Check |
|---|---|
| Controls say "disabled" / 401 | `CONTROL_TOKEN` in `.env`, same value in the header box, restart server |
| NO CAMERA SIGNAL | wrong `CAMERA_SOURCE`; app using the camera; URL not reachable |
| Model: model_missing | train first, `models/best.pt` must exist |
| Robot OFFLINE | wrong port/baud; Serial Monitor open elsewhere; sketch not sending telemetry; Arduino resets on connect (wait 2 s) |
| Bin level "unknown" | not calibrated, sensor timeout (returns null), or telemetry older than `SENSOR_STALE_S` |
| Everything goes to MANUAL_INTERVENTION | confidence below `CONF_THRESHOLD`, moisture/metal contradiction, bin full, or car stop unconfirmed (`CAR_STOP_REQUIRED`) |
| Sorts never "verified" | deposit sensor stub not implemented, or firmware not clearing `deposit_confirmed` |
| Seal refused | see Events log: arm not home, car moving, level unknown/below 85% |

Dashboard has no login beyond the token: run it on a trusted network only. Logs: `data/logs/app.log`, DB: `data/waste_robot.db`.

## 9. Live camera monitoring
The dashboard uses persistent ByteTrack IDs from the configured YOLO model to show live boxes, class names,
confidence, and tracking IDs. A tracked object is added once to the camera-detection ledger in SQLite;
camera detections are not hardware-confirmed deposits. Resetting camera counts clears the active totals but
retains the timestamped history. The reset action requires the dashboard control token.

Material cards and charts use only the model's real class names. Unsupported material cards (currently coal
and wood) are labeled as requiring model training. Bin camera-mapped counts are separate from robot-verified
deposits. Weight is shown only from configured load-cell readings (`HAS_LOAD_CELL=true` and `bin_weights_kg`
telemetry in kilograms); camera observations are never used to estimate weight.
