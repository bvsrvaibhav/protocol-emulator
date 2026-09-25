/*
 * Copyright (c) 2026 Sriram Vaibhav
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

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

  function [15:0] prog(input [4:0] a);
    case (a)
      5'd0:    prog = {4'd7, 4'd0, 8'h55};  
      5'd1:    prog = {4'd1, 4'd0, 8'h00};  
      5'd2:    prog = {4'd2, 4'd0, 8'd3};   
      5'd3:    prog = {4'd5, 4'd0, 8'd7};   
      5'd4:    prog = {4'd4, 4'd0, 8'd0};   
      5'd5:    prog = {4'd2, 4'd0, 8'd3};   
      5'd6:    prog = {4'd6, 4'd0, 8'd4};   
      5'd7:    prog = {4'd1, 4'd0, 8'h01};  
      5'd8:    prog = {4'd2, 4'd0, 8'd3};   
      5'd9:    prog = {4'd3, 4'd0, 8'd0};   
      default: prog = 16'h0000;             
    endcase
  endfunction

  reg [7:0] in1, in2;      
  reg [7:0] uin1, uin2;    
  reg [2:0] sck_d, mosi_d, cs_d;

  wire loading  = ~cs_d[1];
  wire sck_rise = sck_d[1] & ~sck_d[2];
  wire mosi     = mosi_d[1];

 
  reg [15:0] mem [0:31];
  reg [7:0]  pins, uio_reg, uio_oe_reg, osr, isr, x, wcnt;
  reg [4:0]  pc;
  reg        waiting;
  reg [19:0] shreg;
  reg [4:0]  bitcnt;
  integer    i;

  wire [15:0] instr = mem[pc];
  wire [3:0]  op    = instr[15:12];
  wire [7:0]  imm   = instr[7:0];
  wire [2:0]  pidx  = imm[2:0];
  wire        lvl   = imm[3];
  wire [20:0] word  = {shreg, mosi};

  always @(posedge clk) begin
    if (!rst_n) begin
      for (i = 0; i < 32; i = i + 1) mem[i] <= prog(i[4:0]);
      in1 <= 0; in2 <= 0; uin1 <= 0; uin2 <= 0;
      sck_d <= 0; mosi_d <= 0; cs_d <= 3'b111;
      pc <= 0; pins <= 8'h01; osr <= 0; isr <= 0; x <= 0; wcnt <= 0;
      waiting <= 0; shreg <= 0; bitcnt <= 0;
      uio_reg <= 0; uio_oe_reg <= 0;
    end else begin
      in1    <= ui_in;          in2  <= in1;
      uin1   <= uio_in;         uin2 <= uin1;
      sck_d  <= {sck_d[1:0], uio_in[0]};
      mosi_d <= {mosi_d[1:0], uio_in[1]};
      cs_d   <= {cs_d[1:0], uio_in[2]};

  
      if (!loading) bitcnt <= 0;
      else if (sck_rise) begin
        shreg <= word[19:0];
        if (bitcnt == 5'd20) begin
          mem[word[20:16]] <= word[15:0];
          bitcnt <= 0;
        end else bitcnt <= bitcnt + 1;
      end


      if (loading) begin
        pc <= 0; waiting <= 0; pins <= 8'h01; uio_oe_reg <= 0;
      end else if (waiting) begin
        if (wcnt == 0) begin waiting <= 0; pc <= pc + 1; end
        else wcnt <= wcnt - 1;
      end else begin
        pc <= pc + 1;
        case (op)
          4'd1:  pins <= imm;
          4'd2:  if (imm != 0) begin waiting <= 1; wcnt <= imm - 1; pc <= pc; end
          4'd3:  pc <= imm[4:0];
          4'd4:  begin
                   if (instr[8]) begin
                     uio_oe_reg[pidx] <= ~osr[0]; uio_reg[pidx] <= 1'b0;
                   end else pins[pidx] <= osr[0];
                   osr <= {1'b0, osr[7:1]};
                 end
          4'd5:  x <= imm;
          4'd6:  if (x != 0) begin x <= x - 1; pc <= imm[4:0]; end
          4'd7:  osr <= imm;
          4'd8:  if (in2[pidx] != lvl) pc <= pc;
          4'd9:  isr <= {in2[pidx], isr[7:1]};
          4'd10: if (in2[imm[7:5]] == instr[8]) pc <= imm[4:0];
          4'd11: pins <= isr;
          4'd12: pins[pidx] <= lvl;
          4'd13: uio_oe_reg[pidx] <= lvl;
          4'd14: uio_reg[pidx] <= lvl;
          4'd15: isr <= {uin2[pidx], isr[7:1]};
          default: ;
        endcase
      end
    end
  end

  assign uo_out  = pins;
  assign uio_out = uio_reg;
  assign uio_oe  = loading ? 8'h00 : uio_oe_reg;

  wire _unused = &{ena, instr[11:9], 1'b0};

endmodule
