#!/usr/bin/env python3
"""
UV-K1 Radio Programming Utility — CSV import/export for Quansheng UV-K1
with F4HWN Fusion v5.x firmware.

No CHIRP or wx dependency. Only requires pyserial.

Usage:
    uvk1_csv.py download -o channels.csv          # radio → CSV
    uvk1_csv.py upload -i channels.csv             # CSV → radio
    uvk1_csv.py backup -o backup.img               # radio → binary image
    uvk1_csv.py restore -i backup.img              # binary image → radio
    uvk1_csv.py dump --image backup.img -o ch.csv  # offline: image → CSV
    uvk1_csv.py patch --image backup.img -i ch.csv -o out.img  # offline
"""

import struct
import csv
import sys
import argparse
import time
import io

try:
    import serial
except ImportError:
    serial = None  # allow offline commands without pyserial

# ── Constants ────────────────────────────────────────────────────────────

MEM_SIZE = 0x00B190
PROG_SIZE = 0x00A171
MEM_BLOCK = 0x80
MR_CHANNELS_MAX = 1024

ADDR_CHANNELS = 0x000000
ADDR_NAMES = 0x004000
ADDR_ATTRS = 0x008000

CTCSS_TONES = [
    67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4,
    88.5, 91.5, 94.8, 97.4, 100.0, 103.5, 107.2, 110.9,
    114.8, 118.8, 123.0, 127.3, 131.8, 136.5, 141.3, 146.2,
    151.4, 156.7, 159.8, 162.2, 165.5, 167.9, 171.3, 173.8,
    177.3, 179.9, 183.5, 186.2, 189.9, 192.8, 196.6, 199.5,
    203.5, 206.5, 210.7, 218.1, 225.7, 229.1, 233.6, 241.8,
    250.3, 254.1
]

DTCS_CODES = [
    23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54,
    65, 71, 72, 73, 74, 114, 115, 116, 122, 125, 131,
    132, 134, 143, 145, 152, 155, 156, 162, 165, 172, 174,
    205, 212, 223, 225, 226, 243, 244, 245, 246, 251, 252,
    255, 261, 263, 265, 266, 271, 274, 306, 311, 315, 325,
    331, 332, 343, 346, 351, 356, 364, 365, 371, 411, 412,
    413, 423, 431, 432, 445, 446, 452, 454, 455, 462, 464,
    465, 466, 503, 506, 516, 523, 526, 532, 546, 565, 606,
    612, 624, 627, 631, 632, 654, 662, 664, 703, 712, 723,
    731, 732, 734, 743, 754
]

STEPS = [2.5, 5, 6.25, 10, 12.5, 25, 8.33, 0.01, 0.05, 0.1, 0.25, 0.5,
         1, 1.25, 9, 15, 20, 30, 50, 100, 125, 200, 250, 500]

POWER_NAMES = ["USER", "LOW1", "LOW2", "LOW3", "LOW4", "LOW5", "MID", "HIGH"]
MODE_NAMES = ["FM", "NFM", "AM", "NAM", "USB"]
COMPANDER_NAMES = ["OFF", "TX", "RX", "TX/RX"]
PTTID_NAMES = ["OFF", "UP", "DOWN", "UP+DOWN", "APOLLO"]
OFFSET_DIR_NAMES = ["OFF", "+", "-"]

BANDS = {
    0: (50_000_000, 76_000_000),
    1: (108_000_000, 137_000_000),
    2: (137_000_000, 174_000_000),
    3: (174_000_000, 350_000_000),
    4: (350_000_000, 400_000_000),
    5: (400_000_000, 470_000_000),
    6: (470_000_000, 600_000_000),
}

TONE_NONE = 0
TONE_CTCSS = 1
TONE_DCS = 2
TONE_RDCS = 3

CSV_COLUMNS = [
    "Channel", "Name", "Frequency", "Offset", "OffsetDir", "Mode",
    "Power", "RxTone", "TxTone", "Step", "Compander", "ScanList",
    "TxLock", "BusyCL", "FreqReverse", "DTMF_PTTID", "DTMF_Decode"
]


