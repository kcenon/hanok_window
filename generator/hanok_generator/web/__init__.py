"""Local web interface for hanok-window-generator.

Every package copies the top-level modules, engine, presets and schema into its
source/ folder, and that copy is part of the package_id. This subpackage is not
collected (package.source_files() does not recurse), so the web layer can change
without changing any package_id.
"""
