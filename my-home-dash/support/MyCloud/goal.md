The goal is to back up the E: drive (WD_Black) to MyCloud using the WD_Black share.

The strategy is currently one directory at a time.

Use this robocopy pattern for each top-level directory instead of mirroring the whole `E:` drive in one command:

`robocopy "E:\<DirectoryName>" "\\wdmycloud\WD_Black\E_Drive_Backup\<DirectoryName>" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_<directoryname>_to_wdblack2.log"`

This keeps the destination rooted under `\\wdmycloud\WD_Black\E_Drive_Backup` while still handling the backup one source directory at a time.

Order of work:

1. Do MyProjects first.
2. Follow with ProgramFiles.
3. Then do everything else.

Provide an ETA hourly.