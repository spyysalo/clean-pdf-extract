#!/usr/bin/env python3

# Attempts to fix encoding issues in plain text.

import sys
import os
import unicodedata
import logging

from argparse import ArgumentParser

import ftfy


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--no-fix',
        default=False,
        action='store_true',
        help='do not apply ftfy.fix_encoding'
    )
    ap.add_argument(
        '--keep-nonprintable',
        default=False,
        action='store_true',
        help='keep all non-printable characters'
    )
    ap.add_argument(
        '--normalization',
        choices=['NFC', 'NFKC', 'NFD', 'NFKD', 'None'],
        default='NFKC',
        help='unicode normalization to apply',
    )
    ap.add_argument(
        'text',
        nargs='+',
        help='text file(s) extracted from PDF'
    )
    return ap


def remove_nonprintable(string):
    if remove_nonprintable.table is None:
        exceptions = { '\n', '\t', '\u00AD' }
        nonprintable = [
            chr(c) for c in range(sys.maxunicode) if
            not chr(c).isprintable() and chr(c) not in exceptions
        ]
        remove_nonprintable.table = str.maketrans('', '', ''.join(nonprintable))
    return string.translate(remove_nonprintable.table)
remove_nonprintable.table = None


def normalize_encoding(fn, args):
    with open(fn) as f:
        text = f.read()

    if not args.no_fix:
        try:
            text = ftfy.fix_encoding(text)
        except Exception as e:
            logger.error(f'fix_encoding for {fn}: {e}')

    if args.normalization != 'None':
        try:
            text = unicodedata.normalize(args.normalization, text)
        except Exception as e:
            logger.error(f'normalize for {fn}: {e}')

    if not args.keep_nonprintable:
        text = remove_nonprintable(text)

    print(text, end='')


def main(argv):
    args = argparser().parse_args(argv[1:])

    logger.setLevel(logging.INFO)

    for fn in args.text:
        normalize_encoding(fn, args)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