# ── Exceptions ───────────────────────────────────────────────────────────

class RadioError(Exception):
    pass


# ── Tone encode/decode ───────────────────────────────────────────────────

def decode_tone(code: int, flag: int) -> str:
    if flag == TONE_NONE:
        return "OFF"
    if flag == TONE_CTCSS:
        if 0 <= code < len(CTCSS_TONES):
            return str(CTCSS_TONES[code])
        return "OFF"
    if flag == TONE_DCS:
        if 0 <= code < len(DTCS_CODES):
            return f"D{DTCS_CODES[code]:03d}N"
        return "OFF"
    if flag == TONE_RDCS:
        if 0 <= code < len(DTCS_CODES):
            return f"D{DTCS_CODES[code]:03d}R"
        return "OFF"
    return "OFF"


def encode_tone(tone_str: str) -> tuple:
    """Returns (code, flag)."""
    s = tone_str.strip().upper()
    if not s or s == "OFF":
        return (0, TONE_NONE)
    # DCS: D023N or D023R
    if s.startswith("D") and len(s) >= 4 and s[-1] in ("N", "R"):
        try:
            dcs_code = int(s[1:-1])
        except ValueError:
            raise ValueError(f"Invalid DCS tone: {tone_str}")
        if dcs_code not in DTCS_CODES:
            raise ValueError(f"Unknown DCS code: {dcs_code}")
        idx = DTCS_CODES.index(dcs_code)
        flag = TONE_DCS if s[-1] == "N" else TONE_RDCS
        return (idx, flag)
    # CTCSS: numeric frequency
    try:
        freq = float(s)
    except ValueError:
        raise ValueError(f"Invalid tone: {tone_str}")
    if freq not in CTCSS_TONES:
        # find closest
        closest = min(CTCSS_TONES, key=lambda t: abs(t - freq))
        if abs(closest - freq) < 0.05:
            freq = closest
        else:
            raise ValueError(f"Unknown CTCSS tone: {freq}")
    return (CTCSS_TONES.index(freq), TONE_CTCSS)


# ── Band detection ───────────────────────────────────────────────────────

def find_band(freq_hz: int) -> int:
    for band, (lo, hi) in BANDS.items():
        if lo <= freq_hz < hi:
            return band
    return 0


# ── Binary codec ─────────────────────────────────────────────────────────
#
# Bitfield layout (CHIRP bitwise = MSB-first within byte):
#   Byte 10: txcodeflag[7:4] | rxcodeflag[3:0]
#   Byte 11: modulation[7:4] | offsetDir[3:0]
#   Byte 12: unused[7] | txLock[6] | busyChLockout[5] | txpower[4:2] | bandwidth[1] | freq_reverse[0]
#   Byte 13: unused[7:4] | dtmf_pttid[3:1] | dtmf_decode[0]
#   Attr byte 0: unused[7:5] | compander[4:3] | band[2:0]

