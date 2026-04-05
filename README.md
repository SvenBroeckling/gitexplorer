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

## Features

- File tree showing all tracked files for the selected branch
- Branch selector
- Per-file commit timeline slider
- Three view modes: **Clean** (file as-is), **Inline Diff**, **Side-by-Side Diff**
- Syntax highlighting via Pygments (Monokai theme)
- Fully selectable and copyable source view

## Development

```sh
git clone https://github.com/yourusername/gitexplorer
cd gitexplorer
uv sync
uv run gitexplorer
```

## License

MIT
