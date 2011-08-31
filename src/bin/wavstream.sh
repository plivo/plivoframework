#!/bin/bash

@PREFIX@/bin/wavdump.py $@ |sox -t wav - -t raw -