def decode_channel(image: bytes, idx: int) -> dict:
    """Decode channel idx (0-based) from binary image. Returns dict or None if empty."""
    ch_base = ADDR_CHANNELS + idx * 16
    name_base = ADDR_NAMES + idx * 16
    attr_base = ADDR_ATTRS + idx * 2

    freq, offset, rxcode, txcode, b10, b11, b12, b13, step, _ = \
        struct.unpack_from('<IIBBBBBBBB', image, ch_base)

    if freq == 0xFFFFFFFF or freq == 0:
        return None
    # validate frequency is in a sane range (18 MHz - 1300 MHz in 10Hz units)
    freq_hz = freq * 10
    if freq_hz < 18_000_000 or freq_hz > 1_300_000_000:
        return None

    # decode bitfields
    rxcodeflag = b10 & 0x0F
    txcodeflag = (b10 >> 4) & 0x0F
    modulation = (b11 >> 4) & 0x0F
    offset_dir = b11 & 0x0F
    freq_reverse = b12 & 0x01
    bandwidth = (b12 >> 1) & 0x01
    txpower = (b12 >> 2) & 0x07
    busy_cl = (b12 >> 5) & 0x01
    tx_lock = (b12 >> 6) & 0x01
    dtmf_decode = b13 & 0x01
    dtmf_pttid = (b13 >> 1) & 0x07

    # mode: modulation * 2 + bandwidth -> index into MODE_NAMES
    mode_idx = modulation * 2 + bandwidth
    if mode_idx >= len(MODE_NAMES):
        mode_idx = 0
    # USB special case: bandwidth doesn't matter
    if modulation == 2:
        mode_idx = 4  # USB

    # channel name
    raw_name = image[name_base:name_base + 16]
    name = raw_name.rstrip(b'\xff\x00').decode('latin-1').rstrip()

    # attributes
    if attr_base + 1 < len(image):
        a0, a1 = image[attr_base], image[attr_base + 1]
        band = a0 & 0x07
        compander = (a0 >> 3) & 0x03
        scanlist = a1
    else:
        band = find_band(freq * 10)
        compander = 0
        scanlist = 0

    # step
    step_khz = STEPS[step] if 0 <= step < len(STEPS) else 12.5

    return {
        "channel": idx + 1,
        "name": name,
        "freq_mhz": (freq * 10) / 1_000_000,
        "offset_mhz": (offset * 10) / 1_000_000,
        "offset_dir": OFFSET_DIR_NAMES[offset_dir] if offset_dir < len(OFFSET_DIR_NAMES) else "OFF",
        "mode": MODE_NAMES[mode_idx],
        "power": POWER_NAMES[txpower] if txpower < len(POWER_NAMES) else "HIGH",
        "rx_tone": decode_tone(rxcode, rxcodeflag),
        "tx_tone": decode_tone(txcode, txcodeflag),
        "step_khz": step_khz,
        "compander": COMPANDER_NAMES[compander] if compander < len(COMPANDER_NAMES) else "OFF",
        "scanlist": scanlist,
        "tx_lock": "ON" if tx_lock else "OFF",
        "busy_cl": "ON" if busy_cl else "OFF",
        "freq_reverse": "ON" if freq_reverse else "OFF",
        "dtmf_pttid": PTTID_NAMES[dtmf_pttid] if dtmf_pttid < len(PTTID_NAMES) else "OFF",
        "dtmf_decode": "ON" if dtmf_decode else "OFF",
    }


