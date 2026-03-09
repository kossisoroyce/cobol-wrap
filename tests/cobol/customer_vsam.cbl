       IDENTIFICATION DIVISION.
       PROGRAM-ID. CUSTVSAM.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUSTOMER-MASTER ASSIGN TO 'custmast.vsam'
               ORGANIZATION IS INDEXED
               RECORD KEY IS CUST-KEY
               ACCESS MODE IS DYNAMIC.

       DATA DIVISION.
       FILE SECTION.
       FD CUSTOMER-MASTER.
       01 CUSTOMER-MASTER-REC.
          05 CUST-KEY          PIC X(10).
          05 CUST-NAME         PIC X(40).
          05 CUST-ADDR1        PIC X(30).
          05 CUST-ADDR2        PIC X(30).
          05 CUST-CITY         PIC X(20).
          05 CUST-STATE        PIC X(2).
          05 CUST-ZIP          PIC X(10).
          05 CUST-BALANCE      PIC S9(10)V99 COMP-3.
          05 CUST-CREDIT-LIMIT PIC 9(8)V99 COMP-3.
          05 CUST-TYPE         PIC X(1).
             88 RETAIL-CUST    VALUE 'R'.
             88 WHOLESALE-CUST VALUE 'W'.
             88 VIP-CUST       VALUE 'V'.

       WORKING-STORAGE SECTION.
       01 WS-IO-STATUS         PIC XX.
          88 IO-SUCCESS        VALUE '00'.
          88 IO-NOT-FOUND      VALUE '23'.

       LINKAGE SECTION.
       01 LK-CUST-KEY          PIC X(10).
       01 LK-OPERATION         PIC X(1).
       01 LK-RETURN-CODE       PIC S9(2).

       PROCEDURE DIVISION USING LK-CUST-KEY LK-OPERATION LK-RETURN-CODE.
       PROCESS-CUSTOMER.
           MOVE 0 TO LK-RETURN-CODE.
           GOBACK.
