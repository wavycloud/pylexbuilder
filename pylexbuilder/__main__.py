import os
from argparse import ArgumentParser

import stub_generator

def main():
    parser = ArgumentParser()
    parser.add_argument('-d','--dirpath', help='dirpath', required=True)
    args = parser.parse_args()
    dirpath = args.dirpath


if __name__ == '__main__':
    main()