def encode_channel(ch: dict, image: bytearray, idx: int):
    """Write channel dict into binary image at idx (0-based). Mutates image."""
    ch_base = ADDR_CHANNELS + idx * 16
    name_base = ADDR_NAMES + idx * 16
    attr_base = ADDR_ATTRS + idx * 2

    freq_hz = int(round(ch["freq_mhz"] * 1_000_000))
    offset_hz = int(round(ch["offset_mhz"] * 1_000_000))
    freq_10hz = freq_hz // 10
    offset_10hz = offset_hz // 10

    # mode -> modulation + bandwidth
    mode = ch["mode"].upper()
    if mode not in MODE_NAMES:
        raise ValueError(f"Unknown mode: {mode}")
    mode_idx = MODE_NAMES.index(mode)
    # FM=0, NFM=1, AM=2, NAM=3, USB=4
    if mode_idx <= 3:
        modulation = mode_idx // 2
        bandwidth = mode_idx % 2
    else:  # USB
        modulation = 2
        bandwidth = 0

    offset_dir = OFFSET_DIR_NAMES.index(ch.get("offset_dir", "OFF").upper()) \
        if ch.get("offset_dir", "OFF").upper() in OFFSET_DIR_NAMES else 0

    txpower = POWER_NAMES.index(ch.get("power", "LOW2").upper()) \
        if ch.get("power", "LOW2").upper() in POWER_NAMES else 2

    rx_code, rx_flag = encode_tone(ch.get("rx_tone", "OFF"))
    tx_code, tx_flag = encode_tone(ch.get("tx_tone", "OFF"))

    step_khz = float(ch.get("step_khz", 12.5))
    step_idx = STEPS.index(step_khz) if step_khz in STEPS else 4  # default 12.5

    tx_lock = 1 if ch.get("tx_lock", "OFF").upper() == "ON" else 0
    busy_cl = 1 if ch.get("busy_cl", "OFF").upper() == "ON" else 0
    freq_reverse = 1 if ch.get("freq_reverse", "OFF").upper() == "ON" else 0
    dtmf_decode = 1 if ch.get("dtmf_decode", "OFF").upper() == "ON" else 0

    pttid_name = ch.get("dtmf_pttid", "OFF").upper()
    dtmf_pttid = PTTID_NAMES.index(pttid_name) if pttid_name in PTTID_NAMES else 0

    # pack bitfields
    b10 = (tx_flag << 4) | (rx_flag & 0x0F)
    b11 = (modulation << 4) | (offset_dir & 0x0F)
    b12 = (tx_lock << 6) | (busy_cl << 5) | ((txpower & 0x07) << 2) | (bandwidth << 1) | freq_reverse
    b13 = ((dtmf_pttid & 0x07) << 1) | dtmf_decode

    struct.pack_into('<IIBBBBBBBB', image, ch_base,
                     freq_10hz, offset_10hz,
                     rx_code, tx_code,
                     b10, b11, b12, b13,
                     step_idx, 0)

    # name (16 bytes): empty → \xff padding, non-empty → \x00 padding
    name = ch.get("name", "")[:16]
    if name:
        name_bytes = name.encode('latin-1', errors='replace').ljust(16, b'\x00')
    else:
        name_bytes = b'\xff' * 16
    image[name_base:name_base + 16] = name_bytes

    # attributes
    comp_name = ch.get("compander", "OFF").upper()
    compander = COMPANDER_NAMES.index(comp_name) if comp_name in COMPANDER_NAMES else 0
    band = find_band(freq_hz)
    scanlist = int(ch.get("scanlist", 0))

    if attr_base + 1 < len(image):
        # preserve unused bits from existing byte
        existing_a0 = image[attr_base]
        a0 = (existing_a0 & 0xE0) | ((compander & 0x03) << 3) | (band & 0x07)
        image[attr_base] = a0
        image[attr_base + 1] = scanlist & 0xFF


def clear_channel(image: bytearray, idx: int):
    """Clear a channel slot (mark as empty)."""
    ch_base = ADDR_CHANNELS + idx * 16
    name_base = ADDR_NAMES + idx * 16
    attr_base = ADDR_ATTRS + idx * 2

    image[ch_base:ch_base + 16] = b'\xff' * 16
    image[name_base:name_base + 16] = b'\x00' * 16
    if attr_base + 1 < len(image):
        image[attr_base:attr_base + 2] = b'\xff\xff'


# ── CSV I/O ──────────────────────────────────────────────────────────────

def channel_to_csv_row(ch: dict) -> dict:
    return {
        "Channel": ch["channel"],
        "Name": ch["name"],
        "Frequency": f'{ch["freq_mhz"]:.5f}',
        "Offset": f'{ch["offset_mhz"]:.5f}',
        "OffsetDir": ch["offset_dir"],
        "Mode": ch["mode"],
        "Power": ch["power"],
        "RxTone": ch["rx_tone"],
        "TxTone": ch["tx_tone"],
        "Step": ch["step_khz"],
        "Compander": ch["compander"],
        "ScanList": ch["scanlist"],
        "TxLock": ch["tx_lock"],
        "BusyCL": ch["busy_cl"],
        "FreqReverse": ch["freq_reverse"],
        "DTMF_PTTID": ch["dtmf_pttid"],
        "DTMF_Decode": ch["dtmf_decode"],
    }


