       IDENTIFICATION DIVISION.
       PROGRAM-ID. COMPUTE.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TEMP PIC 9(8).

       LINKAGE SECTION.
       01 LK-A              PIC 9(4).
       01 LK-B              PIC 9(4).
       01 LK-SUM            PIC 9(8).
       01 LK-PRODUCT        PIC 9(8).

       PROCEDURE DIVISION USING LK-A LK-B LK-SUM LK-PRODUCT.
       DO-COMPUTE.
           ADD LK-A TO LK-B GIVING LK-SUM.
           MULTIPLY LK-A BY LK-B GIVING LK-PRODUCT.
           GOBACK.
