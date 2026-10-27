# PandaMap project guide

## Settings search

Follow `C:\Games\Wow-Octo\#Addons-dev\.claude-shared\octowow-runtime.md`,
"Settings pages and search (Panda suite)".

## Changelog and releases

- Do not commit, push, tag or publish unless explicitly asked. Never add AI
  credit.
- Every player-visible addon change adds one concise line under
  `CHANGELOG.md`'s `[Unreleased]` section in the same task. Use `Added`,
  `Changed`, `Fixed`, `Removed` or `Security`; describe only what changes for
  the player, keep it to one line and merge overlapping notes. Do not list
  internal refactors, tests, documentation or tooling.
- Never edit release version numbers by hand. When the user asks to publish,
  run `python -B tools/release.py prepare` (`--minor` or `--major` only when
  requested), review and commit its changes, then create and push the matching
  `v*` tag. The GitHub workflow validates the changelog and uses that version's
  entry as the release notes. The first release keeps the current version.

## Discord release message

When the user asks for the Discord message of a release, give it in one code
block, ready to copy, in this structure: version line, `-----------` divider,
`**Added**` / `**Changed**` / `**Fixed**` sections (only those present) with
`- ` bullets copied from that version's `CHANGELOG.md` entry, then
`**Download:** https://github.com/Tom75VN/PandaMap/releases/download/v<VERSION>/PandaMap.zip`
(the latest published release) and a final `@everyone` line.

## Response style (STRICT, always applies)

The user wants VERY SHORT answers. No exceptions.

- Bullet points only. Never write a paragraph.
- One short line per bullet (about 12 words max).
- Only the most important information. Cut everything else.
- First bullet: the result (fixed / not fixed / what was found).
- Then only if relevant: what the user must do, remaining uncertainty.
- Changed files and validation: one bullet each, no detail.
- No background, no reasoning, no restating the question.
- Commands the user must run go in their own code block.
- If the user asks for detail, give it; otherwise stay short.
