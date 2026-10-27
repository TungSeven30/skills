# skills

a walk-in closet for my agents.

This repo is a Claude Code plugin marketplace. It holds one plugin, `seven30`, which bundles every skill in the collection, so installing the plugin gives an agent the whole closet and new skills arrive on update.

## Install

In Claude Code:

```
/plugin marketplace add TungSeven30/skills
/plugin install seven30@seven30-skills
```

Or in one step on Claude Code 2.1.275 or later:

```
/plugin install seven30 --marketplace TungSeven30/skills
```

Skills run as `/seven30:<skill-name>`. Pull new skills with `/plugin marketplace update seven30-skills`.

## Layout

- `.claude-plugin/marketplace.json` lists the plugins in this marketplace.
- `plugins/seven30/.claude-plugin/plugin.json` is the plugin's manifest.
- `plugins/seven30/skills/<skill-name>/SKILL.md` is one skill per folder.

## Add a skill

Create `plugins/seven30/skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter, bump `version` in `plugin.json`, run `claude plugin validate .`, then commit and push. The bundled `add-skill` skill walks an agent through the same steps.
