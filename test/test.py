# SPDX-License-Identifier: Apache-2.0
# Protocol tests for tt_um_janestreet_emulator. Every check decodes real pin activity.
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from asm import assemble

HERE = os.path.dirname(os.path.abspath(__file__))
HALF = 8          # clk cycles per host SCK half period (clk must be >= 4x SCK)

A_ID, A_CTRL, A_STATUS, A_TXDATA, A_RXDATA, A_CLKDIV = 0, 1, 2, 3, 4, 5
A_GPIO_LO, A_GPIO_HI, A_WRAP_BOT, A_WRAP_TOP = 0x09, 0x0A, 0x0D, 0x0E
A_IMEM_ADDR, A_IMEM_LO, A_IMEM_HI = 0x11, 0x12, 0x13
RUN_CLEAR = 0x05  # CTRL: run + soft clear, FIFOs owned by the engine (uart_mode = 0)


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    dut.ena.value = 1
    dut.cs_n.value = 1
    dut.sck.value = 0
    dut.mosi.value = 0
    dut.pins_in.value = 0x1F
    dut.uio_ext.value = 0xFF
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


async def spi(dut, rw, addr, data=0):
    """One 16-bit host frame {rw, addr[6:0], data[7:0]}, mode 0, MSB first."""
    word = (rw << 15) | (addr << 8) | data
    rdv = 0
    dut.cs_n.value = 0
    await ClockCycles(dut.clk, HALF)
    for i in range(16):
        dut.mosi.value = (word >> (15 - i)) & 1
        await ClockCycles(dut.clk, HALF)
        if i >= 8:
            rdv = (rdv << 1) | (int(dut.uo_out.value) & 1)
        dut.sck.value = 1
        await ClockCycles(dut.clk, HALF)
        dut.sck.value = 0
    await ClockCycles(dut.clk, HALF)
    dut.cs_n.value = 1
    await ClockCycles(dut.clk, HALF)
    return rdv


async def wr(dut, addr, data):
    await spi(dut, 0, addr, data)


async def rd(dut, addr):
    return await spi(dut, 1, addr)


async def load_text(dut, text, name="<inline>"):
    words, wb, wt = assemble(text, name)
    await wr(dut, A_IMEM_ADDR, 0)
    for w in words:
        await wr(dut, A_IMEM_LO, w & 0xFF)
        await wr(dut, A_IMEM_HI, w >> 8)
    await wr(dut, A_WRAP_BOT, wb)
    await wr(dut, A_WRAP_TOP, wt)


