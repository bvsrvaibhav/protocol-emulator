## How it works

A tiny programmable CPU for bit-banging hardware protocols. Instead of a
dedicated UART block, an SPI block, and an I2C block, there is one 16-bit
core with 32 words of instruction memory and a small instruction set built
around reading pins, writing pins, and counting cycles precisely. A program
loaded into memory *becomes* a UART transmitter, an SPI master, or an I2C
master, in the same way the RP2040's PIO state machines or TI's PRU cores
let firmware take over what used to be fixed peripheral logic.

**Instruction set** (16-bit word: opcode, flags, 8-bit operand):

| Op | Mnemonic | Effect |
|----|----------|--------|
| 0  | NOP      | no-op |
| 1  | SET imm  | all `uo_out` pins <= imm |
| 2  | WAIT n   | stall for n+1 cycles |
| 3  | JMP a    | pc <= a |
| 4  | PUTBIT p, m | shift a bit out of the OSR onto pin p. m=0: push-pull on `uo_out`. m=1: open-drain on `uio` (drive low for 0, release/float for 1) |
| 5  | LOADX imm | loop counter x <= imm |
| 6  | DJNZ a   | x--; if x != 0, pc <= a |
| 7  | LOADO imm | load the output shift register (OSR) |
| 8  | WPIN p, lvl | stall until input pin p == lvl |
| 9  | GETBIT p | shift input pin p into the input shift register (ISR) |
| 10 | JPIN a, p, lvl | branch to a if input pin p == lvl |
| 11 | OUTISR   | all `uo_out` pins <= ISR |
| 12 | SETPIN p, lvl | set one `uo_out` pin |
| 13 | DIRPIN p, dir | set a `uio` pin's drive-enable (1=drive, 0=release) |
| 14 | SETUIO p, lvl | set a `uio` pin's output latch |
| 15 | GETUIO p | shift a `uio` pin into the ISR |

Every instruction takes 1 cycle, except WAIT (n+1 cycles) and a stalled WPIN.

**Two pin groups, on purpose.** `uo_out`/`ui_in` are always push-pull, which
is all UART, SPI, and most simple protocols need. `uio` pins add true
tri-state control (DIRPIN/SETUIO/GETUIO, and PUTBIT's open-drain mode),
because I2C's shared SDA line has to be able to float and be pulled high
externally, not just driven high or low. Splitting the two kept the push-pull
path simple while still supporting open-drain where it's actually needed.

**Loading a program.** `uio[0:2]` (SCK/MOSI/CS_N) are a small SPI-style
loader, always available regardless of what the core is currently running.
While CS_N is held low, the core is reset and held idle, and 21-bit words
(5-bit address + 16-bit instruction) are shifted in MSB-first, sampled on
SCK's rising edge. Raising CS_N starts the program running from address 0.
Because the loader only uses `uio[0:2]` while CS_N is low, a running
program is free to use those same three pins (and `uio[3:7]`) as ordinary
I/O once loading is done.

**What's built and verified in simulation:** a UART transmitter, a UART
receiver, generic pin read/write, a full-duplex SPI master transfer (MOSI
out, MISO in, correct byte on both), and an I2C write (start condition,
8 data bits with real open-drain release/drive, ack read, stop condition).
The chip ships with the UART transmitter as its default program at reset,
so it does something visible even before anything is loaded.

An assembler (`test/asm.py`) turns readable mnemonics and labels into the
16-bit words the loader expects, so writing a new protocol program doesn't
mean hand-computing hex.

## How to test

In simulation (`cd test && make`) five cocotb tests exercise: the default
UART transmit, a UART receiver program loaded and fed a real bit stream, a
generic pin-copy program, a full I2C start/byte/ack/stop sequence, and a
full-duplex SPI transfer.

On real hardware: hold `load_cs_n` low and shift in a program via
`load_sck`/`load_mosi` as described above, then release `load_cs_n` to run
it. The board ships with a working UART TX demo (0x55 repeating) at reset,
so `pio_out0` can be checked with a logic analyzer or UART receiver with no
loading step at all, as a sanity check that the chip is alive.

## External hardware

None required to see the chip run its default program. For I2C or SPI use,
an external pull-up resistor is needed on any pin used as an open-drain
I2C line (as with any I2C bus), and a matching SPI slave device.
