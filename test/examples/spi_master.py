# SPDX-License-Identifier: Apache-2.0
"""SPI master, mode 0 (CPOL=0, CPHA=0). Pins: 0=SCLK 1=MOSI 3=MISO 4=CS.
Shifts 0xA5 out on MOSI, shifts MISO in, result left in OUTO -> uo_out."""

from asm import SET, WAIT, JMP, PUTBIT, LOADX, DJNZ, LOADO, GETBIT, SETB, OUTO, ins

SPI_MASTER = [
    ins(SETB, lvl=1, pin=4),   
    ins(SETB, lvl=0, pin=0),   
    ins(LOADO, 0xA5),          
    ins(SETB, lvl=0, pin=4),   
    ins(LOADX, 7),
    ins(PUTBIT, pin=1),        
    ins(SETB, lvl=1, pin=0),   
    ins(GETBIT, pin=3),        
    ins(SETB, lvl=0, pin=0),   
    ins(DJNZ, 4),
    ins(SETB, lvl=1, pin=4),   
    ins(OUTO),                 
    ins(JMP, 11),              
]
