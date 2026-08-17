#!/usr/bin/env python3

import argparse
import sys
import time
import wave

import numpy as np
import sounddevice as sd


# ============================================================================
# SITOR-A / AMTOR PARAMETERS
# ============================================================================

BAUD = 100.0
BIT_TIME = 0.010

DEFAULT_SAMPLE_RATE = 48000

# 170 Hz FSK shift.
DEFAULT_MARK = 1670.0
DEFAULT_SPACE = 1500.0

DATA_SECONDS = 0.210
RESPONSE_SECONDS = 0.240
FRAME_SECONDS = 0.450


# ============================================================================
# SITOR / CCIR-476 SYMBOLS
# ============================================================================

ALPHA = 0x0F
BETA = 0x33
RQ = 0x66

CS1 = 0x65
CS2 = 0x6A
CS3 = 0x59

LETTERS_SHIFT = 0x5A
FIGURES_SHIFT = 0x36


# ============================================================================
# CCIR-476 CHARACTER TABLES
# ============================================================================

LETTERS = {
    "A": 0x47,
    "B": 0x72,
    "C": 0x1D,
    "D": 0x53,
    "E": 0x56,
    "F": 0x1B,
    "G": 0x35,
    "H": 0x69,
    "I": 0x4D,
    "J": 0x17,
    "K": 0x1E,
    "L": 0x65,
    "M": 0x39,
    "N": 0x59,
    "O": 0x71,
    "P": 0x2D,
    "Q": 0x2E,
    "R": 0x55,
    "S": 0x4B,
    "T": 0x74,
    "U": 0x4E,
    "V": 0x3C,
    "W": 0x27,
    "X": 0x3A,
    "Y": 0x2B,
    "Z": 0x63,
    " ": 0x5C,
    "\r": 0x78,
}

FIGURES = {
    "0": 0x2D,
    "1": 0x2E,
    "2": 0x27,
    "3": 0x56,
    "4": 0x55,
    "5": 0x74,
    "6": 0x2B,
    "7": 0x4E,
    "8": 0x4D,
    "9": 0x71,
    "-": 0x47,
    "'": 0x17,
    "!": 0x1B,
    "&": 0x35,
    "#": 0x69,
    "(": 0x1E,
    ")": 0x65,
    ":": 0x1D,
    ",": 0x59,
    ".": 0x39,
    "/": 0x3A,
    "?": 0x72,
    "=": 0x3C,
    "+": 0x63,
}

LETTER_DECODE = {
    value: key
    for key, value in LETTERS.items()
}

FIGURE_DECODE = {
    value: key
    for key, value in FIGURES.items()
}


# ============================================================================
# CCIR-476
# ============================================================================

def ccir_valid(symbol):
    return (
        0 <= symbol <= 0x7F
        and symbol.bit_count() == 4
    )


def symbol_to_bits(symbol):
    # LSB first (bit 0 to bit 6)
    return [
        (symbol >> bit) & 1
        for bit in range(7)
    ]


def bits_to_symbol(bits):
    value = 0
    for i, bit in enumerate(bits[:7]):
        value |= int(bit) << i
    return value


def encode_char(character, mode):
    character = character.upper()

    if character == "\n":
        character = "\r"

    if character == " ":
        return [LETTERS[" "]], mode

    if character in LETTERS:
        symbol = LETTERS[character]

        if mode != "letters":
            return [
                LETTERS_SHIFT,
                symbol,
            ], "letters"

        return [symbol], "letters"

    if character in FIGURES:
        symbol = FIGURES[character]

        if mode != "figures":
            return [
                FIGURES_SHIFT,
                symbol,
            ], "figures"

        return [symbol], "figures"

    # Unsupported character becomes ?.
    if mode != "figures":
        return [
            FIGURES_SHIFT,
            FIGURES["?"],
        ], "figures"

    return [FIGURES["?"]], "figures"


def encode_text(text):
    mode = "figures"

    for character in text:
        symbols, mode = encode_char(
            character,
            mode,
        )

        yield from symbols


