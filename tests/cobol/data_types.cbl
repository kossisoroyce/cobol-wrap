       IDENTIFICATION DIVISION.
       PROGRAM-ID. DATATYPES.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-NUMERIC-TYPES.
          05 WS-SMALL-INT      PIC 9(4).
          05 WS-LARGE-INT      PIC 9(18).
          05 WS-SIGNED         PIC S9(9).
          05 WS-DECIMAL-V99    PIC 9(10)V99.
          05 WS-DECIMAL-V9-2   PIC 9(10)V9(2).
          05 WS-COMP3-AMT      PIC S9(13)V99 COMP-3.
          05 WS-COMP-BIN       PIC 9(9) COMP.
          05 WS-BINARY         PIC 9(9) BINARY.
       01 WS-STRING-TYPES.
          05 WS-SHORT-STR      PIC X(10).
          05 WS-LONG-STR       PIC X(255).
          05 WS-ALPHA-ONLY     PIC A(20).
       01 WS-OCCURS-EXAMPLE.
          05 WS-FIXED-ARR      PIC X(5) OCCURS 10 TIMES.
       01 WS-OCCURS-DEP.
          05 WS-COUNT          PIC 9(2).
          05 WS-DYN-ARR        PIC X(10) OCCURS 1 TO 20 TIMES
                                         DEPENDING ON WS-COUNT.
       01 WS-REDEFINES-BASE    PIC X(10).
       01 WS-REDEFINES-NUM REDEFINES WS-REDEFINES-BASE PIC 9(10).
       01 WS-STATUS-CODE       PIC X(2).
          88 STATUS-OK         VALUE '00'.
          88 STATUS-WARN       VALUE '01'.
          88 STATUS-ERR        VALUE '99'.

       LINKAGE SECTION.
       01 LK-INPUT             PIC X(100).
       01 LK-OUTPUT            PIC X(100).
       01 LK-RESULT-CODE       PIC S9(4).

       PROCEDURE DIVISION USING LK-INPUT LK-OUTPUT LK-RESULT-CODE.
       PROCESS-DATA.
           MOVE LK-INPUT TO LK-OUTPUT.
           MOVE 0 TO LK-RESULT-CODE.
           GOBACK.
