# MyCloud TODO

## Overall Status

- [x] Goal document exists.
- [x] Decisions document exists.
- [x] TODO tracker exists.
- [x] Backup command and logging approach are finalized.
- [x] Initial backup execution has started.
- [ ] Hourly ETA reporting is in place.

## Current Snapshot

- Current phase: continuation
- Last completed checkpoint: `Downloads`, `tmp`, and the root-level `E:\` file pass all completed successfully on `2026-04-05`; the only recorded issue across the remaining queue is one inaccessible source file during `Backup`.
- Safe resume point: no additional folder phases remain. The only unresolved item is the inaccessible `Backup` reparse-point file `E:\Backup\Users\Valued Customer\AppData\Local\JetBrains\IdeaIC2024.1\.port`; retry it only after the source object becomes readable.
- Next action: optional follow-up only, either verify the NAS copy set or retry the single failed file under `E:\Backup\Users\Valued Customer\AppData\Local\JetBrains\IdeaIC2024.1\.port`.
- Current blocker: one source file in `Backup` is still inaccessible, producing `ERROR 1920` in both the full rerun and a targeted single-file retry; all later phases completed.
- Progress evidence: `C:\Users\jpful\Documents\robocopy_downloads_to_wdblack2.log`, `C:\Users\jpful\Documents\robocopy_tmp_to_wdblack2.log`, and `C:\Users\jpful\Documents\robocopy_root_files_to_wdblack2.log` all contain completed robocopy summaries from `2026-04-05`.
- Monitoring update: remaining queue ETA is now effectively `0`; `Downloads` finished in seconds, `tmp` finished in less than a second, and the root-level file pass also finished in less than a second.
- Command source note: these commands are reconstructed from the current `E:` directory layout and saved workspace context, not from inaccessible prior chat history.
- ETA helper script: `support\MyCloud\estimate_backup_eta.ps1` now calculates fast ETA from cached directory sizes plus incremental robocopy log parsing and reports an expected completion date/time.

## Standard Command Pattern

- Per-directory command template: `robocopy "E:\<DirectoryName>" "\\wdmycloud\WD_Black\E_Drive_Backup\<DirectoryName>" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_<directoryname>_to_wdblack2.log"`
- Execution rule: run exactly one top-level `E:` directory per command.
- Destination rule: keep all copies under `\\wdmycloud\WD_Black\E_Drive_Backup`.
- Logging rule: use one log file per directory in `C:\Users\jpful\Documents`.
- Safety note: `/MIR` mirrors deletions within the target directory, so confirm the source and destination before each live run.

## Update Rules

- Update this file immediately when a step finishes, stalls, or changes state.
- Never delete completed steps. Mark them complete and append new notes below them.
- Record the exact command used for every live backup run.
- Record the log file path for every live backup run.
- Record start time, stop time, exit code, and summary result for every live backup run.
- Update `Safe resume point` after each successful checkpoint.
- If work stops unexpectedly, record the blocker and the last verified good state before doing anything else.
- Reuse prior checkpoints instead of restarting from the top unless the notes say the previous attempt is invalid.

## Completed

- [x] Define the goal for backing up `E:` (`WD_Black`) to the My Cloud `WD_Black` share.
- [x] Define the initial execution order: `MyProjects`, then `ProgramFiles`, then everything else.
- [x] Create supporting planning documents in `support/MyCloud/`.

## Execution Ledger

### Phase 1: `MyProjects`

- Status: completed
- Source: `E:\MyProjects`
- Destination: `\\wdmycloud\WD_Black\E_Drive_Backup\MyProjects`
- Proposed command: `robocopy "E:\MyProjects" "\\wdmycloud\WD_Black\E_Drive_Backup\MyProjects" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_myprojects_to_wdblack2.log"`
- Approved command status: approved and started
- Log file: `C:\Users\jpful\Documents\robocopy_myprojects_to_wdblack2.log`
- Started at: `2026-04-03 09:03:46`
- Completed at: `2026-04-03 15:25:22`
- Last checkpoint: live mirror run completed successfully after the destination share was restored with `admin` and a blank password.
- ETA basis: actual robocopy summary throughput from the completed phase.
- Resume rule: do not restart this phase from scratch unless the command, destination, or prior run validity changes.

