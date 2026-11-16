"""Download official NWDP CSV exports with retries and a resumable partial file."""
import argparse
import csv
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from backend.app.laboratory_wqi import COLUMNS, DATA, normalized


def download(url, ca_bundle=None):
    parsed = urlsplit(url)
    name = parsed.path.rsplit('/', 1)[-1]
    if (parsed.scheme != 'https' or parsed.hostname not in {'nwdp.nwic.gov.in', 'www.nwdp.nwic.gov.in'}
            or not name.lower().endswith('.csv') or not name.replace('_', '').replace('-', '').replace('.', '').isalnum()):
        raise ValueError('Supply a direct HTTPS NWDP CSV download link.')
    directory = DATA / 'cpcb'
    directory.mkdir(exist_ok=True)
    output = directory / name
    if output.exists():
        print(f'Already present: {output.name}')
        return
    partial = output.with_suffix('.part')
    command = ['curl.exe', '--fail', '--silent', '--show-error', '--retry', '3',
               '--retry-delay', '2', '--retry-max-time', '120',
               '--connect-timeout', '10', '--max-time', '60', '--output', str(partial)]
    if ca_bundle is not None:
        command.extend(['--cacert', str(ca_bundle)])
    if partial.exists() and partial.stat().st_size:
        command.extend(['--continue-at', '-'])
    subprocess.run([*command, url], check=True)
    with partial.open(encoding='utf-8-sig', newline='') as stream:
        header = {normalized(field) for field in next(csv.reader(stream), [])}
    if not header.intersection(COLUMNS):
        raise ValueError(f'CSV has no recognized water-quality columns: {name}')
    partial.replace(output)
    print(f'Imported: {output.name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='+')
    parser.add_argument('--ca-bundle', type=Path, help='Trusted PEM bundle supplied by your administrator')
    args = parser.parse_args()
    if args.ca_bundle is not None and not args.ca_bundle.is_file():
        parser.error('--ca-bundle must point to an existing PEM file')
    failed = False
    for link in args.urls:
        try:
            download(link, args.ca_bundle)
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            failed = True
            print(error)
    raise SystemExit(int(failed))
