# Remote Real-Data Smoke Test

This document explains a safe, small-scale smoke-test workflow for running
the `fusi` pipeline using real data that resides on a remote host.

Example remote location (your setup):

```
hfu@slate.local:/Users/hfu/github/fusi/source-store
```

Goals:

- Avoid copying the full dataset (which may be very large).
- Provide a repeatable, conservative fetch step to obtain a small sample.
- Run the split-aggregate flow locally against the sample to validate memory
  usage and end-to-end integration.

Prerequisites on local machine:

- `ssh` access to remote host
- `rsync` available locally
- Sufficient local disk to hold the sample (a few hundred MB)

Recommended steps
-----------------

1. Check remote path exists (non-destructive):

```
./scripts/fetch_remote_sample.py --remote hfu@slate.local:/Users/hfu/github/fusi/source-store --check
```

2. Fetch a small sample of TIFFs (dry-run first):

```
./scripts/fetch_remote_sample.py --remote hfu@slate.local:/Users/hfu/github/fusi/source-store \
    --rsync-sample --pattern "*.tif" --dest tmp/sample --dry-run
```

If the dry-run looks OK, run without `--dry-run` to copy actual files.

3. Prepare a local `source-store` subset that points to `tmp/sample`.

For example, create `source-store/local_sample/` and copy or symlink the TIFFs there. Then generate a `bounds.csv` for that source and run the split-aggregate flow:

```
# make a named source visible to the pipeline
mkdir -p source-store/local_sample
rsync -av tmp/sample/ source-store/local_sample/

# generate bounds.csv for the sample
just bounds local_sample

# run zoom-split aggregate on the sample (small and safe)
just aggregate-split local_sample -o output/local_sample.pmtiles --keep-intermediates
```

Notes and safety
----------------
- The helper script uses `rsync --include=<pattern> --exclude=*` to avoid copying everything.
- Always run the script in `--dry-run` mode initially.
- The pipeline will still produce MBTiles in `output/`; ensure `TMPDIR` is set if you want temporary files on a specific device.

Next steps
----------
- If the smoke test is successful, incrementally increase the area or zoom range.
- Use the `pipelines/memory_monitor.py` output logged by `split_aggregate` to check RSS peaks per zoom-group and adjust split patterns accordingly.
