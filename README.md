# CleanMail - Email Cleaner

CleanMail is a clean, local-first email helper that runs on your computer. It reads your Gmail backup (.mbox file), shows you who emails you the most, groups newsletters and promotional ads, and lets you create rules to block junk mail in Gmail.

## Features

- **Upload any .mbox file**: Drag and drop your Gmail backup file from any browser on Mac, Windows, or Linux.
- **Live upload progress**: Real-time progress bar showing percentage and megabytes uploaded.
- **Zero memory blowup**: Reads through multi-gigabyte email files smoothly.
- **Smart email detection**: Automatically finds newsletters, ads, and receipts so you do not accidentally block important invoices.
- **AI reviews**: Optional Gemini connection to review mixed senders and recommend safe Gmail search rules.
- **One-click filter download**: Generates search queries and an importable XML filter file for Gmail.
- **Classic Apple System UI**: Retro Mac OS styling using system.css.

## Getting Started

1. Start CleanMail:
```bash
./run.sh
```

During first setup, CleanMail will ask in the terminal for an optional Gemini API key. You can press Enter to skip if you prefer basic offline rules.

2. Open in your browser:
Navigate to:
```
http://127.0.0.1:8000
```

3. Clean your Gmail:
- Click **Choose .mbox File** or drag and drop your Gmail backup into the window.
- Watch the live upload progress and email reading counter.
- Browse your senders, click **Newsletters and Ads**, and click **Create Gmail Filter** to export rules.
