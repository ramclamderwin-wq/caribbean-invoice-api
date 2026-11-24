# Quillvora invoice benchmark

This folder contains the CSV manifest template for a labelled extraction benchmark.
The runner is in `scripts/benchmark_invoices.py`.

## What you need

- A running Quillvora API with a test API key.
- Permission to use each invoice in the test.
- A ground-truth value for each field, checked against the original invoice.
- Python 3.10+ and the `requests` package.

Keep invoice files and completed manifests out of GitHub. They may contain confidential
supplier, customer, banking, tax, or payment information. Use redacted copies where
possible and store them locally in a private folder.

## Prepare the files

1. Make a private local folder for the benchmark.
2. Put the invoice PDFs or images in it, preserving their filenames.
3. Copy `benchmarks/benchmark_manifest.template.csv` into that private folder as
   `benchmark_manifest.csv`.
4. Add one row per invoice. The `file` column is relative to the manifest file.
5. Enter the correct values from the original invoice. Use ISO dates (`YYYY-MM-DD`) where possible; common named-month and unambiguous numeric dates are also normalized. Ambiguous numeric dates are not guessed. Use decimal amounts (for example `108.25`). Leave a cell blank
   only when the field is genuinely absent or cannot be established.

The labelled fields are supplier name, invoice number, invoice date, currency,
subtotal, tax, and total.

## Run the benchmark

The benchmark runner uses the `requests` dependency already declared in `requirements.txt`. If you installed the API dependencies, no extra package is needed.

Set the API address and test key in your shell rather than writing secrets into a file:

```bash
export QUILLVORA_BASE_URL="https://YOUR-STAGING-API"
export QUILLVORA_API_KEY="YOUR_TEST_API_KEY"
python scripts/benchmark_invoices.py \
  --manifest /private/path/benchmark_manifest.csv \
  --output /private/path/benchmark_results.json
```

The script uploads each invoice to `POST /v1/extract-file`, compares the returned
`fields` with the labelled values, and reports exact-match accuracy for each field.
It also records request errors, processing time, warnings, and the review-required flag.

## Interpreting results

- Accuracy is calculated only over nonblank labelled cells for that field.
- Blank ground-truth cells are excluded, not counted as correct.
- This first version uses exact-match comparisons after conservative normalization.
- A small public sample is useful for finding bugs, but it is not representative proof
  of commercial accuracy.
- Report results by language, country, document type, scan quality, and layout once
  enough labelled invoices exist.
- Never make accuracy claims from synthetic or unpermissioned documents.

Do not run this against a production customer account or upload private invoices to an
unapproved service. Use a staging environment and test credentials.
