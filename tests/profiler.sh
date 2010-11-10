#!/bin/bash

[ -e $1 ] || {
  echo "$(basename $0) PYTHONSCRIPT"
  exit 1
}

python -m cProfile $1

exit 0
