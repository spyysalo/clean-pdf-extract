#!/usr/bin/env python3

import sys
import os
import re
import logging

from argparse import ArgumentParser


# Defaults for command-line arguments
DEFAULT_MIN_LENGTH = 5
DEFAULT_MAX_GAP = 3
DEFAULT_TAG = 'cleanpdfextract:tableofcontents'

# Generic regular expressions TOC-related lines
TOC_LINE_RE = re.compile(r'(\.\s*){5,}(\d+)\s*$')
BLANK_LINE_RE = re.compile(r'^\s*$')
SHORT_LINE_RE = re.compile(r'^.{,10}$')
LOOSE_TOC_LINE_RE_1 = re.compile(r'^.*\.\s*\d+\s*$')
LOOSE_TOC_LINE_RE_2 = re.compile(r'^.*(\.\s*){5}.*$')

# Language-specific regular expressions for TOC-related lines
TOC_HEADER_RE = {
    'fi': re.compile(r'^\s*(?:\d+\.?\s*)?(sisällys(?:luettelo)?|sisältö)\s*$', re.I)
}

logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--min-length',
        type=int,
        default=DEFAULT_MIN_LENGTH,
        help='minimum TOC length in lines'
    )
    ap.add_argument(
        '--max-gap',
        type=int,
        default=DEFAULT_MAX_GAP,
        help='maximum gap length between TOC blocks in lines'
    )
    ap.add_argument(
        '--mark',
        default=False,
        action='store_true',
        help='mark TOCs instead of filtering'
    )
    ap.add_argument(
        '--tag',
        default=DEFAULT_TAG,
        help='tag to use with --mark'
    )
    ap.add_argument(
        '--debug',
        default=False,
        action='store_true',
        help='print debug info'
    )
    ap.add_argument(
        'text',
        nargs='+',
        help='text file(s) extracted from PDF'
    )
    return ap


def categorize_toc_lines(lines, args):
    categorized = []
    for line in lines:
        if TOC_LINE_RE.search(line):
            categorized.append((True, line))
        else:
            categorized.append((False, line))
    return categorized


def non_toc_line_between_toc_lines(categorized, index):
    def is_toc_line(index):
        if index < 0 or index > len(categorized):
            return False
        else:
            return categorized[index][0]
    return (
        is_toc_line(index-1) and
        is_toc_line(index+1) and
        not is_toc_line(index)
    )


def optional_between_lines_before_toc(categorized, index):
    regexes = [
        BLANK_LINE_RE,
        SHORT_LINE_RE,
        LOOSE_TOC_LINE_RE_1,
        LOOSE_TOC_LINE_RE_2,
    ]
    while index < len(categorized):
        if categorized[index][0] == True:
            return True
        elif not any(r.match(categorized[index][1]) for r in regexes):
            return False    # not OK as in-between line
        index += 1
    return False


def recategorize_preceding_lines(categorized, args):
    """Categorize lines matching REs preceding TOC lines as TOC lines."""
    regexes = list(TOC_HEADER_RE.values())
    recategorized = []
    in_block = False
    for i, (category, line) in enumerate(categorized):
        if ((in_block or any(r.match(line) for r in regexes)) and
            optional_between_lines_before_toc(categorized, i+1)):
            in_block = True
        else:
            in_block = False
        if in_block:
            category = True
        recategorized.append((category, line))
    return recategorized


def recategorize_in_between_lines(categorized, args):
    """Categorize lines matching REs between TOC lines as TOC lines."""
    recategorized = []
    in_block = False
    for i, (category, line) in enumerate(categorized):
        if category == True:
            in_block = True
        elif in_block and optional_between_lines_before_toc(categorized, i):
            category = True    # recategorize
        else:
            in_block = False
        recategorized.append((category, line))
    return recategorized


def smooth_categories(categorized, args, width=1):
    recategorized = []
    for i, (category, line) in enumerate(categorized):
        cats = [
            categorized[j][0]
            for j in range(max(0, i-width), min(len(categorized), i+width+1))
        ]
        ratio = sum(1 for c in cats if c == True)/len(cats)
        if ratio > 0.5:
            category = True
        recategorized.append((category, line))
    return recategorized


def group_toc_lines(categorized, args):
    blocks, block_start = [], None
    for i, (category, line) in enumerate(categorized):
        if category == True:
            # TOC line
            if block_start is None:
                block_start = i    # first in block
            else:
                pass    # block continues
        else:
            # non-TOC line
            if block_start is not None:
                blocks.append((block_start, i))
            block_start = None
    if block_start is not None:
        blocks.append((block_start, i))
    return blocks


def combine_blocks(blocks, args):
    # Repeatedly combine consecutive (start, end) blocks that are no
    # more than args.max_gap apart where at least one is at least
    # args.min_length long.

    def acceptable_block(b):
        return b[1]-b[0] >= args.min_length

    def acceptable_gap(b1, b2):
        assert b1[0] < b2[0]
        return b2[0]-b1[1] <= args.max_gap

    def can_combine(b1, b2):
        return (
            acceptable_gap(blocks[i], blocks[i+1]) and
            (acceptable_block(blocks[i]) or acceptable_block(blocks[i+1]))
        )

    for i in range(len(blocks)-1):
        if can_combine(blocks[i], blocks[i+1]):
            combined = (blocks[i][0], blocks[i+1][1])
            new_blocks = blocks[:i] + [combined] + blocks[i+2:]
            return combine_blocks(new_blocks, args)

    return blocks    # nothing to combine


def filter_blocks(blocks, args):
    return [b for b in blocks if b[1]-b[0] >= args.min_length]


def write_output(lines, blocks, args):
    toc_start_lines = { b for b, e in blocks }
    toc_end_lines = { e-1 for b, e in blocks }
    in_toc = False
    for i, line in enumerate(lines):
        if i in toc_start_lines:
            if args.mark:
                print(f'<{args.tag}>')
            else:
                print()    # replace with blank
            in_toc = True
        if args.mark or not in_toc:
            print(line)
        if i in toc_end_lines:
            if args.mark:
                print(f'</{args.tag}>')
            in_toc = False


def process_tocs(fn, args):
    with open(fn) as f:
        text = f.read()

    lines = text.splitlines()

    categorized = categorize_toc_lines(lines, args)
    categorized = recategorize_preceding_lines(categorized, args)
    categorized = recategorize_in_between_lines(categorized, args)
    categorized = smooth_categories(categorized, args)

    blocks = group_toc_lines(categorized, args)
    blocks = combine_blocks(blocks, args)
    blocks = filter_blocks(blocks, args)

    write_output(lines, blocks, args)


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    for fn in args.text:
        process_tocs(fn, args)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
