# Local Workbench

Local Workbench is a local-first batch analyst for folders of text files and images. Give it a goal; a local Ollama model classifies and summarizes each supported file independently. Review the report, then explicitly approve any categorized copies.

It is a focused, safe batch tool—not a general-purpose computer-use agent. It has no shell-command, move, or delete tools and does not reason across an entire collection.

## Screenshots

The screens below show the TUI and the read-only report review step. The report uses illustrative sample data.

![Local Workbench ready screen with a sample task](docs/screenshots/workbench-ready.png)

![Report review with an explicit copy approval](docs/screenshots/report-review.png)

## What it does

- Processes supported files as resumable jobs, with results and failures saved in SQLite.
- Uses a bounded number of Ollama requests; its concurrency heuristic considers system memory and CPU pressure, not GPU memory.
- Produces a Markdown report with a category, summary, confidence, and notes for each completed file.
- Lets you review that report before copying categorized files to a separate export folder. Originals are never moved, changed, or overwritten.

Example tasks:

- Group customer feedback notes by complaint and summarize each note.
- Triage incident logs by service or error type, with a short evidence summary.
- Categorize screenshots or photos by visible subject or scene.
- Sort project notes into topics and produce a per-file summary.

### Supported files and limits

Text: Markdown, TXT, CSV/TSV, JSON, YAML, XML, HTML, logs, INI, TOML, and Python source.  
Images: PNG, JPG/JPEG, WebP, and BMP; use a vision-capable model.

Each run scans at most 1,000 files. Files over 8 MiB are skipped; text sent for analysis is capped at 32,000 characters per file. PDFs, spreadsheets, archives, and arbitrary computer actions are not supported.

## Quick start

Requirements: Python 3.11+, [Ollama](https://ollama.com/), and a model that supports structured output (and vision, for images).

```bash
git clone https://github.com/sujan-reddy-p/local-workbench.git
cd local-workbench
python -m venv .venv
. .venv/bin/activate
python -m pip install .
ollama pull gemma3:4b
local-workbench --workspace ~/Documents
```

Ollama must be running locally. The TUI accepts a natural-language task. To run without the TUI:

```bash
local-workbench --workspace ~/Documents \
  --task 'Group feedback notes by issue and summarize each note' \
  --parallel 1
```

Use `--resume RUN_ID` to continue an interrupted run. `local-workbench --check` checks the Ollama connection and model availability.

## Privacy and file safety

- The app connects only to an HTTP Ollama endpoint on loopback (default `127.0.0.1:11434`); it does not call a cloud API directly.
- Known Ollama cloud model tags are rejected. **Loopback alone does not guarantee local inference:** Ollama can route cloud models through its server, and custom model aliases may hide their backing model. For sensitive files, verify the selected model is local and disable Ollama cloud features.
- The model receives no shell, network, or file-write tools. The app treats its output as an untrusted suggestion.
- Source files are read-only. Applying results makes copies only, never overwrites existing exports, and requires explicit approval.
- SQLite stores job metadata and suggestions, not source contents by design. Reports can contain paths and summaries; approved exports contain file copies. Keep the state directory private if that data is sensitive.

Reports and exports are stored under `~/.local/share/local-workbench/` by default. Override this with `--state-dir`.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check local_workbench tests
pytest
python -m build
```

## License

MIT. See [LICENSE](LICENSE).
