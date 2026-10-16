## How it works

A tiny 16-bit-instruction core with no fixed program: it reprograms itself over
`ui_in` instead of hard-wiring a single protocol into the gates. Software
(`asm.py`) assembles instruction words; the chip just executes them.

Registers: 5-bit `pc`, 8-bit `osr` (shift register), 8-bit `x` (loop counter),
32 x 16-bit program memory, 8-bit `pins` (drives `uo_out`, push-pull), 8-bit
`bdir` (drives `uio_oe`, open-drain on `uio`).

Instruction format: `[15:12] op, [11] lvl, [10:8] pin, [7:0] imm` (jump
addresses use `imm[4:0]`). 16 opcodes, all used:

| op | mnemonic | effect |
|----|----------|--------|
| 0  | NOP      | — |
| 1  | SET imm      | `uo_out <= imm` |
| 2  | WAIT n       | stall n+1 cycles |
| 3  | JMP a        | `pc <= a` |
| 4  | PUTBIT pin   | `uo_out[pin] <= osr[0]`; `osr >>= 1` |
| 5  | LOADX imm    | `x <= imm` |
| 6  | DJNZ a       | `x--; pc <= a` if x != 0 |
| 7  | LOADO imm    | `osr <= imm` |
| 8  | WAITP lvl,pin| stall until `ui_in[pin] == lvl` |
| 9  | GETBIT pin   | `osr <= {ui_in[pin], osr[7:1]}` |
| 10 | JPIN lvl,pin,a | `pc <= a` if `ui_in[pin] == lvl` |
| 11 | SETB lvl,pin | `uo_out[pin] <= lvl` |
| 12 | OUTO         | `uo_out <= osr` |
| 13 | BUSOE pin,lvl| open-drain drive/shift on `uio[pin]` (see below) |
| 14 | GETBITB pin  | `osr <= {uio[pin], osr[7:1]}` |
| 15 | WAITPB lvl,pin | stall until `uio[pin] == lvl` |

`BUSOE` (op 13) is the one instruction that does two different things
depending on `lvl`, because I2C needs both a static drive/release (for
START/STOP and clocking SCL) and a data-dependent shift (for sending a byte)
on the same open-drain pin, and there were no spare opcodes left to split
them: `lvl=1` drives `uio_oe[pin] <= imm[0]` (1 = pull the bus low, 0 =
release it); `lvl=0` shifts a bit out of `osr` instead (`osr[0]=1` releases,
`osr[0]=0` drives low), consuming `osr` the same way `PUTBIT` does.

`ui_in` and `uio_in` are each read through a 2-flop synchronizer before any
instruction sees them.

### Loading a program

Hold `ui_in[0]` (LOAD) high and clock 16-bit words in MSB-first on `ui_in[1]`
(DATA), one bit per clock, 32 words total. The core is paused (held at
`pc=0`) the whole time LOAD is high, so it always starts clean at `pc=0`
once LOAD goes low, regardless of what it was doing before loading started.

### Pin map used by the example programs

- `uo_out[0]`: UART TX
- `ui_in[2]`: UART RX
- `uio[0]`: I2C/SPI SCL / SCLK
- `uio[1]`: I2C SDA / SPI MOSI
- `uio[3]`: SPI MISO
- `uio[4]`: SPI CS

### Example programs (`examples/`, assembled with `asm.py`)

- UART 8N1 transmitter and receiver (`test/test.py`: `TX_PROG`, `RX_PROG`)
- SPI mode-0 master, full-duplex (`examples/spi_master.py`)
- I2C master: START, 7-bit address + R/W, ACK, STOP (`examples/i2c_master.py`)
- I2C slave/target: detects START, clocks in 8 bits, ACKs, exposes the byte
  on `uo_out` (`examples/i2c_slave.py`). **Known limitation:** the ISA has no
  compare/branch-on-equal instruction (all 16 opcodes are in use), so this
  slave can't match its own address -- it ACKs every address. A real
  multi-device bus needs that; a single-slave demo doesn't. Demonstrates the
  controller role and the target role running against each other, which the
  competition FAQ calls out as a plus.

Byte order on I2C: the core always shifts LSB-first (`PUTBIT`/`BUSOE`), but
I2C transmits MSB-first on the wire. `asm.reverse8()` is applied before
loading a byte to send, and applied again to a byte received via `GETBITB`
to get its natural value back -- same convention, both directions.

## How to test

`cd test && make` runs the cocotb testbench (`test/test.py`) under Icarus
Verilog: loads each example program over the LOAD/DATA pins exactly as real
hardware would, then checks the pin-level protocol output.

- `test_uart_tx_0x55`: loads `TX_PROG`, waits for the UART start bit, samples
  mid-bit, checks the frame decodes to `0x55` with correct start/stop bits.
- `test_i2c_master`: loads the I2C program, runs a Python coroutine
  (`i2c_bus_model`) that emulates a wired-AND bus and ACKs the address byte
  after the 9th SCL rising edge, checks the master reads ACK back correctly.
- `test_i2c_slave`: loads the I2C slave program, runs a scripted Python host
  (`i2c_host_byte`) that drives a real START/address/ACK sequence against it,
  checks the slave ACKs and reports the correct byte back.
- `test_uart_rx`: loads `RX_PROG`, drives 4 bytes in on the RX pin, checks
  each one appears correctly on `uo_out`.

`GATES=yes make` runs the same tests against the post-synthesis gate-level
netlist.

### Verification notes

Caught and fixed via simulation during development, in case it's useful
context for review:

- The core originally resumed at whatever `pc` it had drifted to before
  loading started, instead of `pc=0` — fixed by forcing `pc<=0` for the
  whole duration LOAD is asserted, not just freezing it.
- Gate-level simulation starts every flip-flop at `X`, unlike the RTL-only
  sim (Icarus defaults `reg`s to 0); a transient `X` right after the program
  load settles could crash a test that blindly `int()`s a signal — fixed by
  checking `.is_resolvable` first.
- The I2C testbench's own ACK-timing logic had an off-by-one (the 8th data
  bit's SCL edge and the dedicated ACK-sampling edge aren't the same edge).
- The I2C slave was verified first with a from-scratch two-core loopback
  (the master and slave programs run against each other on a shared
  simulated wire, no scripted stand-in) before any cocotb test was written,
  which caught a real RTL-adjacent bug: `WAITPB` for SCL-high succeeded
  immediately on a stale pre-START level instead of waiting for a genuine
  clock edge, fixed by syncing to SCL-low first.
- The cocotb-side scripted host driving the slave sampled the DUT's
  `uio_oe` once per multi-cycle "settle" window instead of every cycle, so
  it missed the slave's ACK when it started mid-window. Diagnosed by
  instrumenting internal signals (`dut.user_project.pc` etc. -- the DUT's
  top-level cocotb handle is the `tb` wrapper, so the actual core is nested
  one level in) directly in the test log rather than guessing further.

## External hardware

None required. Standard I2C/SPI pull-ups are assumed external if testing on
real silicon; the core drives `uio` open-drain for I2C and expects the host
board to supply pull-ups (or a push-pull level shifter) same as any other
I2C bus.
