# SPDX-License-Identifier: Apache-2.0

import cocotb
from asm import assemble
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

BIT = 6  


async def reset(dut):
    dut.ena.value = 1
    dut.ui_in.value = 1          
    dut.uio_in.value = 0b100    
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1


async def load_program(dut, words):
    """Write words[0..] to memory addresses 0.. through the loader pins."""
    async def pins(sck, mosi, cs_n):
        dut.uio_in.value = (cs_n << 2) | (mosi << 1) | sck
        await ClockCycles(dut.clk, 4)

    await pins(0, 0, 0)  
    for addr, w in enumerate(words):
        full = (addr << 16) | w
        for b in range(20, -1, -1):
            bit = (full >> b) & 1
            await pins(0, bit, 0)
            await pins(1, bit, 0)
    await pins(0, 0, 0)
    await pins(0, 0, 1) 


@cocotb.test()
async def test_demo_uart_tx(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    for _ in range(200):
        await ClockCycles(dut.clk, 1)
        if int(dut.uo_out.value) & 1 == 0:
            break
    else:
        assert False, "no start bit seen"

    await ClockCycles(dut.clk, BIT // 2)
    bits = []
    for _ in range(10):
        bits.append(int(dut.uo_out.value) & 1)
        await ClockCycles(dut.clk, BIT)

    assert bits[0] == 0
    assert sum(b << i for i, b in enumerate(bits[1:9])) == 0x55
    assert bits[9] == 1


@cocotb.test()
async def test_loaded_uart_rx(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    prog = assemble("""
    start:
        WPIN 0, 0       ; wait for start bit on input pin 0
        WAIT 6          ; skip to the middle of bit 0
        LOADX 7
    loop:
        GETBIT 0        ; sample input pin 0
        WAIT 3
        DJNZ loop       ; 8 samples
        OUTISR          ; received byte on the output pins
        JMP start
    """)
    await load_program(dut, prog)

    byte = 0xA7
    frame = [0] + [(byte >> i) & 1 for i in range(8)] + [1]
    await ClockCycles(dut.clk, 20)
    for b in frame:
        dut.ui_in.value = b
        await ClockCycles(dut.clk, BIT)
    dut.ui_in.value = 1
    await ClockCycles(dut.clk, 3 * BIT)

    got = int(dut.uo_out.value)
    assert got == byte, f"received 0x{got:02x}, expected 0x{byte:02x}"


@cocotb.test()
async def test_loaded_pin_copy(dut):
    """Copy input pin 1 to output pin 2 using JPIN and SETPIN."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    prog = assemble("""
    loop:
        JPIN hi, 1, 1   ; input pin 1 high?
        SETPIN 2, 0
        JMP loop
    hi:
        SETPIN 2, 1
        JMP loop
    """)
    await load_program(dut, prog)

    for level in (1, 0, 1, 0):
        dut.ui_in.value = 0b01 | (level << 1)
        await ClockCycles(dut.clk, 20)
        got = (int(dut.uo_out.value) >> 2) & 1
        assert got == level, f"pin copy failed for level {level}"


def i2c_write_byte_asm(byte, sda=3, scl=4):
    """Bit-bang an I2C-style start + byte (MSB first, open-drain) + ack + stop.
    PUTBIT's open-drain mode drives the OSR bit onto an SDA pin natively
    (drive-low for 0, release-and-float for 1), so the 8 data bits run as
    a real loop instead of being unrolled -- this is the point of having
    open-drain support built into the core rather than bit-banged in software.
    PUTBIT always shifts the LSB out first (osr[0], right shift). I2C is
    MSB-first, so the byte is bit-reversed here, at assemble time, before
    it's loaded into OSR -- the same fix SPI needed."""
    rev = int(f"{byte:08b}"[::-1], 2)
    return f"""
    DIRPIN {sda}, 1
    DIRPIN {scl}, 1
    SETUIO {sda}, 1
    SETUIO {scl}, 1
    WAIT 2
    SETUIO {sda}, 0
    WAIT 2
    SETUIO {scl}, 0
    LOADO {rev}
    LOADX 7
    bitloop:
        PUTBIT {sda}, 1
        WAIT 1
        SETUIO {scl}, 1
        WAIT 2
        SETUIO {scl}, 0
        DJNZ bitloop
    DIRPIN {sda}, 0
    WAIT 1
    SETUIO {scl}, 1
    GETUIO {sda}
    WAIT 1
    SETUIO {scl}, 0
    WAIT 1
    DIRPIN {sda}, 1
    SETUIO {sda}, 0
    WAIT 1
    SETUIO {scl}, 1
    WAIT 1
    DIRPIN {sda}, 0
    stophold: JMP stophold
    """

@cocotb.test()
async def test_loaded_i2c_write(dut):
    """Bit-bang an I2C start + byte + stop on open-drain uio[3]=SDA, uio[4]=SCL,
    with no external pull-up model: uio_in reads as released (1) unless the
    chip itself is driving, i.e. what an idle bus with a pull-up looks like."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    byte = 0xB3
    prog = assemble(i2c_write_byte_asm(byte))
    await load_program(dut, prog)

    sda_hist, scl_hist = [], []

    def line(driven, out):
        return int(out) if driven else 1  

    for _ in range(400):
        await ClockCycles(dut.clk, 1)
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        sda_hist.append(line(oe & (1 << 3), (out >> 3) & 1))
        scl_hist.append(line(oe & (1 << 4), (out >> 4) & 1))
        dut.uio_in.value = (int(dut.uio_in.value) & ~(1 << 3)) | (sda_hist[-1] << 3)

    def edges(sig):
        return [i for i in range(1, len(sig)) if sig[i] != sig[i - 1]]

    start_idx = next(i for i in edges(sda_hist) if sda_hist[i] == 0 and scl_hist[i] == 1)
    assert start_idx > 0

    scl_rises = [i for i in edges(scl_hist) if scl_hist[i] == 1 and i > start_idx]
    assert len(scl_rises) >= 9, f"expected 9 SCL pulses (8 data + ack), got {len(scl_rises)}"
    got = 0
    for k in range(8):
        got = (got << 1) | sda_hist[scl_rises[k]]
    assert got == byte, f"I2C captured 0x{got:02x}, expected 0x{byte:02x}"

    stop_idx = next(i for i in edges(sda_hist) if i > scl_rises[8] and
                     sda_hist[i] == 1 and scl_hist[i] == 1)
    assert stop_idx > scl_rises[8]


def spi_xfer_asm(byte, mosi=1, sck=2, cs=3, miso=0):
    """SPI mode 0 (CPOL=0, CPHA=0) master transfer of one byte, full duplex:
    MOSI set up before SCK rises, MISO sampled on the rising edge, SCK falls
    to prepare the next bit. No open-drain needed -- SPI is push-pull.
    PUTBIT always shifts the LSB out first (osr[0], right shift), which is
    what UART wants. SPI is conventionally MSB-first, so the byte is
    bit-reversed here, at assemble time, before it's loaded into OSR."""
    rev = int(f"{byte:08b}"[::-1], 2)
    return f"""
    SETPIN {cs}, 0
    LOADO {rev}
    LOADX 7
    loop:
        PUTBIT {mosi}, 0
        WAIT 1
        SETPIN {sck}, 1
        GETBIT {miso}
        WAIT 1
        SETPIN {sck}, 0
        WAIT 1
        DJNZ loop
    SETPIN {cs}, 1
    OUTISR
    done: JMP done
    """


@cocotb.test()
async def test_loaded_spi_xfer(dut):
    """Drive an SPI master transfer and check both directions: the MOSI/SCK/CS
    waveform sends the right byte, and a byte driven on the MISO input pin
    (as if from a slave) is correctly captured into the output pins."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    tx_byte = 0x6C
    rx_byte = 0x93  
    prog = assemble(spi_xfer_asm(tx_byte))
    await load_program(dut, prog)

    mosi_bits, cs_hist, sck_hist = [], [], []
    rx_bits = [(rx_byte >> i) & 1 for i in range(7, -1, -1)]
    bit_i = [0]
    prev_sck = [0]

    for _ in range(300):
        await ClockCycles(dut.clk, 1)
        out = int(dut.uo_out.value)
        sck = (out >> 2) & 1
        cs_hist.append((out >> 3) & 1)
        sck_hist.append(sck)
        mosi_bits.append((out >> 1) & 1)
        if prev_sck[0] == 1 and sck == 0 and bit_i[0] < 8:
            dut.ui_in.value = rx_bits[bit_i[0]]
            bit_i[0] += 1
        prev_sck[0] = sck

    def edges(sig):
        return [i for i in range(1, len(sig)) if sig[i] != sig[i - 1]]

    cs_lo = next(i for i in range(len(cs_hist)) if cs_hist[i] == 0)
    cs_hi = next(i for i in edges(cs_hist) if cs_hist[i] == 1 and i > cs_lo)
    sck_rises = [i for i in edges(sck_hist) if sck_hist[i] == 1 and cs_lo <= i < cs_hi]
    assert len(sck_rises) == 8, f"expected 8 SCK pulses, got {len(sck_rises)}"

    got_tx = 0
    for k in range(8):
        got_tx = (got_tx << 1) | mosi_bits[sck_rises[k]]
    assert got_tx == tx_byte, f"MOSI captured 0x{got_tx:02x}, expected 0x{tx_byte:02x}"

    await ClockCycles(dut.clk, 5)
    got_rx = int(dut.uo_out.value)
    assert got_rx == rx_byte, f"MISO captured 0x{got_rx:02x}, expected 0x{rx_byte:02x}"
