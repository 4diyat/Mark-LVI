"""Run a real Qt smoke test and expose failures as CI annotations.

The raw Actions log can be unavailable even when the job has completed. Keep
its diagnostic tail in a check annotation, including failures in Qt callbacks.
"""
import subprocess
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Expected one smoke-test script')
    result = subprocess.run([sys.executable, sys.argv[1]], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=240)
    output = result.stdout.decode('utf-8', errors='replace')
    print(output, end='', flush=True)
    if result.returncode:
        tail = output[-10000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error title=Qt smoke test failed::{sys.argv[1]} exited {result.returncode}%0A{tail}', flush=True)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