def csv_row_to_channel(row: dict) -> dict:
    return {
        "channel": int(row["Channel"]),
        "name": row.get("Name", "").strip(),
        "freq_mhz": float(row["Frequency"]),
        "offset_mhz": float(row.get("Offset", "0")),
        "offset_dir": row.get("OffsetDir", "OFF").strip().upper(),
        "mode": row.get("Mode", "FM").strip().upper(),
        "power": row.get("Power", "LOW2").strip().upper(),
        "rx_tone": row.get("RxTone", "OFF").strip(),
        "tx_tone": row.get("TxTone", "OFF").strip(),
        "step_khz": float(row.get("Step", "12.5")),
        "compander": row.get("Compander", "OFF").strip().upper(),
        "scanlist": int(row.get("ScanList", "0")),
        "tx_lock": row.get("TxLock", "OFF").strip().upper(),
        "busy_cl": row.get("BusyCL", "OFF").strip().upper(),
        "freq_reverse": row.get("FreqReverse", "OFF").strip().upper(),
        "dtmf_pttid": row.get("DTMF_PTTID", "OFF").strip().upper(),
        "dtmf_decode": row.get("DTMF_Decode", "OFF").strip().upper(),
    }


def export_csv(image: bytes, outfile, skip_empty: bool = True,
               channels: list = None):
    """Write channels from binary image to CSV file object."""
    writer = csv.DictWriter(outfile, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    count = 0
    for idx in range(MR_CHANNELS_MAX):
        ch_num = idx + 1
        if channels and ch_num not in channels:
            continue
        ch = decode_channel(image, idx)
        if ch is None:
            if not skip_empty:
                writer.writerow({"Channel": ch_num})
            continue
        writer.writerow(channel_to_csv_row(ch))
        count += 1
    return count


def import_csv(infile) -> list:
    """Read channels from CSV file object. Returns list of channel dicts."""
    reader = csv.DictReader(infile)
    channels = []
    for row in reader:
        if not row.get("Frequency") or not row["Frequency"].strip():
            continue
        channels.append(csv_row_to_channel(row))
    return channels


# ── Serial protocol ──────────────────────────────────────────────────────
# Copied from program_pmr446.py with chirp.errors replaced by RadioError.

def xorarr(data: bytes) -> bytes:
    tbl = [22, 108, 20, 230, 46, 145, 13, 64,
           33, 53, 213, 64, 19, 3, 233, 128]
    ret = b""
    idx = 0
    for byte in data:
        ret += bytes([byte ^ tbl[idx]])
        idx = (idx + 1) % len(tbl)
    return ret


def calculate_crc16_xmodem(data: bytes) -> int:
    poly = 0x1021
    crc = 0x0
    for byte in data:
        crc = crc ^ (byte << 8)
        for _ in range(8):
            crc = crc << 1
            if crc & 0x10000:
                crc = (crc ^ poly) & 0xFFFF
    return crc & 0xFFFF


def _send_command(serport, data: bytes):
    crc = calculate_crc16_xmodem(data)
    data2 = data + struct.pack("<H", crc)
    command = (struct.pack(">HBB", 0xabcd, len(data), 0) +
               xorarr(data2) +
               struct.pack(">H", 0xdcba))
    serport.write(command)


def _receive_reply(serport) -> bytes:
    header = serport.read(4)
    if len(header) != 4:
        raise RadioError(f"Header short read: got {len(header)} bytes")
    if header[0] != 0xAB or header[1] != 0xCD or header[3] != 0x00:
        raise RadioError(f"Bad response header: {header.hex()}")

    cmd = serport.read(int(header[2]))
    if len(cmd) != int(header[2]):
        raise RadioError(f"Body short read: got {len(cmd)}, expected {header[2]}")

    footer = serport.read(4)
    if len(footer) != 4:
        raise RadioError(f"Footer short read: got {len(footer)} bytes")
    if footer[2] != 0xDC or footer[3] != 0xBA:
        raise RadioError(f"Bad response footer: {footer.hex()}")

    return xorarr(cmd)


def _sayhello(serport) -> str:
    hellopacket = b"\x14\x05\x04\x00\x6a\x39\x57\x64"
    tries = 5
    while True:
        _send_command(serport, hellopacket)
        rep = _receive_reply(serport)
        if rep:
            break
        tries -= 1
        if tries == 0:
            raise RadioError("Failed to initialize radio")
    if rep.startswith(b'\x18\x05'):
        raise RadioError("Radio is in programming mode, restart into normal mode")

    ss = []
    for i in range(4, min(28, len(rep))):
        if rep[i] < ord(' ') or rep[i] > ord('~'):
            break
        ss.append(chr(rep[i]))
    return ''.join(ss)


def _readmem(serport, offset: int, length: int) -> bytes:
    readmem = (b"\x1b\x05\x08\x00" +
               struct.pack("<HBB", offset, length, 0) +
               b"\x6a\x39\x57\x64")
    _send_command(serport, readmem)
    rep = _receive_reply(serport)
    return rep[8:]


def _writemem(serport, data: bytes, offset: int) -> bool:
    dlen = len(data)
    writemem = (b"\x1d\x05" +
                struct.pack("<BBHBB", dlen + 8, 0, offset, dlen, 1) +
                b"\x6a\x39\x57\x64" + data)
    _send_command(serport, writemem)
    rep = _receive_reply(serport)
    if (rep[0] == 0x1e and
            rep[4] == (offset & 0xff) and
            rep[5] == (offset >> 8) & 0xff):
        return True
    raise RadioError(f"Bad response to writemem at offset 0x{offset:04x}")


def _resetradio(serport):
    resetpacket = b"\xdd\x05\x00\x00"
    _send_command(serport, resetpacket)


def download_image(serport) -> bytes:
    """Download full memory image from radio."""
    firmware = _sayhello(serport)
    print(f"  Firmware: {firmware}", file=sys.stderr)

    eeprom = b""
    addr = 0
    total = MEM_SIZE
    while addr < total:
        data = _readmem(serport, addr, MEM_BLOCK)
        if data and len(data) == MEM_BLOCK:
            eeprom += data
            addr += MEM_BLOCK
        else:
            raise RadioError(f"Download incomplete at 0x{addr:04x}")
        pct = addr * 100 // total
        print(f"\r  Downloading: {pct:3d}%", end="", flush=True, file=sys.stderr)

    print(f"\r  Download complete: {len(eeprom)} bytes    ", file=sys.stderr)
    return eeprom


def upload_image(serport, mmap_data: bytes):
    """Upload program region of memory image to radio."""
    firmware = _sayhello(serport)
    print(f"  Firmware: {firmware}", file=sys.stderr)

    addr = 0
    stop = PROG_SIZE
    while addr < stop:
        remaining = stop - addr
        chunk = MEM_BLOCK if remaining >= MEM_BLOCK else remaining
        dat = mmap_data[addr:addr + chunk]
        if not dat or len(dat) != chunk:
            raise RadioError(
                f"Upload incomplete at 0x{addr:06x} "
                f"(wanted {chunk}, got {len(dat) if dat else 0})")
        _writemem(serport, dat, addr)
        addr += chunk
        pct = addr * 100 // stop
        print(f"\r  Uploading: {pct:3d}%", end="", flush=True, file=sys.stderr)

    print(f"\r  Upload complete                ", file=sys.stderr)
    _resetradio(serport)
    print("  Radio reset. Radio should restart.", file=sys.stderr)


# ── Channel range parsing ────────────────────────────────────────────────

def parse_channel_range(s: str) -> list:
    """Parse '1-16,20,25-30' into sorted list of channel numbers."""
    result = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            lo, hi = int(lo.strip()), int(hi.strip())
            result.update(range(lo, hi + 1))
        else:
            result.add(int(part))
    return sorted(result)


def _require_serial():
    if serial is None:
        print("Error: pyserial is required for radio communication.", file=sys.stderr)
        print("Install with: pip install pyserial", file=sys.stderr)
        sys.exit(1)


def _open_serial(port: str):
    _require_serial()
    return serial.Serial(port=port, baudrate=38400, timeout=4.0)


# ── CLI commands ─────────────────────────────────────────────────────────

def cmd_download(args):
    """Download channels from radio to CSV."""
    ser = _open_serial(args.port)
    try:
        image = download_image(ser)
    finally:
        ser.close()

    channels = parse_channel_range(args.channels) if args.channels else None

    if args.output:
        with open(args.output, "w", newline="") as f:
            count = export_csv(image, f, skip_empty=args.skip_empty, channels=channels)
        print(f"  Exported {count} channels to {args.output}", file=sys.stderr)
    else:
        count = export_csv(image, sys.stdout, skip_empty=args.skip_empty, channels=channels)
        print(f"  Exported {count} channels", file=sys.stderr)


def cmd_upload(args):
    """Upload channels from CSV to radio."""
    # read CSV
    with open(args.input, "r") as f:
        csv_channels = import_csv(f)

    if not csv_channels:
        print("Error: no channels found in CSV.", file=sys.stderr)
        sys.exit(1)

    # download current image
    print("Downloading current image from radio...", file=sys.stderr)
    ser = _open_serial(args.port)
    try:
        image = bytearray(download_image(ser))
    finally:
        ser.close()

    # patch channels
    for ch in csv_channels:
        idx = ch["channel"] - 1
        if not (0 <= idx < MR_CHANNELS_MAX):
            print(f"  Warning: skipping channel {ch['channel']} (out of range)", file=sys.stderr)
            continue
        encode_channel(ch, image, idx)
        print(f"  CH {ch['channel']:4d}: {ch['name']:16s}  {ch['freq_mhz']:.5f} MHz  {ch['mode']}  {ch['power']}", file=sys.stderr)

    # clear channels not in CSV
    if args.clear_other:
        csv_indices = {ch["channel"] - 1 for ch in csv_channels}
        cleared = 0
        for idx in range(MR_CHANNELS_MAX):
            if idx not in csv_indices:
                clear_channel(image, idx)
                cleared += 1
        print(f"  Cleared {cleared} other channels", file=sys.stderr)

    if args.dry_run:
        print(f"Dry run: {len(csv_channels)} channels prepared, NOT uploading.", file=sys.stderr)
        return

    # upload
    print("Uploading modified image to radio...", file=sys.stderr)
    ser = _open_serial(args.port)
    try:
        upload_image(ser, bytes(image))
    finally:
        ser.close()

    print(f"Done! {len(csv_channels)} channels programmed.", file=sys.stderr)


def cmd_backup(args):
    """Download raw binary image from radio."""
    ser = _open_serial(args.port)
    try:
        image = download_image(ser)
    finally:
        ser.close()

    with open(args.output, "wb") as f:
        f.write(image)
    print(f"  Backup saved to {args.output} ({len(image)} bytes)", file=sys.stderr)


def cmd_restore(args):
    """Upload raw binary image to radio."""
    with open(args.input, "rb") as f:
        image = f.read()

    if len(image) < PROG_SIZE:
        print(f"Error: image too small ({len(image)} bytes, need at least {PROG_SIZE})", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"Dry run: would upload {len(image)} bytes. NOT uploading.", file=sys.stderr)
        return

    ser = _open_serial(args.port)
    try:
        upload_image(ser, image)
    finally:
        ser.close()

    print(f"  Image restored ({len(image)} bytes)", file=sys.stderr)


def cmd_dump(args):
    """Offline: dump channels from binary image to CSV."""
    with open(args.image, "rb") as f:
        image = f.read()

    channels = parse_channel_range(args.channels) if args.channels else None

    if args.output:
        with open(args.output, "w", newline="") as f:
            count = export_csv(image, f, skip_empty=args.skip_empty, channels=channels)
        print(f"  Exported {count} channels to {args.output}", file=sys.stderr)
    else:
        count = export_csv(image, sys.stdout, skip_empty=args.skip_empty, channels=channels)
        print(f"  Exported {count} channels", file=sys.stderr)


def cmd_patch(args):
    """Offline: apply CSV to binary image."""
    with open(args.image, "rb") as f:
        image = bytearray(f.read())

    with open(args.input, "r") as f:
        csv_channels = import_csv(f)

    if not csv_channels:
        print("Error: no channels found in CSV.", file=sys.stderr)
        sys.exit(1)

    for ch in csv_channels:
        idx = ch["channel"] - 1
        if not (0 <= idx < MR_CHANNELS_MAX):
            print(f"  Warning: skipping channel {ch['channel']} (out of range)", file=sys.stderr)
            continue
        encode_channel(ch, image, idx)
        print(f"  CH {ch['channel']:4d}: {ch['name']:16s}  {ch['freq_mhz']:.5f} MHz  {ch['mode']}  {ch['power']}", file=sys.stderr)

    # clear channels not in CSV
    if args.clear_other:
        csv_indices = {ch["channel"] - 1 for ch in csv_channels}
        cleared = 0
        for idx in range(MR_CHANNELS_MAX):
            if idx not in csv_indices:
                clear_channel(image, idx)
                cleared += 1
        print(f"  Cleared {cleared} other channels", file=sys.stderr)

    with open(args.output, "wb") as f:
        f.write(bytes(image))
    print(f"  Patched {len(csv_channels)} channels → {args.output}", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="UV-K1 Radio Programming Utility — CSV import/export "
                    "(F4HWN Fusion firmware)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    p = subparsers.add_parser("download", help="Download channels from radio to CSV")
    p.add_argument("-p", "--port", default="/dev/ttyACM0", help="Serial port")
    p.add_argument("-o", "--output", help="Output CSV file (default: stdout)")
    p.add_argument("--skip-empty", action="store_true", default=True,
                   help="Skip empty channels (default)")
    p.add_argument("--include-empty", action="store_true",
                   help="Include empty channels in output")
    p.add_argument("--channels", help="Channel range, e.g. '1-16' or '1,5,10-20'")
    p.set_defaults(func=cmd_download)

    # upload
    p = subparsers.add_parser("upload", help="Upload channels from CSV to radio")
    p.add_argument("-p", "--port", default="/dev/ttyACM0", help="Serial port")
    p.add_argument("-i", "--input", required=True, help="Input CSV file")
    p.add_argument("--dry-run", action="store_true", help="Don't upload, just show changes")
    p.add_argument("--clear-other", action="store_true",
                   help="Clear all channels NOT in the CSV")
    p.set_defaults(func=cmd_upload)

    # backup
    p = subparsers.add_parser("backup", help="Download raw binary image from radio")
    p.add_argument("-p", "--port", default="/dev/ttyACM0", help="Serial port")
    p.add_argument("-o", "--output", required=True, help="Output image file")
    p.set_defaults(func=cmd_backup)

    # restore
    p = subparsers.add_parser("restore", help="Upload raw binary image to radio")
    p.add_argument("-p", "--port", default="/dev/ttyACM0", help="Serial port")
    p.add_argument("-i", "--input", required=True, help="Input image file")
    p.add_argument("--dry-run", action="store_true", help="Don't upload, just validate")
    p.set_defaults(func=cmd_restore)

    # dump (offline)
    p = subparsers.add_parser("dump", help="Offline: dump channels from image to CSV")
    p.add_argument("--image", required=True, help="Binary image file")
    p.add_argument("-o", "--output", help="Output CSV file (default: stdout)")
    p.add_argument("--skip-empty", action="store_true", default=True)
    p.add_argument("--include-empty", action="store_true")
    p.add_argument("--channels", help="Channel range")
    p.set_defaults(func=cmd_dump)

    # patch (offline)
    p = subparsers.add_parser("patch", help="Offline: apply CSV to binary image")
    p.add_argument("--image", required=True, help="Source binary image file")
    p.add_argument("-i", "--input", required=True, help="Input CSV file")
    p.add_argument("-o", "--output", required=True, help="Output binary image file")
    p.add_argument("--clear-other", action="store_true",
                   help="Clear all channels NOT in the CSV")
    p.set_defaults(func=cmd_patch)

    args = parser.parse_args()

    # handle --include-empty overriding --skip-empty
    if hasattr(args, "include_empty") and args.include_empty:
        args.skip_empty = False

    args.func(args)


if __name__ == "__main__":
    main()
