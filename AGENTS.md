# Repository Guidelines

This repository builds a FreeSWITCH image from source via a single `Dockerfile`. Keep changes small, documented, and reproducible.

## Project Structure & Organization

- `Dockerfile`: primary build and install logic.
- `README.md`: project overview and usage notes.  
If you add files, prefer `scripts/` for helper shell scripts, `config/` for sample FreeSWITCH configs, and `tests/` for validation scripts.

## Build, Run, and Development

- Build image: `docker build -t freeswitch:dev .`
- Run FreeSWITCH: `docker run --rm --name freeswitch -p 5060:5060/udp -p 8021:8021/tcp freeswitch:dev`
- Attach CLI: `docker exec -it freeswitch fs_cli`  
When changing the `Dockerfile`, ensure the image still builds cleanly on a fresh checkout.

## Coding Style & Naming

- Dockerfile: group related steps, keep comments accurate, and avoid unnecessary layers.
- Shell scripts: use `#!/usr/bin/env bash` and `set -euo pipefail`; 2-space indentation.
- Names: use descriptive, lowercase file and directory names with hyphens (e.g., `build-utils.sh`).

## Testing Guidelines

No formal test suite exists yet. At minimum:
- Build the image and ensure the build completes without errors.
- Start a container and verify FreeSWITCH starts and accepts `fs_cli` connections.  
Place future automated tests in `tests/` and provide a `tests/run.sh` entrypoint.

## Commit & Pull Request Guidelines

- Commit messages: short, imperative, and scoped (e.g., `Add mod_audio_fork build step`).
- PRs: describe the motivation, key changes, and how you tested (commands and sample output). Link related issues when available.

## Security, Configuration, and Agent Notes

Do not commit secrets or environment-specific configs; prefer documenting volume mounts and env vars in `README.md`. When editing build steps (mirrors, dependencies, modules), keep them minimal and explain rationale in comments and PR descriptions.

