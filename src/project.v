/*
 * Copyright (c) 2026 Sriram Vaibhav
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// Tiny programmable pin-toggling core (v0.1).
// Instruction: [15:13] opcode, [7:0] operand.
//   0 NOP
//   1 SET  imm   : output pins <= imm
//   2 WAIT n     : instruction takes n+1 cycles
//   3 JMP  a     : pc <= a
//   4 PUTBIT     : pin0 <= osr[0]; osr <= osr >> 1
//   5 LOADX imm  : x <= imm
//   6 DJNZ a     : if (x != 0) { x <= x-1; pc <= a } else pc <= pc+1
//   7 LOADO imm  : osr <= imm
// Every instruction takes 1 cycle except WAIT.

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

  reg [7:0] pins, osr, x, wcnt;
  reg [4:0] pc;
  reg       waiting;
  reg [15:0] instr;

  always @* begin
    case (pc)
      5'd0:    instr = {3'd7, 5'd0, 8'h55};  // LOADO 0x55
      5'd1:    instr = {3'd1, 5'd0, 8'h00};  // SET 0   (start bit)
      5'd2:    instr = {3'd2, 5'd0, 8'd3};   // WAIT 3
      5'd3:    instr = {3'd5, 5'd0, 8'd7};   // LOADX 7
      5'd4:    instr = {3'd4, 5'd0, 8'd0};   // PUTBIT
      5'd5:    instr = {3'd2, 5'd0, 8'd3};   // WAIT 3
      5'd6:    instr = {3'd6, 5'd0, 8'd4};   // DJNZ 4
      5'd7:    instr = {3'd1, 5'd0, 8'h01};  // SET 1   (stop bit)
      5'd8:    instr = {3'd2, 5'd0, 8'd3};   // WAIT 3
      5'd9:    instr = {3'd3, 5'd0, 8'd0};   // JMP 0
      default: instr = 16'h0000;             // NOP
    endcase
  end

  wire [2:0] op  = instr[15:13];
  wire [7:0] imm = instr[7:0];

  always @(posedge clk) begin
    if (!rst_n) begin
      pc <= 0; pins <= 8'h01; osr <= 0; x <= 0; wcnt <= 0; waiting <= 0;
    end else if (waiting) begin
      if (wcnt == 0) begin waiting <= 0; pc <= pc + 1; end
      else wcnt <= wcnt - 1;
    end else begin
      pc <= pc + 1;
      case (op)
        3'd1: pins <= imm;
        3'd2: if (imm != 0) begin waiting <= 1; wcnt <= imm - 1; pc <= pc; end
        3'd3: pc <= imm[4:0];
        3'd4: begin pins[0] <= osr[0]; osr <= {1'b0, osr[7:1]}; end
        3'd5: x <= imm;
        3'd6: if (x != 0) begin x <= x - 1; pc <= imm[4:0]; end
        3'd7: osr <= imm;
        default: ;
      endcase
    end
  end

  assign uo_out  = pins;
  assign uio_out = 0;
  assign uio_oe  = 0;

  wire _unused = &{ena, ui_in, uio_in, 1'b0};

endmodule
