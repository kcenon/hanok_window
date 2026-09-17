# DWG regression in CI

The Windows matrix job installs ODA File Converter 27.1.0 and runs
`GeneratorTests.test_dwg_round_trip_keeps_every_check`. The R3 and artwork A2
drawings each make a real DXF → DWG → DXF round trip. Each returned drawing
must pass all 71 checks and preserve the count of entities carrying XDATA.
The test prints each case's result and converter version after its assertions pass.

## Usage basis reviewed on 2026-09-17 (KST)

The maintainer confirmed that this repository's CI is for non-commercial use.
ODA's [official FAQ](https://www.opendesign.com/faq/question/what-are-oda-viewer-and-oda-file-converter)
allows nonmembers to use File Converter for non-commercial applications.
The [official download page](https://www.opendesign.com/guestfiles/oda_file_converter)
documents command-line batch conversion. This workflow applies that allowance
to non-commercial regression testing on temporary runners. The sources do not
specifically name GitHub Actions; this is the basis for this workflow, not a
claim of permission for commercial use or redistribution.

The installed 27.1.0 package's cached MSI was inspected read-only: its dialogs
contain a copyright warning, with no separate license-agreement dialog or
license text among the installed files. The WinGet label `Freeware` is not the
basis for the usage decision. Reassess the terms before changing the use or
converter version; commercial use needs an appropriate ODA license.

The converter and installer are never committed, uploaded as artifacts, or
added to the Python distribution or generated CAD packages. Conversion stays
local to the runner; no drawing is sent to an external conversion service.

## Installation and failure handling

`.github/scripts/install-oda.ps1` downloads the official Windows MSI directly.
The Windows Server 2025 [runner software inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
does not list WinGet, so the workflow does not require it. The setup log also
reports whether WinGet is present on the actual runner.

Version 27.1.0, the ODA download URL, and SHA-256 are pinned to the
[WinGet installer manifest](https://github.com/microsoft/winget-pkgs/blob/29b5dd318c692ec734ce503c7a7162da03535921/manifests/o/ODA/ODAFileConverter/27.1.0/ODA.ODAFileConverter.installer.yaml).
On the review date, ODA's download page also linked this Windows installer;
its downloaded bytes matched the pinned checksum.
The SHA-256 is `3D5961F510CF95F398B8E2920899DC8E8C51ADECDAF5B20A40B3D1A29269DE81`.
A mismatch prevents execution. The MSI runs silently without restarting;
exit codes 0 and 3010 are accepted only if the expected executable exists.
The download timeout is 90 seconds and the setup step has a five-minute limit.

Every matrix job initially sets `HANOK_ODAFC` to a nonexistent path. Only
successful Windows setup publishes the installed path through `GITHUB_ENV`.
Thus download, installation, or discovery failure cannot accidentally select
a partial installation or another converter through `PATH` or installation folders.
The status step reports availability and setup outcome, and warns on setup failure.
Linux and macOS keep the missing-converter override and log the named test's skip.

Only the installation step has `continue-on-error`. Once the converter is
available, conversion errors, timeouts, and assertion failures fail CI normally.
The setup helper's tests simulate successful installation, reboot-required
success, download failure, hash mismatch, installer failure, and a missing
executable, without downloading or installing software.

## Verification and updates

The generator suite uses verbose unittest discovery. Running the test file
directly would rewrite tracked `tests/results.json`; CI does not do that.
An additional Windows invocation overrides `HANOK_ODAFC` with a missing path
and checks the existing skip behavior even after successful installation.

Review the named test and both case results in the Windows job log. A green
workflow in which every DWG test skipped does not prove DWG coverage. The
existing test suites and cross-platform R3 package comparison must also pass.

To update ODA, review its current terms and official download availability,
then update the version, URL, checksum, and expected installation path together
with the helper tests and this note. ODA's FAQ warns that older versions may
be restricted to members; an unavailable pinned download must remain a visible
setup failure rather than being replaced with an unverified mirror.
