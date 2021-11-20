#!/usr/bin/env python3

import sys
import os
import re
import logging

from statistics import median
from collections import defaultdict
from itertools import tee
from argparse import ArgumentParser


# Defaults for command-line arguments
DEFAULT_MAX_GAP = 10

# Regular expressions for matching page numbers
NUMBER_ONLY_RE = re.compile(r'^\s*(\d+)\s*$')
DASHED_NUMBER_RE = re.compile(r'^\s*-+\s*(\d+)\s*-+\s*$')


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--max-gap',
        type=int,
        default=DEFAULT_MAX_GAP,
        help='maximum gap in page number sequence'
    )
    ap.add_argument(
        '--mark',
        default=False,
        action='store_true',
        help='mark page numbers instead of filtering'
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


class Candidate:
    """Represents potential page number."""
    def __init__(self, number, line, line_index, span=None):
        self.number = number
        self.line = line
        self.line_index = line_index
        self.span = span

    def marked_line(self, tag='pagenumber'):
        if self.span is None:
            return f'<{tag}>{self.line}</{tag}>'    # mark whole line
        else:
            pre = self.line[:self.span[0]]
            tagged = self.line[self.span[0]:self.span[1]]
            post = self.line[self.span[1]:]
            return f'{pre}<{tag}>{tagged}</{tag}>{post}'

    def line_without_page_number(self):
        if self.span is None:
            return None
        else:
            pre = self.line[:self.span[0]]
            post = self.line[self.span[1]:]
            return f'{pre}{post}'

    def __str__(self):
        return f'{self.number} {self.line_index}:{self.span} "{self.line}"'

    def __lt__(self, other):
        return self.number < other.number


def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def longest_increasing_subsequence(seq):
    # O(n log n) implementation following
    # https://en.wikipedia.org/wiki/Longest_increasing_subsequence
    min_idx = [0] * (len(seq)+1)
    pred = [0] * len(seq)
    max_len = 0
    for i in range(0, len(seq)):
        # Binary search for the largest positive j <= max_len such
        # that seq[min_idx[j]] < seq[i]
        lo = 1
        hi = max_len + 1
        while lo < hi:
            mid = lo + int((hi-lo)/2)
            if seq[min_idx[mid]] < seq[i]:
                lo = mid + 1
            else:
                hi = mid

        # lo is 1 greater than the length of the longest prefix of seq[i]
        new_len = lo

        # predecessor of seq[i] is the last index of the subsequence
        # of length new_len-1
        pred[i] = min_idx[new_len-1]
        min_idx[new_len] = i

        if new_len > max_len:
            # found subsequence longer than any found yet
            max_len = new_len

    # reconstruct
    lis = [0] * max_len
    k = min_idx[max_len]
    for i in reversed(range(0, max_len)):
        lis[i] = seq[k]
        k = pred[k]

    return lis


def page_number_candidates(lines):
    candidates = []
    for i, line in enumerate(lines):
        for regex in [NUMBER_ONLY_RE, DASHED_NUMBER_RE]:
            m = regex.match(line)
            if m:
                number = int(m.group(1))
                candidates.append(Candidate(number, line, i))
                break
    return candidates


def _subsequences(prev, seq, candidate_map):
    if not seq:
        yield []
    else:
        first, rest = seq[0], seq[1:]
        for c in candidate_map[first]:
            if prev is None or c.line_index > prev.line_index:
                for s in _subsequences(c, rest, candidate_map):
                    yield [c] + s


def candidate_sequences(sequence, candidates):
    # TODO this risks a combinatorial explosion
    candidates_by_number = defaultdict(list)
    for c in candidates:
        candidates_by_number[c.number].append(c)
    return list(_subsequences(None, sequence, candidates_by_number))


def avg_page_len(prev, curr):
    assert prev.number < curr.number
    page_diff = curr.number - prev.number
    line_diff = curr.line_index - prev.line_index
    return line_diff/page_diff


def estimate_page_length(sequences):
    # estimate page length in lines based on sequences of Candidates
    estimates = []
    for sequence in sequences:
        lengths = []
        for prev, curr in pairwise(sequence):
            lengths.append(avg_page_len(prev, curr))
        estimates.append(median(lengths))
    return median(estimates)


def plausible_page_number_pair(prev, curr, page_length, args):
    if curr.number > prev.number + args.max_gap:
        return False
    elif 20 * avg_page_len(prev, curr) < page_length:
        return False    # much too short a page
    else:
        return True


def trim_sequence(sequence, page_length, args):
    if len(sequence) < 2:
        return sequence
    for i, (prev, curr) in enumerate(pairwise(sequence), start=1):
        if not plausible_page_number_pair(prev, curr, page_length, args):
            start = sequence[:i]
            end = trim_sequence(sequence[i:], page_length, args)
            longer = start if len(start) > len(end) else end
            return longer
    return sequence


def select_best_sequence(sequences, page_length):
    scored = []
    for sequence in sequences:
        score = 0
        # longer and more uniform page len is better
        for prev, curr in pairwise(sequence):
            length = avg_page_len(prev, curr)
            ratio = length / page_length
            score += ratio if ratio < 1.0 else 1.0/ratio
        scored.append((score, sequence))
    scored.sort(reverse=True)
    return scored[0][1]


def line_has_page_number(line, number):
    m = re.search(r'^\s*(?:-+\s*)?('+str(number)+r')', line)
    if m:
        logger.debug(f'line_has_page_number: {number} on {line}')
        return m
    return None


def find_page_number(number, start_line, min_line, max_line, lines):
    distance = 0
    while start_line-distance >= min_line or start_line+distance <= max_line:
        match, line = None, None
        if start_line-distance >= min_line:
            index = start_line-distance
            match = line_has_page_number(lines[index], number)
        if match is None and start_line+distance <= max_line:
            index = start_line+distance
            match = line_has_page_number(lines[index], number)
        if match is not None:
            return Candidate(number, lines[index], index, match.span())
        distance += 1
    return None


def repair_sequence(sequence, lines, page_length, args):
    if len(sequence) < 2:
        return sequence    # nothing to repair
    repaired = []
    for prev, curr in pairwise(sequence):
        repaired.append(prev)
        missing = list(range(prev.number+1, curr.number))
        if len(missing) > args.max_gap:
            logger.warning(f'not attempting to repair {missing}')
            continue
        for number in missing:
            diff = number - prev.number
            start_line = prev.line_index + diff * page_length
            min_line = max(prev.line_index+1, start_line-page_length)
            max_line = min(curr.line_index-1, start_line+page_length)
            new_candidate = find_page_number(
                number,
                int(start_line),
                int(min_line),
                int(max_line),
                lines
            )
            if new_candidate is not None:
                repaired.append(new_candidate)
    repaired.append(curr)
    return repaired


def make_page_number_sequence(candidates, args):
    lis = longest_increasing_subsequence([c.number for c in candidates])

    # filter out candidates with numbers not on the LIS
    lis_numbers = set(lis)
    candidates = [c for c in candidates if c.number in lis_numbers]

    sequences = candidate_sequences(lis, candidates)
    if len(sequences) > 100:
        logger.warning(f'{len(sequences)} candidate page num sequences in {fn}')

    page_length = estimate_page_length(sequences)
    logger.debug(f'estimated page length: {page_length}')

    sequences = [trim_sequence(s, page_length, args) for s in sequences]

    sequence = select_best_sequence(sequences, page_length)
    return sequence, page_length


def process_page_numbers(fn, args):
    with open(fn) as f:
        text = f.read()

    lines = text.splitlines()

    candidates = page_number_candidates(lines)

    sequence, page_length = make_page_number_sequence(candidates, args)

    # find new candidates with a looser matching criterion
    repaired = repair_sequence(sequence, lines, page_length, args)
    sequence, page_length = make_page_number_sequence(repaired, args)

    candidate_by_line_index = { c.line_index: c for c in sequence }
    for i, line in enumerate(lines):
        c = candidate_by_line_index.get(i)
        if c:
            if args.mark:
                print(c.marked_line())
            elif c.line_without_page_number():
                print(c.line_without_page_number())
            else:
                pass    # only page number on line
        else:
            print(line)


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    for fn in args.text:
        process_page_numbers(fn, args)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
