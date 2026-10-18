#!/bin/sh
# `npm run app` hands this to `tauri dev` in place of cargo. It builds the window's program, then
# starts it under the name "LocalFlow Research Journey": macOS names a program that is not in an
# app bundle after its file, and a Rust binary's own file name cannot contain spaces.
# It ignores the arguments `tauri dev` forwards (always a plain debug build, so `--release` or
# `--features` given to `npm run app` have no effect) and expects the default target directory,
# not a CARGO_TARGET_DIR or build.target-dir override.
set -e
cd "$(dirname "$0")/../src-tauri"
cargo build --no-default-features --color always
ln -f target/debug/localflow-research-journey "target/debug/LocalFlow Research Journey"
exec "target/debug/LocalFlow Research Journey"
