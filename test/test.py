# SPDX-License-Identifier: Apache-2.0
"""I2C slave (target role): detects START, clocks in 8 bits (address+R/W),
ACKs unconditionally, exposes the received byte on uo_out.

Known limitation: the ISA has no compare/branch-on-equal instruction (all 16
opcodes are in use), so this slave can't match its own address -- it ACKs
every address. A real multi-device bus needs that; a single-slave demo
doesn't.

Byte order: uo_out holds the received byte bit-reversed (GETBITB
reconstructs LSB-first, matching UART RX's convention, but I2C transmits
MSB-first) -- apply reverse8() in software to read the natural value, the
same way the master applies it before loading a byte to send."""

from asm import BUSOE, WAITPB, LOADX, GETBITB, DJNZ, OUTO, JMP, ins

SCL, SDA = 0, 1

I2C_SLAVE_ALWAYS_ACK = [
    ins(BUSOE, imm=0, lvl=1, pin=SCL),   # 0  release SCL (slave never drives it)
    ins(BUSOE, imm=0, lvl=1, pin=SDA),   # 1  release SDA
    ins(WAITPB, lvl=0, pin=SDA),         # 2  wait for START (SDA falls while idle-high)
    ins(WAITPB, lvl=0, pin=SCL),         # 3  sync to a real clock low before sampling
                                          #    (SCL may still read high from before START)
    ins(LOADX, 7),                       # 4
    ins(WAITPB, lvl=1, pin=SCL),         # 5  loop target: wait for a real SCL rising edge
    ins(GETBITB, pin=SDA),               # 6  sample
    ins(WAITPB, lvl=0, pin=SCL),         # 7  wait SCL low again
    ins(DJNZ, 5),                        # 8  loop for all 8 bits
    ins(OUTO),                           # 9  uo_out <= received byte (bit-reversed, see above)
    ins(BUSOE, imm=1, lvl=1, pin=SDA),   # 10 ACK: drive SDA low
    ins(WAITPB, lvl=1, pin=SCL),         # 11 wait for the ACK clock pulse
    ins(WAITPB, lvl=0, pin=SCL),         # 12
    ins(BUSOE, imm=0, lvl=1, pin=SDA),   # 13 release SDA
    ins(JMP, 13),                        # 14 idle
]