def decode_symbol(symbol, mode):
    if symbol == LETTERS_SHIFT:
        return "letters", None

    if symbol == FIGURES_SHIFT:
        return "figures", None

    if symbol in {
        ALPHA,
        BETA,
        RQ,
        CS1,
        CS2,
        CS3,
    }:
        return mode, None

    if mode == "letters":
        return mode, LETTER_DECODE.get(symbol)

    return mode, FIGURE_DECODE.get(symbol)


# ============================================================================
# WAV WRITER
# ============================================================================

class WavWriter:
    def __init__(self, filename, sample_rate):
        self.file = wave.open(filename, "wb")

        self.file.setnchannels(1)
        self.file.setsampwidth(2)
        self.file.setframerate(sample_rate)

    def write(self, samples):
        samples = np.asarray(
            samples,
            dtype=np.float32,
        )

        samples = np.clip(
            samples,
            -1.0,
            1.0,
        )

        pcm = (
            samples * 32767.0
        ).astype(np.int16)

        self.file.writeframes(
            pcm.tobytes()
        )

    def close(self):
        self.file.close()


# ============================================================================
# PTT
# ============================================================================

class RTSPTT:
    def __init__(
        self,
        device,
        active_high=True,
    ):
        try:
            import serial
        except ImportError:
            raise RuntimeError(
                "pyserial is required for RTS PTT. "
                "Install it with:\n"
                "python3 -m pip install pyserial"
            )

        self.serial = serial.Serial(
            device,
            baudrate=9600,
            timeout=0,
        )

        self.active_high = active_high

    def on(self):
        self.serial.rts = self.active_high

    def off(self):
        self.serial.rts = not self.active_high

    def close(self):
        self.serial.close()


# ============================================================================
# TRANSMITTER
# ============================================================================

