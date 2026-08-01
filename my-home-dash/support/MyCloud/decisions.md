# MyCloud Decisions

This document records the key operational decisions for backing up the `E:` drive (`WD_Black`) to the My Cloud `WD_Black` share.

## Decision 1: Use The My Cloud `WD_Black` Share As The Backup Target

- Status: accepted
- Decision: The destination for this backup workstream is `\\wdmycloud\WD_Black`.
- Why: That share is the current reachable path for the first-generation WD My Cloud on this network.
- Alternatives considered:
  - Backup to the web UI path: rejected because the web UI is for management, not file transfer.
  - Backup to a different share name: rejected because `WD_Black` is the known current target.
- Consequences:
  - Commands and documentation should consistently use the SMB share path.
  - Network share availability must be verified before long copy jobs begin.
- Rollback path: Update the destination path in the backup command and notes if the share location changes.

## Decision 2: Execute The Backup One Directory At A Time

- Status: accepted
- Decision: The backup strategy is to run one `robocopy` mirror command per top-level directory instead of running a single all-drive job immediately.
- Why: This reduces risk, makes failures easier to isolate, and allows throughput estimates to be based on real runs.
- Alternatives considered:
  - One full-drive backup in a single pass: rejected because it is harder to monitor and recover cleanly.
  - File-by-file manual copying: rejected because it is too slow and inconsistent.
- Consequences:
  - Progress tracking is clearer.
  - Each directory gets its own destination path and log file.
  - The plan can be adjusted between phases based on real transfer behavior.
- Rollback path: Merge phases later into a broader command only after the per-directory approach is proven.

## Decision 2A: Standardize On A Per-Directory `robocopy` Mirror Template

- Status: accepted
- Decision: Each backup phase should use this command shape, with the source directory name and log file changed per run: `robocopy "E:\<DirectoryName>" "\\wdmycloud\WD_Black\E_Drive_Backup\<DirectoryName>" /MIR /Z /FFT /R:2 /W:5 /XJ /MT:16 /DCOPY:DAT /COPY:DAT /NP /TEE /LOG:"C:\Users\jpful\Documents\robocopy_<directoryname>_to_wdblack2.log"`.
- Why: This preserves the user's preferred `robocopy` settings while adapting them to the safer one-directory-at-a-time execution model.
- Alternatives considered:
  - Keep the older `/E` copy-only commands: rejected because the requested command uses `/MIR` and should be reflected in the plan.
  - Run the provided command against `E:\` directly: rejected because the workstream is intentionally staged one top-level directory at a time.
- Consequences:
  - The backup is now a mirror operation for each directory, so deletions in the source directory will be reflected in the destination directory for that phase.
  - Every live run must confirm the exact source directory before execution.
  - Log files will be written to `C:\Users\jpful\Documents` using one file per directory.
- Rollback path: Replace `/MIR` with `/E` or another copy mode if mirroring proves too destructive for the intended workflow.

## Decision 3: Use The Directory Order `MyProjects`, Then `ProgramFiles`, Then Everything Else

- Status: accepted
- Decision: Backup phases will run in this order: `MyProjects`, then `ProgramFiles`, then the remaining content on `E:`.
- Why: `MyProjects` is the highest-priority content and the best first candidate for validating the process before wider backup passes.
- Alternatives considered:
  - Alphabetical directory order: rejected because it does not reflect priority.
  - Largest directories first: rejected because priority matters more than size alone.
- Consequences:
  - Early effort focuses on the most important directory.
  - Later commands must avoid duplicating already completed phases.
- Rollback path: Reorder later phases if actual data size, risk, or urgency changes.

## Decision 4: Provide ETA Updates Hourly

- Status: accepted
- Decision: The backup process should provide ETA updates on an hourly cadence.
- Why: Long-running copy operations are easier to manage when progress is reported at a predictable interval.
- Alternatives considered:
  - No ETA reporting: rejected because it makes long jobs opaque.
  - Constant minute-by-minute reporting: rejected because it is noisier than needed.
- Consequences:
  - The chosen copy command or wrapper should capture enough progress data to estimate remaining time.
  - Initial ETA quality may be rough until the first backup throughput is measured.
- Rollback path: Change the reporting cadence if hourly updates prove too sparse or too noisy.

## Decision 5: Use The First Phase As The Baseline For Future Estimates

- Status: accepted
- Decision: The `MyProjects` backup run will establish the initial throughput and ETA assumptions for later phases.
- Why: Real observed transfer speed on this workstation and NAS is more reliable than theoretical estimates.
- Alternatives considered:
  - Estimate all future phases before any run: rejected because it would be guesswork.
  - Wait until all phases are complete to estimate performance: rejected because planning needs early feedback.
- Consequences:
  - The first run should be logged carefully.
  - Later ETA updates can be improved after the first measured transfer.
- Rollback path: Replace the baseline if later phases reveal materially different throughput characteristics.

## Decision 6: Skip System Metadata Folders But Include Root-Level Files

- Status: accepted
- Decision: The continuation run should skip `$RECYCLE.BIN` and `System Volume Information`, but it should still copy root-level files from `E:\` into `\\wdmycloud\WD_Black\E_Drive_Backup`.
- Why: The system metadata folders are noisy, privilege-sensitive, and low-value for this NAS backup, while the root files are part of the user-visible drive content.
- Alternatives considered:
  - Copy every top-level item without exceptions: rejected because system metadata folders can fail or add low-value churn.
  - Ignore root-level files entirely: rejected because that would leave part of the drive unprotected.
- Consequences:
  - The backup queue remains focused on the meaningful user data.
  - The continuation workflow needs a final root-files pass after the directory phases complete.
- Rollback path: Remove the exclusions and treat the drive root as a single broader copy target if a true block-level-style mirror is preferred later.