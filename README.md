# GitExplorer

A PyQt6-based Git history explorer. Browse any git repository's file history with syntax-highlighted inline and side-by-side diffs.

## Usage

Run from inside a git repository:

```sh
uvx gitexplorer
```

Or point it at a specific repo:

```sh
uvx gitexplorer /path/to/repo
```

### Run directly from GitHub

No local install needed — run the latest version straight from the repository:

```sh
uvx --from git+https://github.com/SvenBroeckling/gitexplorer gitexplorer
```

Pin to a specific branch, tag, or commit:

```sh
# branch
uvx --from git+https://github.com/SvenBroeckling/gitexplorer@main gitexplorer

# tag
uvx --from git+https://github.com/SvenBroeckling/gitexplorer@v1.0.0 gitexplorer

# commit
uvx --from git+https://github.com/SvenBroeckling/gitexplorer@abc1234 gitexplorer
```

Add `--reinstall` to force uv to re-fetch instead of using its cache:

```sh
uvx --reinstall --from git+https://github.com/SvenBroeckling/gitexplorer gitexplorer
```

## Features

- File tree showing all tracked files for the selected branch
- Branch selector
- Per-file commit timeline slider
- Three view modes: **Clean** (file as-is), **Inline Diff**, **Side-by-Side Diff**
- Syntax highlighting via Pygments (Monokai theme)
- Fully selectable and copyable source view

## Development

```sh
git clone https://github.com/SvenBroeckling/gitexplorer
cd gitexplorer
uv sync
uv run gitexplorer
```

## License

MIT
