# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from asm import NOP, SET, WAIT, JMP, PUTBIT, LOADX, DJNZ, LOADO
from asm import WAITP, GETBIT, JPIN, SETB, OUTO
from asm import ins, load_program

BIT = 6 
IDLE = 0b100  

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


RX_PROG = [
    ins(WAITP, lvl=0, pin=2),  
    ins(WAIT, 6),              
    ins(LOADX, 7),
    ins(GETBIT, pin=2),       
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
        if int(dut.uo_out.value) & 1 == 0:
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
