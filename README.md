# Local Workbench

**A local-first batch-work runner for jobs that are tedious to do file by file.** Give it a goal, choose a workspace, and let a local Ollama model analyze supported files into a durable report. The model suggests categories and summaries; the application queues work, limits concurrent inference, saves results in SQLite, and can make approved categorized copies. It never deletes or moves originals, runs shell commands, or calls a cloud API.

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

Model downloads use disk space and inference consumes RAM/VRAM. Start with one worker; the application adapts concurrency to available memory and CPU load, and never exceeds the configured cap of four requests.

## Install and run

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
local-workbench --workspace ~/Documents
```

The TUI accepts a natural-language instruction. Example goals:

- `Tag each feedback note by its main complaint and summarize the evidence.`
- `Sort these screenshots into product area categories and note what each shows.`
- `Identify the log files that mention database timeouts; summarize the relevant evidence.`
- `Extract vendor, invoice date, and total from each receipt image.`

The TUI shows run progress and writes a Markdown report to `~/.local/share/local-workbench/reports/`. Inputs are read-only. Select **Review and copy categories** only after checking the report; this writes copies under `~/.local/share/local-workbench/exports/run-N/` and leaves the input files untouched.

Direct CLI use:

```bash
local-workbench --check --model gemma3:4b
local-workbench --workspace ~/Documents --task 'Tag each note by topic and summarize it'
local-workbench --workspace ~/Documents --resume 3
```

Use `--parallel 1` to force a single inference request, or `--parallel 2` to permit up to two when memory allows. Every run is saved to SQLite under the state directory, and interrupted `running` items are returned to the queue when resumed. Failed items are retried when you resume that run.

## Safety and privacy

- The workspace is selected explicitly; only supported regular text and image files are scanned.
- Hidden directories, Git metadata, dependency folders, and files larger than 8 MiB are skipped. Each run scans at most 1,000 supported files. Text is limited to 32,000 characters per file.
- File contents are sent only to the configured Ollama host, which defaults to `http://127.0.0.1:11434`. This project does not send data to a cloud provider.
- The model has no shell, network, write, move, or delete tools. Its output is treated as an untrusted suggestion and validated against a fixed JSON schema.
- The only apply operation copies categorized files into a new export tree; it never overwrites existing files or modifies originals.

## Development

```bash
pytest
```

The test suite uses fake model responses and temporary folders; it does not require Ollama or download a model. GitHub Actions runs tests on Python 3.11–3.13.

## License

MIT. See [LICENSE](LICENSE).
