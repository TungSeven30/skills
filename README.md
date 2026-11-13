# skills

a walk-in closet for my agents.

This repo is a Claude Code plugin marketplace named `seven30-skills`. Each category of skills is its own plugin, so you install only the categories you want.

## Layout

```
.claude-plugin/marketplace.json            the catalog: lists each installable category
plugins/<category>/.claude-plugin/plugin.json
plugins/<category>/skills/<skill-name>/SKILL.md
plugins/<category>/skills/<skill-name>/... scripts, references, templates, assets for that skill
scripts/validate.sh                        checks everything before you push
scripts/sync-upstream.py                   re-pulls skills that track an upstream repo
upstreams/<name>.json, <name>.lock.json    what an upstream sync installs, and the exact commits it installed
```

| Category | Purpose | Skills | Installable |
| :- | :- | :- | :- |
| `core` | General-purpose skills that don't belong to one field, including tools for maintaining this repo | `add-skill` | Yes |
| `coding` | Writing, reviewing, testing and shipping code | none yet | Not yet |
| `design` | Visual, interface and brand design | The [Open Design](https://github.com/nexu-io/open-design/tree/main/skills) catalogue, synced from upstream (see `upstreams/open-design.lock.json` for the list) | Yes |
| `filmmaking` | Video and film production, from script to edit | none yet | Not yet |

A category becomes installable when it has at least one skill and an entry in `marketplace.json`. Until then its folder and `plugin.json` are ready, but the marketplace doesn't list it.

## Install

Add the marketplace once, in a Claude Code session:

```
/plugin marketplace add TungSeven30/skills
```

Then install the categories you want:

```
/plugin install core@seven30-skills
```

On Claude Code 2.1.275 or later you can do both steps at once with `/plugin install core --marketplace TungSeven30/skills`.

`design@seven30-skills` installs the same way; `coding@seven30-skills` and `filmmaking@seven30-skills` will once those categories have skills. From a shell, use `claude plugin marketplace add TungSeven30/skills` and `claude plugin install core@seven30-skills`.

Skills run as `/<category>:<skill-name>`, for example `/core:add-skill`.

## Update

```
/plugin marketplace update seven30-skills
```

An installed plugin picks up changes only when its `version` in `plugin.json` changes, so bump it with every change to a category. You can also turn on auto-update for the marketplace under **Marketplaces** in `/plugin`.

## Add a skill to an existing category

1. Create `plugins/<category>/skills/<skill-name>/SKILL.md` with `name` (same as the folder) and `description` frontmatter.
2. Keep the skill's scripts, references and assets in its own folder and link them by relative path.
3. Bump `version` in `plugins/<category>/.claude-plugin/plugin.json`.
4. If this is the category's first skill, add its entry to `marketplace.json` (see below) and mark it installable in the table above.
5. Run `scripts/validate.sh`, then commit and push.

The `add-skill` skill in `core` walks an agent through the same steps.

## Skills synced from upstream

Some skills are verbatim copies of someone else's skills that we keep current with their repo instead of editing here. Each source has a manifest in `upstreams/`:

- `upstreams/<name>.json` says which catalogue to follow, which plugin it lands in, and any `exclude` entries or `pins` (an explicit repo and `path`, or several `paths`, for entries the script can't resolve on its own).
- `upstreams/<name>.lock.json` is written by the sync: every installed skill with its source repo, path, commit and license, plus every skipped entry and why.

To update, run from the repo root:

```
scripts/sync-upstream.py upstreams/open-design.json --check   # preview what would change
scripts/sync-upstream.py upstreams/open-design.json           # apply it
scripts/validate.sh
```

The sync replaces every folder listed in the previous lock, so skills removed upstream disappear here too, and bumps the plugin's minor version when anything changed. It never touches skills it didn't install. Each installed folder carries the upstream `LICENSE` and an `UPSTREAM.md` with its source and commit. Don't edit these folders by hand, because the next sync overwrites them; to drop one, add it to `exclude`.

For Open Design, entries that are full skills are copied from the Open Design repo. Entries that are only catalogue stubs (a pointer to another repo) are resolved to the original skill in that repo, so you get the real instructions, scripts and references. An entry is skipped when its upstream has no license, a license outside the allow list (MIT, Apache-2.0, BSD, ISC, MPL-2.0, CC0, CC-BY-4.0, Unlicense), or no longer contains the skill; the lock file lists each one.

## Create a new category

1. Copy an existing `plugins/<category>/.claude-plugin/plugin.json` to `plugins/<new-category>/.claude-plugin/plugin.json` and change `name`, `description` and `keywords`.
2. Add its first skill under `plugins/<new-category>/skills/`.
3. Add an entry to `plugins` in `.claude-plugin/marketplace.json` with the same `name`, `"source": "./plugins/<new-category>"` and a `description`.
4. Add a row to the table above, run `scripts/validate.sh`, then commit and push.

Never rename or remove a registered category without recording the old name in `renames` in `marketplace.json`.

## Migrate from `seven30@seven30-skills`

The old all-in-one `seven30` plugin is now the `core` plugin, and `marketplace.json` maps `seven30` to `core` under `renames`. After you run `/plugin marketplace update seven30-skills`, Claude Code moves your `seven30` install over to `core`. If it then reports `Plugin "core" not cached`, run `/plugin install core@seven30-skills` once.

What changed:

- Plugin name: `seven30` is now `core`. Install other categories separately as they fill up.
- Skill invocation: `/seven30:add-skill` is now `/core:add-skill`.
- Install command: `/plugin install seven30@seven30-skills` is now `/plugin install core@seven30-skills`.

## Use these skills in other agents

Each skill folder is a plain [Agent Skills](https://agentskills.io) folder: a `SKILL.md` plus its own files. To use one elsewhere, copy the whole folder, `plugins/<category>/skills/<skill-name>/`, into wherever that agent loads skills from.

Limits:

- The marketplace, `/plugin` commands, `plugin.json` and `marketplace.json` are Claude Code features. Other agents don't install from this marketplace.
- Frontmatter beyond `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools` is a Claude Code extension, and some tools reject it.
- `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_ROOT}`, `/category:skill` names, and instructions that name Claude Code tools, hooks or subagents work only in Claude Code. Check a skill for these before reusing it.
- A skill that runs a bundled script needs that script's interpreter and any tools it calls installed on the machine. `add-skill` needs `git`, `python3` and the `claude` CLI for `scripts/validate.sh`, and only makes sense inside a checkout of this repo.
