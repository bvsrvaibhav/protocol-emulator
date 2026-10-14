# SPDX-License-Identifier: Apache-2.0
"""Assembler for the tt_um_example pin core. ins(op, imm, lvl, pin) -> 16-bit word."""

NOP, SET, WAIT, JMP, PUTBIT, LOADX, DJNZ, LOADO = 0, 1, 2, 3, 4, 5, 6, 7
WAITP, GETBIT, JPIN, SETB, OUTO = 8, 9, 10, 11, 12
BUSOE, GETBITB, WAITPB = 13, 14, 15


def ins(op, imm=0, lvl=0, pin=0):
    return (op << 12) | (lvl << 11) | (pin << 8) | imm


def reverse8(b):
    """Bit-reverse a byte. The core always shifts LSB-first (PUTBIT/BUSOE),
    but I2C is MSB-first on the wire -- pre-reverse a byte before loading it
    to send, and reverse a byte received via GETBITB to get its natural value."""
    r = 0
    for i in range(8):
        r |= ((b >> i) & 1) << (7 - i)
    return r


def assemble(prog, mem_words=32):
    """Pad a list of ins(...) words to mem_words with NOPs."""
    assert len(prog) <= mem_words, f"program has {len(prog)} words, core holds {mem_words}"
    return prog + [0] * (mem_words - len(prog))


async def load_program(dut, prog):
    """Serial-load an assembled program into the core via ui_in[0]=LOAD, ui_in[1]=DATA."""
    from cocotb.triggers import ClockCycles

    idle = int(dut.ui_in.value) & ~0b11  # keep other input bits (e.g. RX line) as they are
    for w in assemble(prog):
        for i in range(15, -1, -1):
            dut.ui_in.value = idle | 1 | (((w >> i) & 1) << 1)
            await ClockCycles(dut.clk, 1)
    dut.ui_in.value = idle
