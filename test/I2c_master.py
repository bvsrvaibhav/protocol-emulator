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
        ins(LOADO, reverse8(byte)),        
                                             
        ins(BUSOE, imm=0, lvl=1, pin=SCL),  
        ins(BUSOE, imm=0, lvl=1, pin=SDA),   
        ins(WAIT, 2),                        
        ins(BUSOE, imm=1, lvl=1, pin=SDA),   
        ins(WAIT, 2),                        
        ins(BUSOE, imm=1, lvl=1, pin=SCL),
        ins(LOADX, 7),                     
        ins(BUSOE, lvl=0, pin=SDA),         
        ins(WAIT, 2),                        
        ins(BUSOE, imm=0, lvl=1, pin=SCL),  
        ins(WAIT, 2),                       
        ins(BUSOE, imm=1, lvl=1, pin=SCL),  
        ins(DJNZ, 8),                       
        ins(BUSOE, imm=0, lvl=1, pin=SDA),  
        ins(WAIT, 2),
        ins(BUSOE, imm=0, lvl=1, pin=SCL),
        ins(WAIT, 2),                        
        ins(GETBITB, pin=SDA),              
        ins(BUSOE, imm=1, lvl=1, pin=SCL),  
        ins(OUTO),                         
        ins(BUSOE, imm=1, lvl=1, pin=SDA),   
        ins(WAIT, 2),                     
        ins(BUSOE, imm=0, lvl=1, pin=SCL),  
        ins(WAIT, 2),                     
        ins(BUSOE, imm=0, lvl=1, pin=SDA),  
        ins(JMP, 26),                       
    ]


# Demo program: address a device at 0x53, write direction.
I2C_WRITE_ADDR = i2c_write_addr(0x53, rw=0)
