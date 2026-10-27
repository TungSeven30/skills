---
name: add-skill
description: Use when adding a new skill or a new category to Tung's skills repo (TungSeven30/skills) so it ships through the seven30-skills plugin marketplace.
---

# Add a skill to this repo

Each category in this repo is its own plugin under `plugins/<category>/`, listed in `.claude-plugin/marketplace.json`. The categories are `core` (general-purpose skills, including this one), `coding`, `design` and `filmmaking`.

## Add a skill to an existing category

1. Pick the category whose purpose fits the skill. Use `core` only for skills that don't belong to any one field.
2. Create `plugins/<category>/skills/<skill-name>/SKILL.md`. The folder name is the skill name: lowercase letters, digits and hyphens.
3. Start the file with frontmatter holding `name` (same as the folder) and a one-line `description` that says when to use the skill. The description decides when the skill fires, so make it specific. Keep to the Agent Skills fields (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`) if the skill should also work outside Claude Code.
4. Put scripts, references, templates and assets inside the skill's own folder and point to them by relative path, or by `${CLAUDE_SKILL_DIR}/...` in commands Claude runs. Never use absolute paths from your machine, and never reach into another skill's folder.
5. If the category's entry is missing from `.claude-plugin/marketplace.json` (its first skill), add it now. See "Add a new category" step 3.
6. Bump `version` in `plugins/<category>/.claude-plugin/plugin.json` so installed copies pick up the change on update.
7. Run `scripts/validate.sh` from the repo root and fix anything it reports.
8. Commit and push. Users get the skill with `/plugin marketplace update seven30-skills`, and it runs as `/<category>:<skill-name>`.

## Add a new category

1. Create `plugins/<category>/.claude-plugin/plugin.json` with `name` (the category, kebab-case), `description`, `version`, `author` and `repository`, copying an existing category's file as a template.
2. Add the first skill under `plugins/<category>/skills/` as above. Don't register a category that has no skills.
3. Add an entry to the `plugins` array in `.claude-plugin/marketplace.json` with the same `name`, `"source": "./plugins/<category>"` and a `description`. The entry name must match the `name` in `plugin.json`.
4. Add the category to the layout table and install list in `README.md`, then run `scripts/validate.sh`.

## Rules

- One copy of each skill. To move a skill between categories, move its whole folder with `git mv`, bump both plugins' versions, and note the new invocation name in the README.
- Never rename or remove a plugin entry without adding the old name to `renames` in `marketplace.json` (new name, or `null` if removed). Treat `renames` as append-only.