Checklist:

- [x] Confirm source path.
- [x] Confirm destination path.
- [x] Record proposed backup command.
- [x] Record proposed log file path.
- [x] Approve backup command for live run.
- [x] Start backup.
- [x] Capture first trustworthy throughput sample.
- [x] Record first provisional ETA update.
- [x] Mark phase complete.

Summary:

- Bytes copied: `79.760 g`
- Elapsed copy time: `5:55:56`
- Transfer rate: `4,010,138 Bytes/sec` (`229.462 MegaBytes/min`)
- Failures: `0`

### Phase 2: `ProgramFiles`

- Status: completed
- Source: `E:\ProgramFiles`
- Destination: `\\wdmycloud\WD_Black\E_Drive_Backup\ProgramFiles`
- Proposed command: `robocopy "E:\ProgramFiles" "\\wdmycloud\WD_Black\E_Drive_Backup\ProgramFiles" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_programfiles_to_wdblack2.log"`
- Approved command status: approved for continuation queue
- Log file: `C:\Users\jpful\Documents\robocopy_programfiles_to_wdblack2.log`
- Started at: `2026-04-03 23:47:58`
- Completed at: `2026-04-04 00:14:06`
- Last checkpoint: continuation queue finished `ProgramFiles` with robocopy exit code `1`, which is a successful run with copied files.
- ETA basis: actual robocopy summary throughput from the completed phase.
- Resume rule: do not begin until Phase 1 command behavior is proven.

Checklist:

- [x] Confirm source path.
- [x] Confirm destination path.
- [x] Record proposed backup command.
- [x] Record proposed log file path.
- [x] Approve backup command for live run.
- [x] Start backup.
- [x] Record hourly ETA update.
- [x] Mark phase complete.

Summary:

- Bytes copied: `25.348 g`
- Bytes skipped: `11.876 g`
- Elapsed copy time: `0:22:58`
- Transfer rate: `19,737,582 Bytes/sec` (`1,129.394 MegaBytes/min`)
- Failures: `0`

### Phase 3: Everything Else

- Status: completed with one source-file access failure in `Backup`
- Source: remaining top-level directories on `E:`: `.pnpm-store`, `Backup`, `Downloads`, and `tmp`
- Destination: matching folders under `\\wdmycloud\WD_Black\E_Drive_Backup`
- Full commands:
  - `robocopy "E:\.pnpm-store" "\\wdmycloud\WD_Black\E_Drive_Backup\.pnpm-store" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_pnpm-store_to_wdblack2.log"`
  - `robocopy "E:\Backup" "\\wdmycloud\WD_Black\E_Drive_Backup\Backup" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_backup_to_wdblack2.log"`
  - `robocopy "E:\Downloads" "\\wdmycloud\WD_Black\E_Drive_Backup\Downloads" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_downloads_to_wdblack2.log"`
  - `robocopy "E:\tmp" "\\wdmycloud\WD_Black\E_Drive_Backup\tmp" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_tmp_to_wdblack2.log"`
- Batch helper command: not used because this workstream intentionally runs one directory per command.
- Approved command status: pending list of remaining directories
- Approved command status: approved through `support\MyCloud\continue_e_drive_backup.ps1`
- Log file: one log per top-level directory in `C:\Users\jpful\Documents`
- Started at: `2026-04-04 00:14:07` for `.pnpm-store`; `2026-04-04 00:14:38` for the first `Backup` attempt; `2026-04-05 00:30:36` for the clean `Backup` rerun; `2026-04-05 11:35:07` for `Downloads`; `2026-04-05 11:35:47` for `tmp`
- Last checkpoint: `.pnpm-store` completed with robocopy exit code `0`; `Backup` completed its rerun with one failed source file; `Downloads` completed with robocopy exit code `1`; `tmp` completed with robocopy exit code `0`.
- ETA basis: no remaining time in this phase. `Downloads` ended at `2026-04-05 11:35:23`, and `tmp` ended at `2026-04-05 11:35:49`.
- Resume rule: exclude anything already completed in earlier phases.