class SITORTransmitter:
    def __init__(
        self,
        sample_rate,
        mark,
        space,
        amplitude,
        ptt=None,
        reverse=False,
    ):
        self.sample_rate = sample_rate
        if reverse:
            self.mark = space
            self.space = mark
        else:
            self.mark = mark
            self.space = space
        self.amplitude = amplitude
        self.ptt = ptt

        samples_per_bit = sample_rate / BAUD

        if not samples_per_bit.is_integer():
            raise ValueError(
                "Sample rate must be divisible by 100."
            )

        self.samples_per_bit = int(
            samples_per_bit
        )

        self.data_samples = int(
            round(
                DATA_SECONDS
                * sample_rate
            )
        )

        self.response_samples = int(
            round(
                RESPONSE_SECONDS
                * sample_rate
            )
        )

        self.frame_samples = (
            self.data_samples
            + self.response_samples
        )

    # ------------------------------------------------------------------------
    # Audio generation
    # ------------------------------------------------------------------------

    def make_bit(self, bit):
        frequency = (
            self.mark
            if bit
            else self.space
        )

        n = self.samples_per_bit

        t = (
            np.arange(n, dtype=np.float64)
            / self.sample_rate
        )

        audio = (
            self.amplitude
            * np.sin(
                2.0
                * np.pi
                * frequency
                * t
            )
        )

        # Tiny edge ramps to avoid clicks.
        ramp = min(
            int(
                self.sample_rate * 0.001
            ),
            n // 4,
        )

        if ramp:
            audio[:ramp] *= np.linspace(
                0.0,
                1.0,
                ramp,
            )

            audio[-ramp:] *= np.linspace(
                1.0,
                0.0,
                ramp,
            )

        return audio.astype(
            np.float32
        )

    def make_symbol(self, symbol):
        if not ccir_valid(symbol):
            raise ValueError(
                f"Invalid CCIR-476 symbol "
                f"0x{symbol:02X}"
            )

        return np.concatenate([
            self.make_bit(bit)
            for bit in symbol_to_bits(symbol)
        ])

    def make_block(self, symbols):
        if len(symbols) != 3:
            raise ValueError(
                "SITOR-A requires exactly "
                "3 symbols per data block."
            )

        audio = np.concatenate([
            self.make_symbol(symbol)
            for symbol in symbols
        ])

        if len(audio) != self.data_samples:
            raise RuntimeError(
                "Internal timing error: "
                "data block is not exactly 210 ms."
            )

        return audio

    def make_frame(self, symbols):
        data = self.make_block(symbols)

        # The response window is represented as silence in the WAV.
        silence = np.zeros(
            self.response_samples,
            dtype=np.float32,
        )

        frame = np.concatenate([
            data,
            silence,
        ])

        if len(frame) != self.frame_samples:
            raise RuntimeError(
                "Internal timing error: "
                "frame is not exactly 450 ms."
            )

        return frame

    # ------------------------------------------------------------------------
    # Message preparation
    # ------------------------------------------------------------------------

    def encode_blocks(self, text):
        symbols = list(
            encode_text(text)
        )

        # Pad to a complete three-symbol block.
        while len(symbols) % 3:
            symbols.append(BETA)

        blocks = [
            symbols[pos:pos + 3]
            for pos in range(
                0,
                len(symbols),
                3,
            )
        ]

        return blocks

    def make_message_wav(self, text):
        """
        Construct the ENTIRE WAV waveform in advance.
        """
        blocks = self.encode_blocks(text)

        if not blocks:
            return (
                np.empty(0, dtype=np.float32),
                blocks,
            )

        frames = [
            self.make_frame(block)
            for block in blocks
        ]

        audio = np.concatenate(frames)

        expected_samples = (
            len(blocks)
            * self.frame_samples
        )

        if len(audio) != expected_samples:
            raise RuntimeError(
                "Internal timing error: "
                f"generated {len(audio)} samples, "
                f"expected {expected_samples}."
            )

        return audio, blocks

    # ------------------------------------------------------------------------
    # Actual RF/audio transmission
    # ------------------------------------------------------------------------

    def transmit_data(self, audio):
        if self.ptt is not None:
            self.ptt.on()

        try:
            sd.play(
                audio,
                self.sample_rate,
                blocking=True,
            )
        finally:
            if self.ptt is not None:
                self.ptt.off()

    def transmit_block(self, block):
        """
        Transmit only the 210 ms data portion.
        """
        audio = self.make_block(block)

        if self.ptt is not None:
            self.ptt.on()

        try:
            sd.play(
                audio,
                self.sample_rate,
                blocking=True,
            )
        finally:
            if self.ptt is not None:
                self.ptt.off()

    # ------------------------------------------------------------------------
    # Blind/no-ACK transmission
    # ------------------------------------------------------------------------

    def transmit_no_ack(
        self,
        audio,
        verbose=False,
    ):
        if verbose:
            print(
                "[TX] transmitting continuous audio waveform",
                file=sys.stderr,
            )

        if self.ptt is not None:
            self.ptt.on()

        try:
            sd.play(
                audio,
                self.sample_rate,
                blocking=True,
            )
        finally:
            if self.ptt is not None:
                self.ptt.off()

    # ------------------------------------------------------------------------
    # ACK-driven transmission
    # ------------------------------------------------------------------------

    def transmit_arq(
        self,
        blocks,
        receiver,
        verbose=False,
        ack_timeout=0.240,
    ):
        expected_ack = CS1

        receiver.start()

        try:
            for index, block in enumerate(blocks):

                while True:
                    if verbose:
                        print(
                            f"[TX {index + 1}/{len(blocks)}] "
                            + " ".join(
                                f"{symbol:02X}"
                                for symbol in block
                            ),
                            file=sys.stderr,
                        )

                    cycle_start = time.monotonic()

                    self.transmit_block(block)

                    elapsed = (
                        time.monotonic()
                        - cycle_start
                    )

                    ack = receiver.wait_for_control(
                        timeout=max(
                            0.0,
                            ack_timeout
                            - max(
                                0.0,
                                elapsed
                                - DATA_SECONDS,
                            ),
                        ),
                    )

                    if ack == expected_ack:
                        if verbose:
                            print(
                                f"[ARQ] received "
                                f"CS{1 if expected_ack == CS1 else 2}",
                                file=sys.stderr,
                            )

                        expected_ack = (
                            CS2
                            if expected_ack == CS1
                            else CS1
                        )

                        total_elapsed = (
                            time.monotonic()
                            - cycle_start
                        )

                        remaining = (
                            FRAME_SECONDS
                            - total_elapsed
                        )

                        if remaining > 0:
                            time.sleep(
                                remaining
                            )

                        break

                    if verbose:
                        print(
                            "[ARQ] ACK missing or repeat requested; "
                            "retransmitting block",
                            file=sys.stderr,
                        )

                    total_elapsed = (
                        time.monotonic()
                        - cycle_start
                    )

                    remaining = (
                        FRAME_SECONDS
                        - total_elapsed
                    )

                    if remaining > 0:
                        time.sleep(
                            remaining
                        )

        finally:
            receiver.stop()


