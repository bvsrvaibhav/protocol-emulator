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

    await pins(0, 0, 0)  # cs_n low
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
