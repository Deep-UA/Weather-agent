# WeatherAgent

## Layout

- `research/`: notes, API comparisons and design research for the agent. Put research write-ups here as Markdown, not in the project root.

## Skills for this project

Project-scoped (checked in under `.claude/`):
- `skill-creator`: copied to `.claude/skills/skill-creator/`. Use it to write project skills (e.g. calling the weather API).
- `grill-me`: plugin enabled in `.claude/settings.json` from the `claude-code-skills` marketplace.

Built into Claude Code (no setup needed):
- `/claude-api`: Claude API / Agent SDK reference. Read it before writing agent code.
- `/run`: launch the app and check a change works.
- `/code-review`, `/simplify`, `/security-review`: review changes before committing.
- `/init`: regenerate this file once there is code.
