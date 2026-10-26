# Repository Guidelines

## Project Structure & Module Organization

This repository is currently empty apart from this guide. As the project takes shape, keep application code, tests, and assets in clearly named directories. Group related code by feature or module, and place tests close to the code they exercise or in a corresponding test directory. Document any new top-level directories here.

## Build, Test, and Development Commands

No build system, dependencies, or development commands are configured yet. When introducing a toolchain, document the exact commands for installing dependencies, running the project, building it, and executing tests. Prefer reproducible commands that work from the repository root, and commit the relevant configuration and lockfiles.

## Coding Style & Naming Conventions

Follow the conventions of the language and framework introduced to the project. Use consistent indentation and descriptive names; avoid unrelated formatting changes. Add a formatter or linter when the toolchain is established, and document how to run it. Name files and modules consistently with their surrounding code.

## Testing Guidelines

No test framework or coverage target is currently defined. Add automated tests for new behavior and regression fixes as the project develops. Use descriptive test names that state the behavior being checked, and document the test command and any required setup. Run the relevant tests before submitting changes.

## Commit & Pull Request Guidelines

There is no Git history from which to infer a commit convention. Write concise, imperative commit subjects, such as `Add drawing canvas`, and keep each commit focused. Pull requests should explain the change and its motivation, link any relevant issue, and describe the checks performed. Include screenshots or recordings for visible interface changes.

## Configuration & Security

Do not commit credentials, private keys, or local secrets. Document required environment variables with safe example values, and keep machine-specific configuration out of version control.
