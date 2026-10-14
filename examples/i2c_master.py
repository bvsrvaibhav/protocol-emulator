# SPDX-License-Identifier: Apache-2.0
"""I2C master: loads a 7-bit address + write byte, sends START, the address
byte MSB-first, reads the ACK, then STOP. Pins on the open-drain bidirectional
bus: 0=SCL 1=SDA."""

from asm import LOADO, BUSOE, WAIT, LOADX, DJNZ, GETBITB, OUTO, JMP, ins

SCL, SDA = 0, 1


def reverse8(b):
    r = 0
    for i in range(8):
        r |= ((b >> i) & 1) << (7 - i)
    return r


def i2c_write_addr(addr7, rw=0):
    """Build a program that addresses a 7-bit I2C device (rw=0 write, 1 read)."""
    byte = (addr7 << 1) | rw
    return [
        ins(LOADO, reverse8(byte)),          # 0  core shifts LSB-first, so
                                              #    the byte is pre-reversed to
                                              #    come out MSB-first on the wire
        ins(BUSOE, imm=0, lvl=1, pin=SCL),   # 1  release SCL (idle high)
        ins(BUSOE, imm=0, lvl=1, pin=SDA),   # 2  release SDA (idle high)
        ins(WAIT, 2),                        # 3
        ins(BUSOE, imm=1, lvl=1, pin=SDA),   # 4  drive SDA low -> START
        ins(WAIT, 2),                        # 5
        ins(BUSOE, imm=1, lvl=1, pin=SCL),   # 6  drive SCL low
        ins(LOADX, 7),                       # 7
        ins(BUSOE, lvl=0, pin=SDA),          # 8  shift a bit out (loop target)
        ins(WAIT, 2),                        # 9  data settle
        ins(BUSOE, imm=0, lvl=1, pin=SCL),   # 10 release SCL high (sample edge)
        ins(WAIT, 2),                        # 11
        ins(BUSOE, imm=1, lvl=1, pin=SCL),   # 12 drive SCL low
        ins(DJNZ, 8),                        # 13 loop for all 8 bits
        ins(BUSOE, imm=0, lvl=1, pin=SDA),   # 14 release SDA for the slave's ACK
        ins(WAIT, 2),                        # 15
        ins(BUSOE, imm=0, lvl=1, pin=SCL),   # 16 release SCL (sample ACK)
        ins(WAIT, 2),                        # 17
        ins(GETBITB, pin=SDA),               # 18 read ACK bit (0 = ACK, 1 = NACK)
        ins(BUSOE, imm=1, lvl=1, pin=SCL),   # 19 drive SCL low
        ins(OUTO),                           # 20 uo_out <= osr (ACK ends up in bit 7)
        ins(BUSOE, imm=1, lvl=1, pin=SDA),   # 21 drive SDA low, ready for STOP
        ins(WAIT, 2),                        # 22
        ins(BUSOE, imm=0, lvl=1, pin=SCL),   # 23 release SCL high
        ins(WAIT, 2),                        # 24
        ins(BUSOE, imm=0, lvl=1, pin=SDA),   # 25 release SDA high while SCL high -> STOP
        ins(JMP, 26),                        # 26 idle
    ]


# Demo program: address a device at 0x53, write direction.
I2C_WRITE_ADDR = i2c_write_addr(0x53, rw=0)
