#!/usr/bin/env python3
"""
FlatMark lint wrapper: Validate ticket frontmatter, metadata, dependencies and status.
"""
import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import flatmark

if __name__ == "__main__":
    sys.exit(flatmark.lint_main(sys.argv[1:]))
