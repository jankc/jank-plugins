# jank-plugins

Plugins for Claude Code and Codex by [Jank](https://github.com/Jank). Yes, the
name is a pun — the plugins do their best not to live up to it.

Everything here is self-contained, local-first and company-unaware: no plugin
in this marketplace phones home, requires credentials, or assumes any
particular employer, issue tracker or workflow.

## Install

```
/plugin marketplace add Jank/jank-plugins
/plugin install <plugin>@jank-plugins
```

From a local checkout, `/plugin marketplace add /path/to/jank-plugins` works
the same way.

## Plugins

| Plugin | What it does |
|---|---|
| [`alibi`](plugins/alibi/) | Passive work-log capture and daily reconciliation — records which repo, branch and ticket you worked on and for how long, then turns a messy day into one timesheet-ready entry per project. |

## Layout

```
plugins/<name>/           one self-contained plugin per directory
.claude-plugin/           marketplace.json — Claude Code catalog
.agents/plugins/          marketplace.json — Codex catalog
```

Each plugin carries its own manifests: `.claude-plugin/plugin.json` always,
plus `.codex-plugin/plugin.json` when it supports Codex.

## Adding a plugin

1. Create `plugins/<name>/` with at least `.claude-plugin/plugin.json`.
2. Add an entry to **both** catalogs above — a plugin missing from one of them
   silently doesn't exist for that client.
3. On every release, bump the version in **both** plugin manifests, or
   `/plugin marketplace update` is a no-op for existing users.
