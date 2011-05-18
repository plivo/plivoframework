# Copyright (c) 2011 Plivo Team. See LICENSE for details.

#!/bin/bash

# profile a python script with cProfile

[ -e $1 ] || {
  echo "$(basename $0) PYTHONSCRIPT"
  exit 1
}

python -m cProfile $1

exit 0
