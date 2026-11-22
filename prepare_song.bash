#!/bin/bash

SOURCE="$(basename "$1")"
SOURCE="$1"
NAME="$(basename "$1")"
NAME="${NAME/.rg/}"
WORK="/output/tests/$NAME"
FULL="$WORK/full"

export SOURCE
export WORK
export FULL
