#! /usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
import sys


def main():
    """
    usage: python ksfs.py -h
    """
    import argparse

    parser = argparse.ArgumentParser(description='compute ksfs from snps.kmer '
                                                 'files')
    parser.add_argument('snps_files', type=str, nargs='+',
                        help='snps.kmer files')

    args = parser.parse_args()

    for i, snps_file in enumerate(args.snps_files):
        snps = pd.read_csv(snps_file, sep='\t', index_col=0)
        n = snps.n.iloc[0]
        assert all(snps.n == n)
        this_ksfs = snps.groupby(['sample frequency',
                                  'mutation type']).size().unstack('mutation type',
                                                                   fill_value=0)
        if i == 0:
            ksfs = this_ksfs
        else:
            ksfs += this_ksfs
        assert this_ksfs.shape[0] == n - 1

    ksfs.to_csv(sys.stdout, sep='\t')


if __name__ == '__main__':
    main()