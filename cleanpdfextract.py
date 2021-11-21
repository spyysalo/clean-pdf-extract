#!/usr/bin/env python3

import sys
import os
import logging

from argparse import ArgumentParser

from normalizeencoding import normalize_encoding, add_normalize_encoding_args
from filterpagenumbers import filter_page_numbers, add_filter_page_numbers_args
from filtertocs import filter_tocs, add_filter_tocs_args


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


ADD_ARGS_FUNCTIONS = [
    add_normalize_encoding_args,
    add_filter_page_numbers_args,
    add_filter_tocs_args,
]

CLEANING_FUNCTIONS = [
    normalize_encoding,
    filter_page_numbers,
    filter_tocs,
]


def argparser():
    ap = ArgumentParser()

    for add_args_func in ADD_ARGS_FUNCTIONS:
        add_args_func(ap)

    ap.add_argument(
        'text',
        nargs='+',
        help='text file(s) extracted from PDF'
    )
    return ap


def main(argv):
    args = argparser().parse_args(argv[1:])

    logger.setLevel(logging.INFO)

    for fn in args.text:
        with open(fn) as f:
            text = f.read()

        for cleaning_func in CLEANING_FUNCTIONS:
            text = cleaning_func(text, args)

        print(text, end='')


if __name__ == '__main__':
    sys.exit(main(sys.argv))
