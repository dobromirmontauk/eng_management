"""
Git Stats - Git Repository Analysis Tool

This package provides tools for analyzing Git repositories and generating
statistics about commits and lines of code by week and contributor.
"""

from .git_analyzer import GitAnalyzer, CommitStats

__version__ = "1.0.0"
__all__ = ['GitAnalyzer', 'CommitStats']
