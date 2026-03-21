# uvk1-csv — Quansheng UV-K1 Channel Programmer

CLI utility to program the **Quansheng UV-K1** (and UV-K5 V3) radio with **F4HWN Fusion v5.x** firmware via CSV files. No CHIRP or wxPython required.

## Features

- **Download** all channels from radio to a human-readable CSV file
- **Upload** channels from CSV to radio (safe read-modify-write cycle)
- **Backup/restore** raw binary memory images
- **Offline mode** — edit channels without a radio connected (dump/patch image files)
- Channel range filtering (`--channels 1-16,20-30`)
- Dry-run mode for previewing changes
- Supports all channel properties: frequency, offset, duplex, CTCSS/DCS tones, modulation (FM/NFM/AM/USB), 8 power levels, compander, scan lists, and more

## Requirements

- Python 3.8+
- [pyserial](https://pypi.org/project/pyserial/) (`pip install pyserial`) — only needed for radio communication; offline commands work without it
- Quansheng UV-K1 or UV-K5 V3 with [F4HWN Fusion v5.x firmware](https://github.com/armel/uv-k1-k5v3-firmware-custom/releases)
- USB-C cable (or serial cable to mic/spkr connector)

```bash
pip install pyserial
```

## Quick Start

### Download channels from radio to CSV

```bash
./uvk1_csv.py download -o channels.csv
```

### Edit the CSV in any spreadsheet or text editor, then upload

```bash
./uvk1_csv.py upload -i channels.csv
```

### Program PMR446 channels only (wipe everything else)

A ready-made `pmr446.csv` is included with all 16 standard PMR446 channels (NFM, 500 mW):

```bash
./uvk1_csv.py backup -o backup.img              # always backup first
./uvk1_csv.py upload -i pmr446.csv --clear-other # upload PMR + delete rest
```

### Backup before making changes

```bash
./uvk1_csv.py backup -o backup.img
./uvk1_csv.py upload -i channels.csv
```

## Commands

| Command   | Description                        | Radio needed? |
|-----------|------------------------------------|:---:|
| `download` | Download channels from radio to CSV | Yes |
| `upload`   | Upload channels from CSV to radio   | Yes |
| `backup`   | Download raw binary image from radio | Yes |
| `restore`  | Upload raw binary image to radio    | Yes |
| `dump`     | Convert binary image to CSV (offline) | No |
| `patch`    | Apply CSV to binary image (offline)   | No |

### download

```bash
./uvk1_csv.py download -o channels.csv
./uvk1_csv.py download -o channels.csv --channels 1-16
./uvk1_csv.py download --skip-empty          # default: skip empty channels
./uvk1_csv.py download --include-empty        # include empty channel rows
```

### upload

Downloads the current image from radio, patches in the CSV channels, then uploads. Only channels present in the CSV are modified — everything else is preserved. Use `--clear-other` to delete all channels not in the CSV.

```bash
./uvk1_csv.py upload -i channels.csv
./uvk1_csv.py upload -i channels.csv --dry-run    # preview without writing
./uvk1_csv.py upload -i channels.csv --clear-other # delete all channels NOT in the CSV
./uvk1_csv.py upload -i channels.csv -p /dev/ttyUSB0
```

### backup / restore

```bash
./uvk1_csv.py backup -o backup.img
./uvk1_csv.py restore -i backup.img
./uvk1_csv.py restore -i backup.img --dry-run
```

### dump / patch (offline, no radio)

Work with binary image files directly:

```bash
./uvk1_csv.py dump --image backup.img -o channels.csv
./uvk1_csv.py dump --image backup.img --channels 1-16 -o pmr.csv

./uvk1_csv.py patch --image backup.img -i channels.csv -o modified.img
./uvk1_csv.py patch --image backup.img -i pmr446.csv -o clean.img --clear-other
```

### Common options

| Option | Default | Description |
|--------|---------|-------------|
| `-p, --port` | `/dev/ttyACM0` | Serial port |
| `--channels` | all | Channel range, e.g. `1-16` or `1,5,10-20` |
| `--skip-empty` | on | Skip empty channels in CSV output |
| `--include-empty` | off | Include empty channel rows |
| `--dry-run` | off | Preview changes without writing to radio |
| `--clear-other` | off | Clear all channels NOT in the CSV (upload/patch only) |

## CSV Format

The CSV uses one row per channel with the following columns:

| Column | Values | Example |
|--------|--------|---------|
| Channel | 1–1024 | `1` |
| Name | up to 16 characters | `PMR 01` |
| Frequency | MHz (5 decimal places) | `446.00625` |
| Offset | MHz | `0.60000` |
| OffsetDir | `OFF`, `+`, `-` | `-` |
| Mode | `FM`, `NFM`, `AM`, `NAM`, `USB` | `NFM` |
| Power | `USER`, `LOW1`–`LOW5`, `MID`, `HIGH` | `LOW4` |
| RxTone | `OFF`, CTCSS freq, or DCS code | `88.5`, `D023N` |
| TxTone | same as RxTone | `D023R` |
| Step | kHz | `12.5` |
| Compander | `OFF`, `TX`, `RX`, `TX/RX` | `OFF` |
| ScanList | 0–255 | `0` |
| TxLock | `OFF`, `ON` | `OFF` |
| BusyCL | `OFF`, `ON` | `OFF` |
| FreqReverse | `OFF`, `ON` | `OFF` |
| DTMF_PTTID | `OFF`, `UP`, `DOWN`, `UP+DOWN`, `APOLLO` | `OFF` |
| DTMF_Decode | `OFF`, `ON` | `OFF` |

### Tone format

- **No tone**: `OFF`
- **CTCSS**: frequency as decimal, e.g. `67.0`, `88.5`, `254.1`
- **DCS normal**: `D` + 3-digit code + `N`, e.g. `D023N`, `D754N`
- **DCS reverse**: `D` + 3-digit code + `R`, e.g. `D023R`

### Example CSV

```csv
Channel,Name,Frequency,Offset,OffsetDir,Mode,Power,RxTone,TxTone,Step,Compander,ScanList,TxLock,BusyCL,FreqReverse,DTMF_PTTID,DTMF_Decode
1,PMR 01,446.00625,0.00000,OFF,NFM,LOW4,OFF,OFF,12.5,OFF,0,OFF,OFF,OFF,OFF,OFF
2,PMR 02,446.01875,0.00000,OFF,NFM,LOW4,OFF,OFF,12.5,OFF,0,OFF,OFF,OFF,OFF,OFF
3,Repeater,145.60000,0.60000,-,FM,HIGH,88.5,88.5,12.5,OFF,0,OFF,OFF,OFF,OFF,OFF
4,DCS Test,446.03125,0.00000,OFF,NFM,LOW4,D023N,D023N,12.5,OFF,0,OFF,OFF,OFF,OFF,OFF
```

## Power Levels

| Value | Label | Power |
|-------|-------|-------|
| `USER` | User-defined | < 20 mW to 5 W |
| `LOW1` | Low 1 | < 20 mW |
| `LOW2` | Low 2 | 125 mW |
| `LOW3` | Low 3 | 250 mW |
| `LOW4` | Low 4 | 500 mW |
| `LOW5` | Low 5 | 1 W |
| `MID`  | Medium | 2 W |
| `HIGH` | High | 5 W |

For PMR 446, use `LOW4` (500 mW) — the maximum permitted ERP.

## Connecting the Radio

1. Turn on the radio in **normal mode** (not programming mode)
2. Connect via USB-C cable
3. Verify the serial port appears:

```bash
ls -la /dev/ttyACM0
```

If using a Baofeng/Kenwood-style serial cable to the mic/spkr connector, the port will typically be `/dev/ttyUSB0`.

## Troubleshooting

### `Permission denied: /dev/ttyACM0`

Add yourself to the `dialout` group (log out and back in after):

```bash
sudo usermod -aG dialout $USER
```

### `Radio is in programming mode`

Turn off the radio and turn it back on normally (without holding any buttons).

### `Header short read` / `Failed to initialize radio`

- Check the cable connection
- Try unplugging and reconnecting USB-C
- Make sure the radio is powered on

## How It Works

The utility communicates with the radio over USB serial at 38400 baud using the F4HWN protocol:

1. **Upload** always performs a safe read-modify-write cycle: downloads the full memory image, patches only the channels from the CSV, then uploads the modified image. This preserves all settings and unmodified channels.
2. Channel data is stored as 16-byte records in the radio's EEPROM (1024 channels total).
3. The protocol uses XOR obfuscation and CRC-16 XModem for data integrity.

### Memory Map (F4HWN Fusion v5.x)

| Region | Address | Description |
|--------|---------|-------------|
| Channel data | `0x000000` | 1024 channels, 16 bytes each |
| Channel names | `0x004000` | 1024 names, 16 bytes each |
| Channel attributes | `0x008000` | Band, compander, scan list |
| VFO channels | `0x009000` | 14 VFO presets |
| Settings | `0x00A000` | Radio configuration |
| Calibration | `0x00B000` | Calibration data (not written) |

Total EEPROM: 45,456 bytes. Only the program region (0x000000–0x00A170) is written during upload.

## Legacy: program_pmr446.py

The included `program_pmr446.py` is an older script that programs hardcoded PMR 446 channels (1–16). It requires the `chirp` Python package. For new usage, prefer `uvk1_csv.py` which has no CHIRP dependency and supports arbitrary channels via CSV.

## License

Based on the [F4HWN CHIRP driver](https://github.com/armel/uv-k1-k5v3-firmware-custom) (GPLv2+), which builds on work by [sq5bpf](https://github.com/sq5bpf/uvk5-reverse-engineering) and [egzumer](https://github.com/egzumer/uv-k5-firmware-custom).

Licensed under **GPLv2+**.