PROGRAMS = {
    "uart_tx.asm": """
; Bit-banged UART transmitter, 8N1, LSB first.  TX on uio[0] (pin 0).
; Timing: 50 steps per bit  ->  baud = clk / ((CLKDIV+1) * 50)
; Host: write CLKDIV, WRAP_BOT/TOP (from this file), load, push bytes to TXDATA, run.
.equ TX 0
    SETOE 0x01              ; uio[0] output
    SETP  TX, 1             ; idle high
.wrap_bot
    PULL                    ; wait for a byte -> OSR
    SETP  TX, 0             ; start bit
    DLY   47                ; 48 steps
    SETX  7                 ; 8 data bits
bit:
    OUT   TX                ; LSB first
    DLY   47
    JMP   XNZ, bit          ; OUT(1)+DLY(48)+JMP(1) = 50 steps per bit
    SETP  TX, 1             ; stop bit
    DLY   48                ; 50 steps
.wrap_top
""",
    "uart_rx.asm": """
; Bit-banged UART receiver, 8N1, LSB first.  RX on pin 8 (ui_in[3]).
; Samples each bit in the middle (50 steps per bit), pushes received bytes to RXDATA.
.equ RX 8
.wrap_bot
    WAITP RX, 0             ; wait for start bit
    DLY   71                ; skip to the centre of bit 0
    SETX  7
bit:
    IN    RX                ; sample (LSB first)
    DLY   47
    JMP   XNZ, bit          ; 1+48+1 = 50 steps per bit
    PUSH                    ; ~middle of the stop bit
    WAITP RX, 1             ; wait for the line to go idle
.wrap_top
""",
    "spi_master_mode0.asm": """
; SPI master, mode 0 (CPOL=0 CPHA=0), MSB first, 8-bit transfers.
; Pins: SCLK = out 8 (uo_out[1]), MOSI = out 9 (uo_out[2]), CS_N = out 10 (uo_out[3]),
;       MISO = in 8 (ui_in[3]).
; Host: queue bytes in TXDATA, run.  Each received byte is pushed to RXDATA.
; CS_N stays low while more bytes are waiting in the TX FIFO, so queue a whole
; transaction before starting the engine.   SCLK = clk / ((CLKDIV+1) * 17 steps).
.equ SCLK 8
.equ MOSI 9
.equ CS   10
.equ MISO 8
    SETP CS, 1
    SETP SCLK, 0
.wrap_bot
    PULL                    ; first byte of a transaction
    SETP CS, 0
    DLY  3                  ; CS setup
byte:
    SETX 7
bit:
    OUT  MOSI, MSB          ; data changes while SCLK is low
    DLY  6                  ; setup
    SETP SCLK, 1            ; rising edge: slave samples MOSI
    IN   MISO, MSB          ; master samples MISO
    DLY  4
    SETP SCLK, 0            ; falling edge
    JMP  XNZ, bit
    PUSH                    ; received byte
    JMP  TXE, done          ; nothing more queued -> end transaction
    PULL
    JMP  ALWAYS, byte
done:
    DLY  3                  ; CS hold
    SETP CS, 1
.wrap_top
""",
    "spi_master_mode3.asm": """
; SPI master, mode 3 (CPOL=1 CPHA=1), MSB first.  Same pins and host protocol as mode 0.
.equ SCLK 8
.equ MOSI 9
.equ CS   10
.equ MISO 8
    SETP CS, 1
    SETP SCLK, 1            ; idle high
.wrap_bot
    PULL
    SETP CS, 0
    DLY  3
byte:
    SETX 7
bit:
    SETP SCLK, 0            ; falling edge: slave shifts out the next MISO bit
    OUT  MOSI, MSB          ; MOSI changes after the falling edge
    DLY  6
    SETP SCLK, 1            ; rising edge: both sides sample
    IN   MISO, MSB
    DLY  4
    JMP  XNZ, bit
    PUSH
    JMP  TXE, done
    PULL
    JMP  ALWAYS, byte
done:
    DLY  3
    SETP CS, 1
.wrap_top
""",
    "i2c_wr.asm": """
; I2C master: (repeated) START + send bytes.  SDA = uio[0] (pin 0), SCL = uio[1] (pin 1),
; both open-drain: the engine only ever drives them low or releases them (SETD / OUT od),
; clock stretching is honoured by WAITP SCL.
;
; TX FIFO: first byte = (7-bit address << 1) | R/W, then data bytes. Natural bit order.
; For every byte sent one status byte is pushed to RXDATA: 0x00 = ACK, 0x80 = NACK.
; On NACK the transaction is aborted and the rest of the TX FIFO is flushed.
; Ends with HALT; the bus stays claimed (SCL low) so that another program can continue
; (i2c_rd.asm, i2c_stop.asm, or i2c_wr.asm again for a repeated START).
; 5 steps per SCL period: SCL = clk / ((CLKDIV+1) * 5).
.equ SDA 0
.equ SCL 1
    PULL                    ; address byte -> OSR
    SETD SDA, 1             ; make sure both lines are released (repeated START prep)
    SETD SCL, 1
    WAITP SCL, 1
    DLY  1
    SETD SDA, 0             ; START: SDA falls while SCL is high
    DLY  1
    SETD SCL, 0
byte:
    SETX 7
bit:
    OUT  SDA, MSB, OD       ; SDA = OSR[7] (drive low or release)
    SETD SCL, 1
    WAITP SCL, 1            ; clock stretching
    SETD SCL, 0
    JMP  XNZ, bit
    SETD SDA, 1             ; release SDA for the ACK slot
    SETD SCL, 1
    WAITP SCL, 1
    SETI 0
    IN   SDA                ; ISR[7] = ACK bit (0 = ACK)
    PUSH                    ; report 0x00 / 0x80
    JMPH SDA, nack          ; SDA still high -> NACK
    SETD SCL, 0
    JMP  TXE, done
    PULL
    JMP  ALWAYS, byte
nack:
    SETD SCL, 0
flush:
    JMP  TXE, done
    PULL
    JMP  ALWAYS, flush
done:
    HALT
""",
    "i2c_rd.asm": """
; I2C master: read bytes.  Continues after i2c_wr.asm sent an address byte with R/W=1
; (bus claimed, SCL low).  TX FIFO: one dummy byte per byte to read.
; Every received byte is pushed to RXDATA (MSB first, natural order).
; All bytes are ACKed except the last one (NACK), then HALT; use i2c_stop.asm next.
.equ SDA 0
.equ SCL 1
rbyte:
    PULL                    ; consume one token
    SETX 7
rbit:
    SETD SCL, 1
    WAITP SCL, 1            ; clock stretching
    IN   SDA, MSB
    SETD SCL, 0
    JMP  XNZ, rbit
    PUSH
    JMP  TXE, nackbyte      ; no more tokens: this was the last byte
    SETD SDA, 0             ; ACK
    JMP  ALWAYS, ackclk
nackbyte:
    SETD SDA, 1             ; NACK (released)
ackclk:
    SETD SCL, 1
    WAITP SCL, 1
    SETD SCL, 0
    SETD SDA, 1             ; release SDA
    JMP  TXE, done
    JMP  ALWAYS, rbyte
done:
    HALT
""",
    "i2c_stop.asm": """
; I2C master: STOP condition (bus must be claimed: SCL low).
.equ SDA 0
.equ SCL 1
    SETD SDA, 0             ; SDA low while SCL is low
    SETD SCL, 1
    WAITP SCL, 1
    DLY  1
    SETD SDA, 1             ; SDA rises while SCL is high = STOP
    DLY  3                  ; bus free time
    HALT
""",
}


