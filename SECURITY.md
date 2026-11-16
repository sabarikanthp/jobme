# Security policy

JobMe runs on your own computer and handles your resume, job history and an AI provider API key, so security reports are taken seriously. It is a personal open-source project, maintained on a best-effort basis: there is no guaranteed response time.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting instead: open the repository's **Security** tab and choose **Report a vulnerability**. Describe what you did, what you expected and what happened. Do not include real personal data, resumes or API keys; made-up examples are enough.

If private reporting is not available to you, open an issue that says only that you have a security report and no details, and the maintainer will arrange a private channel.

## What is in scope

The code in this repository: the web app and its API, how it stores your data and your API key, the scheduling code, and the helper scripts. The README explains how it is meant to be used (on your own computer, with the key kept in your system's credential store).

Things that are **not** vulnerabilities in this project:

- Someone who already has access to your computer or your user account being able to read your JobMe data (it is a local app; protect the computer).
- Problems in your AI provider, or in software JobMe depends on; report those to their maintainers.
- Running JobMe somewhere other than your own computer, for example exposing it to a network it was not designed for.

## Supported versions

Only the latest commit on `main` is supported. Fixes are made there; there are no maintained older releases.

## If you think a key has leaked

Revoke the key at your AI provider first, then save a new one in JobMe's Settings. Revoking is the step that matters.
