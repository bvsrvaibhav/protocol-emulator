/*
 * Copyright (c) 2026 Sriram Vaibhav
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// Tiny programmable pin core (v0.2).
//
// Loading a program: hold ui_in[0] (LOAD) high and clock 16-bit words in
// MSB first on ui_in[1] (DATA), one bit per clk. Words go to addresses 0, 1, 2...
// (address counter is cleared by reset). Load all 32 words. The core is paused
// while LOAD is high and runs from pc=0 when LOAD goes low.
//
// Instruction: [15:12] op, [11] lvl, [10:8] pin, [7:0] imm (addr = imm[4:0])
//    0 NOP
//    1 SET   imm     : uo_out <= imm
//    2 WAIT  n       : takes n+1 cycles
//    3 JMP   a       : pc <= a
//    4 PUTBIT pin    : uo_out[pin] <= osr[0]; osr <= osr >> 1
//    5 LOADX imm     : x <= imm
//    6 DJNZ  a       : if (x != 0) { x <= x-1; pc <= a }
//    7 LOADO imm     : osr <= imm
//    8 WAITP lvl,pin : stall until input pin == lvl
//    9 GETBIT pin    : osr <= {input pin, osr[7:1]}
//   10 JPIN  lvl,pin,a : if (input pin == lvl) pc <= a
//   11 SETB  lvl,pin : uo_out[pin] <= lvl
//   12 OUTO          : uo_out <= osr
//   13 BUSOE pin,lvl : open-drain drive on uio[pin] (uio_oe[pin], uio_out[pin]=0)
//                      lvl=0: bdir[pin] <= ~osr[0]; osr <= osr >> 1   (shift out a bit:
//                             1 releases the bus, 0 pulls it low -- I2C data/ACK bit)
//                      lvl=1: bdir[pin] <= imm[0]                    (static drive(1)/release(0),
//                             for START/STOP conditions and clocking SCL)
//   14 GETBITB pin   : osr <= {uio[pin], osr[7:1]}  (sample the open-drain bus, e.g. an ACK)
//   15 WAITPB lvl,pin: stall until uio[pin] == lvl  (clock stretching, or wait for a released bus)
// Inputs are read through a 2-flop synchronizer. All instructions take 1 cycle
// except WAIT (n+1) and a stalled WAITP/WAITPB.

module tt_um_example (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  reg [15:0] mem [0:31];
  reg [15:0] sh;
  reg [3:0]  cnt;
  reg [4:0]  waddr;

  reg [7:0] pins, osr, x, wcnt;
  reg [4:0] pc;
  reg       waiting;
  reg [7:0] in_q, in_s;
  reg [7:0] bdir;           
  reg [7:0] uio_q, uio_s;

  wire load  = ui_in[0];
  wire ldata = ui_in[1];

  wire [15:0] sh_next = {sh[14:0], ldata};

  always @(posedge clk) begin
    if (!rst_n) begin
      cnt   <= 0;
      waddr <= 0;
    end else if (load) begin
      sh <= sh_next;
      if (cnt == 4'd15) begin
        mem[waddr] <= sh_next;
        waddr      <= waddr + 5'd1;
        cnt        <= 0;
      end else begin
        cnt <= cnt + 4'd1;
      end
    end else begin
      cnt <= 0;
    end
  end

  always @(posedge clk) begin
    in_q  <= ui_in;
    in_s  <= in_q;
    uio_q <= uio_in;
    uio_s <= uio_q;
  end
  wire [15:0] instr = mem[pc];
  wire [3:0]  op    = instr[15:12];
  wire        lvl   = instr[11];
  wire [2:0]  pidx  = instr[10:8];
  wire [7:0]  imm   = instr[7:0];
  wire [4:0]  addr  = instr[4:0];

  always @(posedge clk) begin
    if (!rst_n) begin
      pc <= 0; pins <= 8'h01; osr <= 0; x <= 0; wcnt <= 0; waiting <= 0; bdir <= 0;
    end else if (load) begin
      pc      <= 0;   
      waiting <= 0;
    end else if (waiting) begin
      if (wcnt == 0) begin waiting <= 0; pc <= pc + 5'd1; end
      else wcnt <= wcnt - 8'd1;
    end else begin
      pc <= pc + 5'd1;
      case (op)
        4'd1:  pins <= imm;
        4'd2:  if (imm != 0) begin waiting <= 1; wcnt <= imm - 8'd1; pc <= pc; end
        4'd3:  pc <= addr;
        4'd4:  begin pins[pidx] <= osr[0]; osr <= {1'b0, osr[7:1]}; end
        4'd5:  x <= imm;
        4'd6:  if (x != 0) begin x <= x - 8'd1; pc <= addr; end
        4'd7:  osr <= imm;
        4'd8:  if (in_s[pidx] != lvl) pc <= pc;
        4'd9:  osr <= {in_s[pidx], osr[7:1]};
        4'd10: if (in_s[pidx] == lvl) pc <= addr;
        4'd11: pins[pidx] <= lvl;
        4'd12: pins <= osr;
        4'd13: if (lvl) bdir[pidx] <= imm[0];
               else begin bdir[pidx] <= ~osr[0]; osr <= {1'b0, osr[7:1]}; end
        4'd14: osr <= {uio_s[pidx], osr[7:1]};
        4'd15: if (uio_s[pidx] != lvl) pc <= pc;
        default: ;
      endcase
    end
  end

  assign uo_out  = pins;
  assign uio_out = 8'h00;  
  assign uio_oe  = bdir;

  wire _unused = &{ena, 1'b0};

endmodule