async def load(dut, name):
    await load_text(dut, PROGRAMS[name], name)

async def wait_halt(dut, polls=400):
    for _ in range(polls):
        if (await rd(dut, A_STATUS)) & 0x80 == 0:
            return
    raise AssertionError("engine did not halt")


async def drain_rx(dut, n):
    return [await rd(dut, A_RXDATA) for _ in range(n)]


async def uart_capture(dut, bit_clks, getbit, timeout=400000):
    """Wait for a start bit, sample 8N1 at mid-bit, return the byte."""
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if getbit() == 0:
            break
    else:
        raise AssertionError("no start bit seen")
    await ClockCycles(dut.clk, bit_clks + bit_clks // 2)
    val = 0
    for i in range(8):
        val |= getbit() << i
        await ClockCycles(dut.clk, bit_clks)
    assert getbit() == 1, "missing stop bit"
    return val


async def uart_send(dut, byte, bit_clks):
    for b in [0] + [(byte >> i) & 1 for i in range(8)] + [1]:
        dut.pins_in.value = 0x1E | b          # ui_in[3] = pin 8
        await ClockCycles(dut.clk, bit_clks)


@cocotb.test()
async def test_host_registers(dut):
    await reset(dut)
    assert await rd(dut, A_ID) == 0xE1
    await wr(dut, A_CLKDIV, 0x5A)
    assert await rd(dut, A_CLKDIV) == 0x5A
    await wr(dut, A_WRAP_TOP, 0x0B)
    assert await rd(dut, A_WRAP_TOP) == 0x0B
    await wr(dut, A_IMEM_ADDR, 3)
    await wr(dut, A_IMEM_LO, 0x12)
    await wr(dut, A_IMEM_HI, 0x34)
    assert await rd(dut, A_IMEM_ADDR) == 4          # pointer auto-increments


@cocotb.test()
async def test_hardwired_uart(dut):
    await reset(dut)
    bit = 217                                       # 25 MHz / 115200 as built in project.v
    pad = lambda: (int(dut.uo_out.value) >> 1) & 1  # TX = uo_out[1]
    await wr(dut, A_CTRL, 0x02)                     # uart_mode
    await wr(dut, A_TXDATA, 0xA6)
    assert await uart_capture(dut, bit, pad) == 0xA6
    await wr(dut, A_TXDATA, 0x3D)
    assert await uart_capture(dut, bit, pad) == 0x3D
    await uart_send(dut, 0x6B, bit)                 # RX = ui_in[3]
    dut.pins_in.value = 0x1F
    await ClockCycles(dut.clk, 3 * bit)
    assert await rd(dut, A_RXDATA) == 0x6B


@cocotb.test()
async def test_engine_uart_tx(dut):
    await reset(dut)
    await wr(dut, A_GPIO_LO, 0x01)                  # TX (uio[0]) idles high before the program drives it
    await wr(dut, A_CLKDIV, 0)                      # 50 steps per bit -> 50 clk per bit
    await load(dut, "uart_tx.asm")
    for b in (0xA6, 0x01, 0x9E):
        await wr(dut, A_TXDATA, b)
    await wr(dut, A_CTRL, RUN_CLEAR)
    pad = lambda: int(dut.uio_in.value) & 1
    got = [await uart_capture(dut, 50, pad) for _ in range(3)]
    assert got == [0xA6, 0x01, 0x9E]
    await wr(dut, A_CTRL, 0x00)


@cocotb.test()
async def test_engine_uart_rx(dut):
    await reset(dut)
    await wr(dut, A_CLKDIV, 0)
    await load(dut, "uart_rx.asm")
    await wr(dut, A_CTRL, RUN_CLEAR)
    await ClockCycles(dut.clk, 200)
    for byte in (0x6B, 0xC4, 0x01, 0xFE):
        await uart_send(dut, byte, 50)
        dut.pins_in.value = 0x1F
        await ClockCycles(dut.clk, 120)
    await wr(dut, A_CTRL, 0x00)
    assert await drain_rx(dut, 4) == [0x6B, 0xC4, 0x01, 0xFE]


async def spi_slave(dut, miso_bytes, mode, frames):
    """SPI slave: CS_N = uo_out[3], SCLK = uo_out[1], MOSI = uo_out[2], MISO = ui_in[3]."""
    cs_p, sck_p, bits, nfall = 1, (0 if mode == 0 else 1), [], 0

    def drive(k):
        byte = miso_bytes[k // 8] if k // 8 < len(miso_bytes) else 0
        dut.pins_in.value = 0x1E | ((byte >> (7 - k % 8)) & 1)

    while True:
        await RisingEdge(dut.clk)
        o = int(dut.uo_out.value)
        sck, mosi, cs = (o >> 1) & 1, (o >> 2) & 1, (o >> 3) & 1
        if cs_p == 1 and cs == 0:
            bits, nfall = [], 0
            drive(0)
        if cs == 0:
            if sck_p == 0 and sck == 1:
                bits.append(mosi)
            if sck_p == 1 and sck == 0:
                nfall += 1
                drive(nfall if mode == 0 else nfall - 1)
        if cs_p == 0 and cs == 1:
            frames.append(list(bits))
            dut.pins_in.value = 0x1F
        cs_p, sck_p = cs, sck


def bits_to_bytes(bits):
    assert len(bits) % 8 == 0, "bit count %d is not a multiple of 8" % len(bits)
    return [sum(b << (7 - k) for k, b in enumerate(bits[i:i + 8])) for i in range(0, len(bits), 8)]


async def run_spi(dut, prog, mode):
    await reset(dut)
    tx, miso = [0x9F, 0x01, 0xC3], [0x5B, 0xA2, 0x3D]   # none is a bit-palindrome
    frames = []
    await wr(dut, A_GPIO_HI, 0x04 if mode == 0 else 0x05)    # CS high, SCLK idle level
    slave = cocotb.start_soon(spi_slave(dut, miso, mode, frames))
    await wr(dut, A_CLKDIV, 1)
    await load(dut, prog)
    for b in tx:
        await wr(dut, A_TXDATA, b)
    await wr(dut, A_CTRL, RUN_CLEAR)
    for _ in range(400):
        if frames:
            break
        await ClockCycles(dut.clk, 100)
    assert len(frames) == 1, "no complete transaction"
    assert bits_to_bytes(frames[0]) == tx
    await wr(dut, A_CTRL, 0x00)
    slave.cancel()
    assert await drain_rx(dut, 3) == miso


@cocotb.test()
async def test_spi_master_mode0(dut):
    await run_spi(dut, "spi_master_mode0.asm", 0)


@cocotb.test()
async def test_spi_master_mode3(dut):
    await run_spi(dut, "spi_master_mode3.asm", 3)


class I2CSlave:
    """Minimal I2C slave. SDA = uio[0], SCL = uio[1]; pulls SDA low through uio_ext."""

    def __init__(self, dut, ack=True, read_data=()):
        self.dut, self.ack, self.read = dut, ack, list(read_data)
        self.phase, self.n, self.bits, self.rw = "idle", 0, [], 0
        self.got, self.start, self.stop, self.master_acks = [], 0, 0, []
        self.cur, self.ri = 0, 0

    def drive(self, v):
        self.dut.uio_ext.value = 0xFF if v else 0xFE

    def lines(self):
        d = self.dut
        out, oe, ext = int(d.uio_out.value), int(d.uio_oe.value), int(d.uio_ext.value)
        pad = (out & oe) | (ext & ~oe & 0xFF)
        return (pad >> 1) & 1, pad & 1          # scl, sda

    def begin_rd_byte(self):
        self.cur = self.read[self.ri] if self.ri < len(self.read) else 0xFF
        self.ri += 1
        self.drive((self.cur >> 7) & 1)

    def on_rise(self, sda):
        self.n += 1
        if self.phase in ("addr", "wr") and self.n <= 8:
            self.bits.append(sda)
        elif self.phase == "rd" and self.n == 9:
            self.master_acks.append(sda == 0)

    def on_fall(self):
        if self.phase in ("addr", "wr"):
            if self.n == 8:
                byte = sum(b << (7 - k) for k, b in enumerate(self.bits))
                self.got.append(byte)
                if self.phase == "addr":
                    self.rw = byte & 1
                self.drive(0 if self.ack else 1)
            elif self.n == 9:
                self.drive(1)
                self.bits, self.n = [], 0
                if self.phase == "addr":
                    self.phase = "rd" if (self.rw and self.ack) else "wr"
                    if self.phase == "rd":
                        self.begin_rd_byte()
        elif self.phase == "rd":
            if 0 < self.n < 8:
                self.drive((self.cur >> (7 - self.n)) & 1)
            elif self.n == 8:
                self.drive(1)
            elif self.n == 9:
                self.n = 0
                if self.master_acks[-1]:
                    self.begin_rd_byte()
                else:
                    self.phase = "idle"
                    self.drive(1)

    async def run(self):
        prev = (1, 1)
        while True:
            await RisingEdge(self.dut.clk)
            scl, sda = self.lines()
            psc, psd = prev
            if psc and scl and psd and not sda:
                self.start += 1
                self.phase, self.n, self.bits = "addr", 0, []
                self.drive(1)
            elif psc and scl and not psd and sda:
                self.stop += 1
                self.phase = "idle"
                self.drive(1)
            elif self.phase != "idle":
                if not psc and scl:
                    self.on_rise(sda)
                if psc and not scl:
                    self.on_fall()
            prev = (scl, sda)


async def i2c_run(dut, prog, tx):
    for b in tx:
        await wr(dut, A_TXDATA, b)
    await load(dut, prog)
    await wr(dut, A_CTRL, RUN_CLEAR)
    await wait_halt(dut)


async def i2c_setup(dut, ack=True, read_data=()):
    await reset(dut)
    slave = I2CSlave(dut, ack, read_data)
    cocotb.start_soon(slave.run())
    await wr(dut, A_CLKDIV, 3)
    return slave


@cocotb.test()
async def test_i2c_write_ack_and_stop(dut):
    s = await i2c_setup(dut)
    await i2c_run(dut, "i2c_wr.asm", [0xA0, 0x3C, 0x55])
    assert s.start == 1 and s.stop == 0               # bus stays claimed after the write
    assert s.got == [0xA0, 0x3C, 0x55]
    assert await drain_rx(dut, 3) == [0x00, 0x00, 0x00]
    await i2c_run(dut, "i2c_stop.asm", [])
    assert s.stop == 1


@cocotb.test()
async def test_i2c_write_nack_aborts(dut):
    s = await i2c_setup(dut, ack=False)
    await i2c_run(dut, "i2c_wr.asm", [0xA0, 0x3C, 0x55])
    assert s.got == [0xA0]
    assert await drain_rx(dut, 1) == [0x80]
    assert (await rd(dut, A_STATUS)) & 0x02, "TX FIFO should have been flushed"


@cocotb.test()
async def test_i2c_read_with_repeated_start(dut):
    s = await i2c_setup(dut, read_data=[0xDE, 0xAD, 0xBE])
    await i2c_run(dut, "i2c_wr.asm", [0xA0, 0x10])              # write register pointer
    await i2c_run(dut, "i2c_wr.asm", [0xA1])                    # repeated START + read address
    assert s.start == 2 and s.stop == 0
    await i2c_run(dut, "i2c_rd.asm", [0, 0, 0])                 # three tokens -> three bytes
    await i2c_run(dut, "i2c_stop.asm", [])
    assert s.stop == 1
    assert s.master_acks == [True, True, False]
    assert await drain_rx(dut, 6) == [0x00, 0x00, 0x00, 0xDE, 0xAD, 0xBE]


ISA_SELFTEST = """
    SETO 0x81
    JMP  OSR7, t1
    SETI 0xE1
    PUSH
t1:
    SETI 0x11
    PUSH
    JMP  OSR0, t2
    SETI 0xE2
    PUSH
t2:
    SETI 0x22
    PUSH
    SETO 0x00
    JMP  OSR0, e3
    JMP  OSR7, e3
    JMP  ALWAYS, t3
e3:
    SETI 0xE3
    PUSH
t3:
    SETI 0x33
    PUSH
    JMPL 3, e4
    JMPH 3, t4
e4:
    SETI 0xE4
    PUSH
t4:
    SETI 0x44
    PUSH
    SETD 3, 0
    JMPL 3, t5
    SETI 0xE5
    PUSH
t5:
    SETI 0x55
    PUSH
    HALT
"""


@cocotb.test()
async def test_isa_jumps_and_open_drain(dut):
    await reset(dut)
    await wr(dut, A_CLKDIV, 1)
    await load_text(dut, ISA_SELFTEST)
    await wr(dut, A_CTRL, RUN_CLEAR)
    await wait_halt(dut)
    assert await drain_rx(dut, 5) == [0x11, 0x22, 0x33, 0x44, 0x55]
    assert (int(dut.uio_oe.value) >> 3) & 1, "SETD 3,0 must enable the output"
    assert (int(dut.uio_out.value) >> 3) & 1 == 0, "and drive it low"
