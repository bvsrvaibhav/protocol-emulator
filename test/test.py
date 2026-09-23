# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

BIT=6
@cocotb.test()
async def test_uart_0x55(dut):
    clock=Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value=1
    dut.ui_in.value=0
    dut.uio_in.value=0
    dut.rst_n.value=0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value=1

for _ in range(200):
    await ClockCycles(dut.clk, 1)
    if int(dut.uo_out.value) & 1 == 0:
        break
else:
    assert False, "no start bit seen"

await ClockCycles(dut.clk, BIT // 2)
bits=[]
for _ in range(10):
    bits.append(int(dut.uo_out.value)&1)
    await ClockCycles(dut.clk, BIT)

assert bits[0]==0 "start bit must be 0"
byte=sum(b<<i for i, b in enumerate(bits[1:9]))
assert byte == 0x55, f"got 0x{byte:02x}"
assert bits[9]==1, "stop bit must be 1"