Checklist:

- [x] List remaining top-level directories.
- [ ] Exclude `MyProjects`.
- [x] Exclude `ProgramFiles`.
- [x] Record full command for `.pnpm-store`.
- [x] Record full command for `Backup`.
- [x] Record full command for `Downloads`.
- [x] Record full command for `tmp`.
- [x] Record that no batch helper command should be used.
- [ ] Approve backup command(s) for live run.
- [x] Approve backup command(s) for live run.
- [x] Start backup.
- [x] Record hourly ETA update.
- [x] Mark phase complete.

### Phase 4: Root-Level `E:\` Files

- Status: completed
- Source: root-level files directly under `E:\`
- Destination: `\\wdmycloud\WD_Black\E_Drive_Backup`
- Command shape: `robocopy "E:\" "\\wdmycloud\WD_Black\E_Drive_Backup" <root-file-list> /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_root_files_to_wdblack2.log"`
- Approved command status: approved through `support\MyCloud\continue_e_drive_backup.ps1`
- Log file: `C:\Users\jpful\Documents\robocopy_root_files_to_wdblack2.log`
- Started at: `2026-04-05 11:35:49`
- Completed at: `2026-04-05 11:35:50`
- Last checkpoint: root-level file pass completed successfully for `license.rtf`.
- ETA basis: complete.
- Resume rule: exclude system metadata folders; only copy root-level files that actually exist at runtime.

## Blockers And Recovery Notes

- Existing staged robocopy attempts on `E_Staged_Backup` include `ERROR 1326` against `\\wdmycloud\WD_Black`, so prior logs should not be treated as valid throughput baselines until NAS authentication is corrected.
- The MyCloud was powered off abruptly. Do not treat the NAS state as trustworthy again until it finishes booting and the `WD_Black` share is reachable over SMB.
- Recovery check on 2026-04-03: `wdmycloud` responds to ping and TCP port `445` is open, but `net view \\wdmycloud` returns `System error 5` and `dir \\wdmycloud\WD_Black` returns `The user name or password is incorrect`.
- Access recovery update on 2026-04-03: `dir \\wdmycloud\WD_Black` succeeded after reconnecting with `admin` and a blank password, and the `MyProjects` mirror run began at `09:03:46`.
- Continuation update on 2026-04-04: the queue completed `ProgramFiles` and `.pnpm-store`, then stopped during the first `Backup` attempt; the safe recovery action is to rerun the `Backup` mirror command directly against the same source, destination, and log path.
- Continuation update on 2026-04-05: the direct `Backup` rerun from `2026-04-04 15:22:16` was confirmed hung because its log never advanced past startup, so that process was terminated and a clean rerun was started at `2026-04-05 00:30:36`.
- Continuation update on 2026-04-05: the clean `Backup` rerun ended with `ERROR 1920` on `E:\Backup\Users\Valued Customer\AppData\Local\JetBrains\IdeaIC2024.1\.port`, then `Downloads`, `tmp`, and the root-level file pass completed successfully.
- Follow-up update on 2026-04-05: a targeted retry of `E:\Backup\Users\Valued Customer\AppData\Local\JetBrains\IdeaIC2024.1\.port` also failed immediately with `ERROR 1920`, and a direct `Copy-Item` attempt returned `The file cannot be accessed by the system`, confirming this remaining item is blocked at the source.

## Run History

- `2026-04-03 09:03:46` to `2026-04-03 15:25:22`: `MyProjects` completed successfully.
- `2026-04-03 23:47:58` to `2026-04-04 00:14:06`: `ProgramFiles` completed successfully with robocopy exit code `1`.
- `2026-04-04 00:14:07` to `2026-04-04 00:14:37`: `.pnpm-store` completed successfully with robocopy exit code `0`.
- `2026-04-04 00:14:38` to unknown stop time: initial `Backup` attempt started and was interrupted.
- `2026-04-04 15:22:16` to `2026-04-05 00:30:36`: direct `Backup` rerun was present but effectively hung, with no log advancement beyond startup.
- `2026-04-05 00:30:36` to `2026-04-05 03:32:54`: clean `Backup` rerun completed with one failed source file (`.port`) and no other recorded failures.
- `2026-04-05 11:35:07` to `2026-04-05 11:35:23`: `Downloads` completed successfully with robocopy exit code `1`.
- `2026-04-05 11:35:47` to `2026-04-05 11:35:49`: `tmp` completed successfully with robocopy exit code `0`.
- `2026-04-05 11:35:49` to `2026-04-05 11:35:50`: root-level `E:\` file pass completed successfully.
- `2026-04-05 13:30:02` to `2026-04-05 13:30:03`: targeted retry for `.port` failed again with robocopy `ERROR 1920`, confirming the final blocked item cannot currently be read from the source.

## Active Work Queue

### 1. Finalize The Backup Command For `MyProjects`

- Status: next
- Why it matters: The first directory should be copied with a repeatable, reviewable command before broader backup work begins.
- Acceptance criteria:
  - Confirm source path for `E:\MyProjects`.
  - Confirm destination path under `\\wdmycloud\WD_Black\E_Drive_Backup`.
  - Review the recorded `robocopy` command.
  - Confirm the mirror strategy with `/MIR`.
  - Confirm logging and retry options.

### 2. Run The First Backup And Capture Baseline Throughput

- Status: next
- Why it matters: A real first run is needed to estimate completion time for larger directory groups.
- Acceptance criteria:
  - Start the `MyProjects` backup.
  - Capture bytes copied, elapsed time, and any skipped files.
  - Record observed throughput for ETA calculations.

### 3. Add Hourly ETA Reporting

- Status: next
- Why it matters: The plan calls for hourly ETA updates during backup execution.
- Acceptance criteria:
  - Define how progress will be measured.
  - Use `support\MyCloud\estimate_backup_eta.ps1` for quick ETA checks without rescanning unless a refresh is explicitly requested.
  - Treat ETA as an expected completion timestamp, not just a duration.
  - Report remaining time at least once per hour while the backup is running.
  - Keep the reporting simple enough to maintain during long copy jobs.

### 4. Prepare The `ProgramFiles` Backup Pass

- Status: candidate
- Why it matters: The second pass should not start until the first pass is understood and the command strategy is stable.
- Acceptance criteria:
  - Confirm exact source path for `ProgramFiles` on `E:`.
  - Reuse or refine the command based on `MyProjects` results.
  - Confirm any exclusions that should apply.

### 5. Define The Catch-All Pass For Everything Else

- Status: candidate
- Why it matters: The final pass should avoid recopying directories already handled in earlier phases.
- Acceptance criteria:
  - List the remaining top-level directories on `E:`.
  - Exclude `MyProjects` and `ProgramFiles` from the catch-all pass.
  - Confirm whether any large or low-value folders should be skipped.
  - Record full `robocopy` mirror commands for each remaining top-level directory.

## Working Notes

- Keep the process one directory at a time.
- Treat `MyProjects` as the proving run for command shape, throughput, and ETA quality.
- Prefer a logged command that can be rerun safely after interruptions.
- Keep destination rooted at `\\wdmycloud\WD_Black\E_Drive_Backup` unless the share layout changes.
- Use `estimate_backup_eta.ps1` with cached sizes and incremental robocopy log parsing as the default ETA workflow so repeat checks stay fast.
- This file is the operational checkpoint document, not just a planning note.
- Each phase should always show `status`, `last checkpoint`, `approved command`, and `log file` before live execution continues.
- The currently recorded commands are mirror commands because they use `/MIR`, so each live run must verify the exact directory pair before execution.