---
name: add-skill
description: Use when adding a new skill to Tung's skills repo (TungSeven30/skills) so it ships through the seven30 plugin marketplace.
---

# Add a skill to this repo

Skills in this repo ship as part of the `seven30` plugin, which the `seven30-skills` marketplace lists.

1. Create `plugins/seven30/skills/<skill-name>/SKILL.md`. The folder name is the skill name: lowercase, digits and hyphens.
2. Start the file with frontmatter holding `name` (same as the folder) and a one-line `description` that says when to use the skill. The description is what decides when the skill fires, so make it specific.
3. Put supporting files (scripts, references, templates) next to `SKILL.md` in the same folder and point to them by relative path.
4. Bump `version` in `plugins/seven30/.claude-plugin/plugin.json` so installed copies pick up the change on update.
5. Run `claude plugin validate .` from the repo root and fix anything it reports.
6. Commit and push. Users get the skill with `/plugin marketplace update seven30-skills`, and it runs as `/seven30:<skill-name>`.
