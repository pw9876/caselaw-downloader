# caselaw-downloader

Downloads UK tax tribunal case law from [The National Archives Find Case Law](https://caselaw.nationalarchives.gov.uk) service.

Targets the **Upper Tribunal (Tax and Chancery Chamber)** and **First-tier Tribunal (Tax Chamber)** by default (~1,700 cases), using the public Atom XML API. No API key required.

## Installation

### RHEL 8

RHEL 8 ships with Python 3.6. Install Python 3.12 via pyenv first:

```bash
# Install build dependencies
sudo dnf install -y gcc zlib-devel bzip2 bzip2-devel readline-devel \
    sqlite sqlite-devel openssl-devel tk-devel libffi-devel xz-devel git

# Install pyenv
curl https://pyenv.run | bash

# Add pyenv to your shell
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc

# Install Python 3.12
pyenv install 3.12
```

Then clone and install:

```bash
git clone https://github.com/pw9876/caselaw-downloader.git
cd caselaw-downloader
pyenv local 3.12
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### macOS / Linux (Python 3.12+ already installed)

```bash
git clone https://github.com/pw9876/caselaw-downloader.git
cd caselaw-downloader
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Usage

```bash
# Count matching cases
caselaw-downloader --count

# Download all cases as XML (default)
caselaw-downloader

# Download first 10 cases
caselaw-downloader --limit 10

# Download XML and PDF
caselaw-downloader --format xml --format pdf

# Specific court only
caselaw-downloader --court ukftt/tc

# Custom output directory
caselaw-downloader --output ./my-cases
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | `./cases` | Directory to save downloaded files |
| `--format`, `-f` | `xml` | Format(s) to download: `xml`, `html`, `pdf` |
| `--court`, `-c` | `ukut/tcc`, `ukftt/tc` | Court code(s) to filter by |
| `--limit`, `-n` | *(all)* | Maximum number of cases to download |
| `--count` | — | Print total matching cases and exit |

## Output Structure

Files are saved under the output directory mirroring the case path:

```
cases/
  ukftt/tc/2026/613/
    case.xml
    case.pdf
  ukut/tcc/2024/100/
    case.xml
```

## Rate Limiting

The public API allows 1,000 requests per 5-minute window. The downloader stays safely under this limit (~194 req/min). Downloading all ~1,700 cases takes approximately 20–30 minutes.

## Licence

Case law data is published under the [Open Justice Licence](https://caselaw.nationalarchives.gov.uk/open-justice-licence).