# ============================================================================
# RECEIVER
# ============================================================================

class SITORReceiver:
    def __init__(
        self,
        sample_rate,
        mark,
        space,
        wav=None,
        reverse=False,
    ):
        self.sample_rate = sample_rate
        if reverse:
            self.mark = space
            self.space = mark
        else:
            self.mark = mark
            self.space = space
        self.wav = wav

        samples_per_bit = (
            sample_rate / BAUD
        )

        if not samples_per_bit.is_integer():
            raise ValueError(
                "Sample rate must be divisible by 100."
            )

        self.samples_per_bit = int(
            samples_per_bit
        )

        self.buffer = np.empty(
            0,
            dtype=np.float32,
        )

        self.stream = None

    def callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ):
        if status:
            print(
                f"[audio] {status}",
                file=sys.stderr,
            )

        samples = np.asarray(
            indata[:, 0],
            dtype=np.float32,
        ).copy()

        if self.wav is not None:
            self.wav.write(samples)

        self.buffer = np.concatenate(
            (
                self.buffer,
                samples,
            )
        )

    @staticmethod
    def tone_power(
        samples,
        frequency,
        sample_rate,
    ):
        if len(samples) == 0:
            return 0.0

        x = (
            samples
            - np.mean(samples)
        )

        n = np.arange(
            len(x),
            dtype=np.float64,
        )

        omega = (
            2.0
            * np.pi
            * frequency
            / sample_rate
        )

        sin_ref = np.sin(
            omega * n
        )

        cos_ref = np.cos(
            omega * n
        )

        i = np.dot(
            x,
            cos_ref,
        )

        q = np.dot(
            x,
            sin_ref,
        )

        return (
            i * i
            + q * q
        )

    def demodulate_bit(self, samples):
        mark_power = self.tone_power(
            samples,
            self.mark,
            self.sample_rate,
        )

        space_power = self.tone_power(
            samples,
            self.space,
            self.sample_rate,
        )

        return (
            1
            if mark_power >= space_power
            else 0
        )

    def get_bits(self):
        complete_bits = (
            len(self.buffer)
            // self.samples_per_bit
        )

        if complete_bits <= 0:
            return []

        sample_count = (
            complete_bits
            * self.samples_per_bit
        )

        data = self.buffer[
            :sample_count
        ]

        self.buffer = self.buffer[
            sample_count:
        ]

        bits = []

        for index in range(
            complete_bits
        ):
            start = (
                index
                * self.samples_per_bit
            )

            stop = (
                start
                + self.samples_per_bit
            )

            bits.append(
                self.demodulate_bit(
                    data[start:stop]
                )
            )

        return bits

    def start(self):
        if self.stream is not None:
            return

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=(
                self.samples_per_bit
                * 5
            ),
            callback=self.callback,
        )

        self.stream.start()

    def stop(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def get_symbol(self, timeout):
        deadline = (
            time.monotonic()
            + timeout
        )

        bits = []

        while time.monotonic() < deadline:
            new_bits = self.get_bits()

            if new_bits:
                bits.extend(new_bits)

            if len(bits) >= 7:
                symbol = bits_to_symbol(
                    bits[:7]
                )

                if ccir_valid(symbol):
                    return symbol

                # Try to recover alignment by shifting one bit.
                bits.pop(0)

            time.sleep(0.002)

        return None

    def wait_for_control(self, timeout):
        """
        Wait for a single 7-bit CS1/CS2/RQ symbol.
        """
        deadline = (
            time.monotonic()
            + timeout
        )

        bits = []

        while time.monotonic() < deadline:
            bits.extend(
                self.get_bits()
            )

            while len(bits) >= 7:
                symbol = bits_to_symbol(
                    bits[:7]
                )

                del bits[:7]

                if not ccir_valid(symbol):
                    continue

                if symbol in {
                    CS1,
                    CS2,
                    CS3,
                    RQ,
                }:
                    return symbol

            time.sleep(0.002)

        return None


# ============================================================================
# RECEIVE DECODER
# ============================================================================

class ReceiveDecoder:
    def __init__(
        self,
        receiver,
        verbose=False,
    ):
        self.receiver = receiver
        self.verbose = verbose

        self.bits = []
        self.mode = "letters"

    def process(self):
        new_bits = self.receiver.get_bits()

        if new_bits:
            self.bits.extend(
                new_bits
            )

        while len(self.bits) >= 7:
            symbol = bits_to_symbol(
                self.bits[:7]
            )

            del self.bits[:7]

            if not ccir_valid(symbol):
                continue

            self.process_symbol(symbol)

    def process_symbol(self, symbol):
        if symbol in {
            ALPHA,
            BETA,
            RQ,
            CS1,
            CS2,
            CS3,
        }:
            if self.verbose:
                print(
                    f"\n[CONTROL 0x{symbol:02X}]",
                    file=sys.stderr,
                )
            return

        self.mode, character = (
            decode_symbol(
                symbol,
                self.mode,
            )
        )

        if character is not None:
            sys.stdout.write(character)
            sys.stdout.flush()

    def run(self):
        self.receiver.start()

        print(
            "[SITOR-A RX] listening",
            file=sys.stderr,
        )

        try:
            while True:
                self.process()
                time.sleep(0.005)

        except KeyboardInterrupt:
            pass

        finally:
            self.receiver.stop()


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "SITOR-A / AMTOR ARQ sound-card modem"
        )
    )

    parser.add_argument(
        "--list-devices",
        action="store_true",
    )

    parser.add_argument(
        "--rx",
        action="store_true",
        help="receive SITOR-A",
    )

    parser.add_argument(
        "--tx",
        metavar="MESSAGE",
        help="transmit MESSAGE",
    )

    parser.add_argument(
        "--no-ack",
        action="store_true",
        help=(
            "TX only: transmit the entire message "
            "without waiting for ACKs"
        ),
    )

    parser.add_argument(
        "--input",
        type=int,
        default=None,
        help="sound-card input device",
    )

    parser.add_argument(
        "--output",
        type=int,
        default=None,
        help="sound-card output device",
    )

    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help="sample rate, default 48000",
    )

    parser.add_argument(
        "--mark",
        type=float,
        default=DEFAULT_MARK,
        help="mark frequency, default 1670 Hz",
    )

    parser.add_argument(
        "--space",
        type=float,
        default=DEFAULT_SPACE,
        help="space frequency, default 1500 Hz",
    )

    parser.add_argument(
        "--amplitude",
        type=float,
        default=0.5,
        help="TX audio amplitude, default 0.5",
    )

    parser.add_argument(
        "--record-wav",
        metavar="FILE.WAV",
        help=(
            "record RX audio, or on TX save the exact "
            "generated 450-ms-frame waveform"
        ),
    )

    parser.add_argument(
        "--reverse",
        action="store_true",
        help="swap mark and space frequencies (polarity reverse)",
    )

    parser.add_argument(
        "--ptt-device",
        metavar="DEVICE",
        help="serial device for RTS PTT",
    )

    parser.add_argument(
        "--ptt-active-low",
        action="store_true",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
    )

    args = parser.parse_args()

    if args.list_devices:
        devices = sd.query_devices()

        for index, device in enumerate(devices):
            print(
                f"{index}: "
                f"{device['name']} "
                f"(in={device['max_input_channels']}, "
                f"out={device['max_output_channels']})"
            )

        return

    if args.rx and args.tx:
        parser.error(
            "--rx and --tx cannot be used together."
        )

    if args.no_ack and not args.tx:
        parser.error(
            "--no-ack requires --tx."
        )

    if not args.rx and not args.tx:
        parser.error(
            "Specify either --rx or --tx MESSAGE."
        )

    # ========================================================================
    # RX
    # ========================================================================

    if args.rx:
        if args.input is None:
            parser.error(
                "--rx requires --input."
            )

        wav = None

        try:
            if args.record_wav:
                wav = WavWriter(
                    args.record_wav,
                    args.sample_rate,
                )

            receiver = SITORReceiver(
                sample_rate=args.sample_rate,
                mark=args.mark,
                space=args.space,
                wav=wav,
                reverse=args.reverse,
            )

            ReceiveDecoder(
                receiver,
                verbose=args.verbose,
            ).run()

        finally:
            if wav is not None:
                wav.close()

        return

    # ========================================================================
    # TX
    # ========================================================================

    if args.tx:
        if args.output is None:
            parser.error(
                "--tx requires --output."
            )

        ptt = None
        wav = None

        try:
            if args.ptt_device:
                ptt = RTSPTT(
                    args.ptt_device,
                    active_high=not args.ptt_active_low,
                )

            transmitter = SITORTransmitter(
                sample_rate=args.sample_rate,
                mark=args.mark,
                space=args.space,
                amplitude=args.amplitude,
                ptt=ptt,
                reverse=args.reverse,
            )

            audio, blocks = (
                transmitter.make_message_wav(
                    args.tx
                )
            )

            block_count = len(blocks)

            expected_samples = (
                block_count
                * transmitter.frame_samples
            )

            if len(audio) != expected_samples:
                raise RuntimeError(
                    "Generated audio length mismatch: "
                    f"{len(audio)} samples generated, "
                    f"{expected_samples} expected "
                    f"for {block_count} blocks."
                )

            actual_seconds = (
                len(audio)
                / args.sample_rate
            )

            expected_seconds = (
                block_count
                * FRAME_SECONDS
            )

            if abs(
                actual_seconds
                - expected_seconds
            ) > (
                1.0 / args.sample_rate
            ):
                raise RuntimeError(
                    "Generated audio duration mismatch: "
                    f"{actual_seconds:.6f}s generated, "
                    f"{expected_seconds:.6f}s expected."
                )

            if args.verbose:
                print(
                    f"[TX] {block_count} blocks",
                    file=sys.stderr,
                )

                print(
                    f"[TX] {actual_seconds:.3f} seconds",
                    file=sys.stderr,
                )

            if args.record_wav:
                wav = WavWriter(
                    args.record_wav,
                    args.sample_rate,
                )

                wav.write(audio)
                wav.close()
                wav = None

            if args.no_ack:
                if args.verbose:
                    print(
                        "[TX] blind mode: "
                        "ACK/RQ disabled",
                        file=sys.stderr,
                    )

                transmitter.transmit_no_ack(
                    audio,
                    verbose=args.verbose,
                )

                return

            if args.input is None:
                parser.error(
                    "Normal --tx requires --input for "
                    "ACK reception. Use --no-ack if "
                    "no receive device is available."
                )

            receiver = SITORReceiver(
                sample_rate=args.sample_rate,
                mark=args.mark,
                space=args.space,
                reverse=args.reverse,
            )

            if args.verbose:
                print(
                    "[TX] ARQ mode: waiting for CS1/CS2",
                    file=sys.stderr,
                )

            transmitter.transmit_arq(
                blocks,
                receiver,
                verbose=args.verbose,
            )

        finally:
            if wav is not None:
                wav.close()

            if ptt is not None:
                try:
                    ptt.off()
                finally:
                    ptt.close()

        return


if __name__ == "__main__":
    main()
