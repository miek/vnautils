#!/usr/bin/env python

import argparse
import matplotlib
import matplotlib.pyplot as plt
import pathlib
from skrf import Network
import sys

def main():
    parser = argparse.ArgumentParser(
        prog = 'plot_touchstone',
        description = 'Plot touchstone files',
    )

    parser.add_argument('filename', nargs='*')
    parser.add_argument('-t', '--type', choices=['smith', 'mag', 'phase'], default='smith')
    parser.add_argument('-o', '--output', type=pathlib.Path)
    parser.add_argument('-n', type=int)
    parser.add_argument('-m', type=int)

    args = parser.parse_args()

    fig = plt.figure(figsize=(20,10))
    #matplotlib.rcParams.update({'font.size': 22})
    plt.grid(True)

    for f in args.filename:
        n = Network(file=f, f_unit='ghz')
        if args.type == 'smith':
            n.plot_s_smith(marker='.', n=args.n, m=args.m)
        elif args.type == 'mag':
            n.plot_s_db(n=args.n, m=args.m)
        elif args.type == 'phase':
            n.plot_s_deg(n=args.n, m=args.m)
        else:
            print("Unknown plot type {args.type}")
            sys.exit(1)

    if args.output is None:
        plt.show()
    else:
        plt.savefig(args.output)

if __name__ == "__main__":
    main()