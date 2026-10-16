# SPDX-License-Identifier: Apache-2.0

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from asm import NOP, SET, WAIT, JMP, PUTBIT, LOADX, DJNZ, LOADO
from asm import WAITP, GETBIT, JPIN, SETB, OUTO
from asm import BUSOE, GETBITB, WAITPB
from asm import ins, load_program
from asm import reverse8
from examples.i2c_master import I2C_WRITE_ADDR, SCL, SDA
from examples.i2c_slave import I2C_SLAVE_ALWAYS_ACK

BIT = 6  # cycles per UART bit
IDLE = 0b100  # ui_in[2] (RX line) idle high, LOAD low

# UART 8N1 transmitter: sends 0x55 forever on uo_out[0]
TX_PROG = [
    ins(LOADO, 0x55),
    ins(SET, 0),
    ins(WAIT, 3),
    ins(LOADX, 7),
    ins(PUTBIT, pin=0),
    ins(WAIT, 3),
    ins(DJNZ, 4),
    ins(SET, 1),
    ins(WAIT, 3),
    ins(JMP, 0),
]

# UART 8N1 receiver: bytes on ui_in[2] appear on uo_out
RX_PROG = [
    ins(WAITP, lvl=0, pin=2),  # wait for start bit
    ins(WAIT, 6),              # move to the middle of data bit 0
    ins(LOADX, 7),
    ins(GETBIT, pin=2),        # 3: sample
    ins(WAIT, 3),
    ins(DJNZ, 3),
    ins(OUTO),
    ins(JMP, 0),
]


async def init(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    dut.ena.value = 1
    dut.ui_in.value = IDLE
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def send_byte(dut, byte):
    frame = [0] + [(byte >> i) & 1 for i in range(8)] + [1]
    for b in frame:
        dut.ui_in.value = b << 2
        await ClockCycles(dut.clk, BIT)


@cocotb.test()
async def test_uart_tx_0x55(dut):
    await init(dut)
    await load_program(dut, TX_PROG)

    for _ in range(200):
        await ClockCycles(dut.clk, 1)
        val = dut.uo_out.value
        if val.is_resolvable and int(val) & 1 == 0:
            break
    else:
        assert False, "no start bit seen"

    await ClockCycles(dut.clk, BIT // 2)
    bits = []
    for _ in range(10):  # start + 8 data + stop
        bits.append(int(dut.uo_out.value) & 1)
        await ClockCycles(dut.clk, BIT)

    assert bits[0] == 0, "start bit must be 0"
    byte = sum(b << i for i, b in enumerate(bits[1:9]))
    assert byte == 0x55, f"got 0x{byte:02x}"
    assert bits[9] == 1, "stop bit must be 1"


async def i2c_bus_model(dut, stop, ack_after_bits=9):
    """Drives dut.uio_in as a wired-AND bus: low if the DUT (or our fake slave)
    is pulling its line low via uio_oe, else released (pulled up) high. ACKs
    the address byte by pulling SDA low once it sees `ack_after_bits` SCL
    rising edges after the START condition. `stop` is a single-item list used
    as a mutable flag -- checked every loop, so the caller can end this task
    deterministically instead of relying on Task.kill()/cancel() timing,
    which left this driver fighting over uio_in in later tests even after
    being killed."""
    bits_seen = 0
    prev_scl = 1
    started = False
    while not stop[0]:
        await ClockCycles(dut.clk, 1)
        oe = int(dut.uio_oe.value)
        scl_driven = (oe >> SCL) & 1
        sda_driven = (oe >> SDA) & 1
        scl = 0 if scl_driven else 1
        sda_from_master = 0 if sda_driven else 1

        if not started and scl == 1 and sda_from_master == 0:
            started = True  # START condition: SDA falls while SCL is high
        if started and prev_scl == 0 and scl == 1:
            bits_seen += 1
        prev_scl = scl

        ack_now = started and bits_seen >= ack_after_bits and not sda_driven
        sda = 0 if (sda_driven or ack_now) else 1
        dut.uio_in.value = (scl << SCL) | (sda << SDA)


@cocotb.test()
async def test_i2c_master(dut):
    await init(dut)
    stop = [False]
    cocotb.start_soon(i2c_bus_model(dut, stop))
    await load_program(dut, I2C_WRITE_ADDR)
    await ClockCycles(dut.clk, 250)
    got = int(dut.uo_out.value)
    stop[0] = True            # ends the background driver -- see i2c_bus_model
    await ClockCycles(dut.clk, 2)  # let it actually observe the flag and exit
    assert got & 0x80 == 0, f"expected ACK (bit7=0), got uo_out=0x{got:02x}"


async def i2c_host_byte(dut, byte, settle=3):
    """Drives dut.uio_in as an open-drain host: START, 8 bits MSB-first of
    `byte`, then releases and reads back the slave's ACK. Combines its own
    drive with whatever the DUT is independently pulling low (its ACK),
    exactly like a real wired-AND bus."""

    async def bus(scl_drive, sda_drive):
        # Re-sample uio_oe every cycle, not once per call -- the DUT can start
        # driving (e.g. its ACK) partway through a `settle` window, and a
        # stale one-shot read misses that entirely.
        scl = sda = 1
        for _ in range(settle):
            oe = int(dut.uio_oe.value)
            scl = 0 if (scl_drive or (oe >> SCL) & 1) else 1
            sda = 0 if (sda_drive or (oe >> SDA) & 1) else 1
            dut.uio_in.value = (scl << SCL) | (sda << SDA)
            await ClockCycles(dut.clk, 1)
        return scl, sda

    await bus(0, 0)                      # idle: both released
    await bus(0, 1)                      # START: SDA low while SCL high
    await bus(1, 1)                      # SCL low
    for i in range(7, -1, -1):           # MSB first
        bit = (byte >> i) & 1
        drive_low = 0 if bit else 1
        await bus(1, drive_low)          # set data while SCL low
        await bus(0, drive_low)          # SCL high: sample edge
        await bus(1, drive_low)          # SCL low
    await bus(1, 0)                      # release SDA for the slave's ACK
    _, sda = await bus(0, 0)             # SCL high: read ACK
    await bus(1, 0)                      # SCL low
    return sda == 0                      # True = ACKed


@cocotb.test()
async def test_i2c_slave(dut):
    await init(dut)
    dut.uio_in.value = (1 << SCL) | (1 << SDA)  # idle: both lines released/high --
    # set BEFORE loading, not after: it must hold through the whole load so the
    # 2-cycle input synchronizer is settled well before the core starts executing
    # (right after load, it would otherwise race the synchronizer by exactly the
    # 2 cycles the core takes to reach its first WAITPB check)
    await load_program(dut, I2C_SLAVE_ALWAYS_ACK)
    await ClockCycles(dut.clk, 10)

    sent = 0xA6  # 7-bit addr 0x53 << 1 | write(0)
    acked = await i2c_host_byte(dut, sent)
    assert acked, "slave did not ACK"

    await ClockCycles(dut.clk, 5)
    got = reverse8(int(dut.uo_out.value))
    assert got == sent, f"sent 0x{sent:02x}, slave captured 0x{got:02x}"


@cocotb.test()
async def test_uart_rx(dut):
    await init(dut)
    await load_program(dut, RX_PROG)
    await ClockCycles(dut.clk, 20)

    for byte in (0xA5, 0x3C, 0xFF, 0x00):
        await send_byte(dut, byte)
        await ClockCycles(dut.clk, 10)
        got = int(dut.uo_out.value)
        assert got == byte, f"sent 0x{byte:02x}, got 0x{got:02x}"
