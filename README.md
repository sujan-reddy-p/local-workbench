# Local Workbench

**A local-first batch-work runner for jobs that are tedious to do file by file.** Give it a goal, choose a workspace, and let an Ollama model analyze supported files into a durable report. The application never deletes or moves originals and has no shell-command or direct cloud API integration. It rejects known Ollama cloud model tags, but the Ollama server can still route cloud models through its local API; use a model you have verified is local if input must stay on-device.

## 0.1.1 release notes

- Known Ollama cloud tags are rejected, and non-regular or oversized inputs cannot enter normal analysis.
- A read-only report preview requires explicit approval before categorized copies; failed files are shown and excluded from copying.
- Regression coverage includes malformed model output, scanner boundaries, resume recovery, and export preservation.
- The CLI now validates workspace paths and `--parallel` (1–4) before starting.
- Direct runs report per-file counts and return exit status 1 when any item needs attention.
- Packaging includes a console entry point and wheel/sdist build instructions.

## What it can help with

- Sort interview notes or customer feedback into themes and produce per-file summaries.
- Triage logs or incident reports into categories such as component, severity, or likely owner.
- Review image sets with a local vision model—for example, classify photos by visible subject or scene.
- Extract short facts from Markdown, text, CSV/TSV, JSON, YAML, HTML, and log files into a reviewable report.
- Make categorized copies of matching inputs into a separate export directory after you approve the action.

This is a batch analyst and safe file-copy tool, not an unrestricted computer-use agent. Each file is analyzed independently; it does not infer a shared answer across a whole corpus. It does not yet parse PDFs, spreadsheets, archives, or execute arbitrary tools. Results can be wrong: check the report before applying copies.

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com/download/linux) running locally
- A local model that supports structured chat output and the file types you want to analyze; the default is `gemma3:4b` (text and images)

On Linux, install Ollama using its official instructions, then download the model once:

```bash
ollama pull gemma3:4b
```

Model downloads use disk space and inference consumes RAM/VRAM. Start with one worker. The concurrency heuristic uses available system memory (a fixed 5 GiB per-request estimate with a 1 GiB reserve) and reduces to one worker at 85% CPU use; it does not inspect GPU memory or model-specific requirements. If resource telemetry is unavailable, it falls back to one worker. The configured cap is 1–4 requests (CLI default: 2), not a performance guarantee.

## Install and run

For a user install from this checkout (non-editable):

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install .
local-workbench --workspace ~/Documents
```

For a development checkout, include test/build tools and use an editable install:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
local-workbench --workspace ~/Documents
```

To build and install the distributable artifacts:

```bash
python -m build
python -m pip install dist/local_workbench-0.1.1-py3-none-any.whl
```

The TUI accepts a natural-language instruction. Example goals:

- `Tag each feedback note by its main complaint and summarize the evidence.`
- `Sort these screenshots into product area categories and note what each shows.`
- `Identify the log files that mention database timeouts; summarize the relevant evidence.`
- `Extract vendor, invoice date, and total from each receipt image.`

The TUI writes a Markdown report to `~/.local/share/local-workbench/reports/`. After a run, choose **Review report / copy files** to inspect the scrollable report, including per-file failures, before approving copies. Hidden, unsupported, oversized, and non-regular files are skipped before processing and do not appear in the report. Approved copies go under `~/.local/share/local-workbench/exports/run-N/`; originals are untouched and existing export files are not overwritten.

Direct CLI use:

```bash
local-workbench --check --model gemma3:4b
local-workbench --workspace ~/Documents --task 'Tag each note by topic and summarize it'
local-workbench --workspace ~/Documents --resume 3
```

`--parallel` accepts only 1–4 (default 2); it is a cap, not a performance guarantee. A successful direct run prints `complete` with completed/total counts and exits 0. A run with one or more failed files prints `needs attention` and exits 1; invalid arguments or workspace paths are concise argparse errors (exit 2). `--check` exits 0 only when Ollama responds and the requested model is installed.

Every run is saved to SQLite under the state directory; interrupted `running` items return to the queue when resumed, and failed items are retried. The state directory (default `~/.local/share/local-workbench`, override with `--state-dir`) contains `jobs.sqlite3`, reports, and exports. SQLite stores the task, absolute workspace path, model, relative file paths, statuses, result suggestions, and errors; it does not intentionally store full source contents. Reports may contain file paths and summaries, and exports contain copies of approved inputs.

## Safety and privacy

- The workspace is selected explicitly; only supported regular text and image files are scanned.
- Hidden directories, Git metadata, dependency folders, symlinks, non-regular files, and files larger than 8 MiB are skipped. Each run scans at most 1,000 supported files. Text is limited to 32,000 characters per file.
- The application sends file contents only to an HTTP Ollama endpoint on loopback, defaulting to `http://127.0.0.1:11434`, and blocks model identifiers ending in `-cloud` or `:cloud`. This does **not** guarantee that inference stays on-device: the Ollama server can route cloud models to Ollama's servers, and a custom model alias may not reveal its backing model. Do not use sensitive data unless you have verified that the selected Ollama model runs locally and cloud inference is disabled.
- The model has no shell, network, write, move, or delete tools. Its output is treated as an untrusted suggestion and validated against a fixed JSON schema.
- The only apply operation copies completed categorized files into a new export tree; it never overwrites existing files or modifies originals.

## Development

```bash
pytest
```

The test suite uses fake model responses and temporary folders; it does not require Ollama or download a model. GitHub Actions runs tests on Python 3.11–3.13.

## License

MIT. See [LICENSE](LICENSE).
