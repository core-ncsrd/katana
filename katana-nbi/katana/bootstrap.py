import argparse
import json
import sys

from katana.shared_utils.bootstrapUtils import (
    BootstrapError,
    load_manifest_file,
    reconcile_manifest,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reconcile Katana Time-0 infrastructure")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        result = reconcile_manifest(load_manifest_file(args.manifest))
    except BootstrapError as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "results": exc.results}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
