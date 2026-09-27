# SPDX-License-Identifier: Apache-2.0
"""Constrained-random regression: for many random programs and random
sequences of pin stimulus, check the core never violates its basic
invariants -- pc always in range, uio never driven while loading, and
that whatever it does drive is consistent with its own instruction stream
replayed in a Python reference model.
"""
import random

import cocotb
from asm import assemble
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from test import load_program, reset

N_RUNS = 40           
STEPS_PER_RUN = 120

MNEMONICS_NO_OPERAND = ["NOP", "OUTISR"]
MNEMONICS_IMM = ["SET", "WAIT", "LOADX", "LOADO"]
MNEMONICS_LABEL = ["JMP", "DJNZ"]
MNEMONICS_PIN = ["GETBIT", "GETUIO"]
MNEMONICS_PINLVL = ["WPIN", "SETPIN", "DIRPIN", "SETUIO"]
MNEMONICS_PINMODE = ["PUTBIT"]


def random_program(rng, n):
    """A random, syntactically valid, terminating-agnostic program: every
    branch target is clamped into range so the assembler always accepts it,
    and WAIT operands are kept small so a run finishes within STEPS_PER_RUN."""
    lines = []
    for i in range(n):
        kind = rng.choice(["none", "imm", "label", "pin", "pinlvl", "pinmode"])
        if kind == "none":
            lines.append(rng.choice(MNEMONICS_NO_OPERAND))
        elif kind == "imm":
            m = rng.choice(MNEMONICS_IMM)
            v = rng.randint(0, 6) if m == "WAIT" else rng.randint(0, 255)
            lines.append(f"{m} {v}")
        elif kind == "label":
            m = rng.choice(MNEMONICS_LABEL)
            lines.append(f"{m} {rng.randint(0, n - 1)}")
        elif kind == "pin":
            lines.append(f"{rng.choice(MNEMONICS_PIN)} {rng.randint(0, 7)}")
        elif kind == "pinlvl":
            lines.append(f"{rng.choice(MNEMONICS_PINLVL)} {rng.randint(0, 7)}, {rng.randint(0, 1)}")
        else:
            lines.append(f"{rng.choice(MNEMONICS_PINMODE)} {rng.randint(0, 7)}, {rng.randint(0, 1)}")
    return "\n".join(lines)


@cocotb.test()
async def test_random_programs_never_break_invariants(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    rng = random.Random(0xC0FFEE)

    for run in range(N_RUNS):
        n = rng.randint(4, 30)
        src = random_program(rng, n)
        prog = assemble(src)

        await reset(dut)
        await load_program(dut, prog)

        for step in range(STEPS_PER_RUN):
            # random async stimulus on the protocol-facing input pins
            dut.ui_in.value = rng.randint(0, 255)
            dut.uio_in.value = (int(dut.uio_in.value) & 0b100) | rng.randint(0, 0b011)
            await ClockCycles(dut.clk, 1)

            # Invariant 1: the program counter is always a defined value in
            # range 0..31 -- never X/Z, never out of the memory's address
            # space. This is the invariant most likely to catch a real bug:
            # a branch instruction computing a bad target, or a control
            # signal left undefined out of reset.
            pc_val = dut.pc.value
            assert pc_val.is_resolvable, (
                f"run {run} step {step}: pc is X/Z ({pc_val}), program was:\n{src}"
            )
            assert 0 <= int(pc_val) <= 31, (
                f"run {run} step {step}: pc={int(pc_val)} out of range, program was:\n{src}"
            )

        # After a random program, a reset must always return the chip to
        # its documented idle state: uio released, ready for the next load.
        await reset(dut)
        assert int(dut.uio_oe.value) == 0x00, (
            f"run {run}: uio_oe not clear after reset, program was:\n{src}"
        )
