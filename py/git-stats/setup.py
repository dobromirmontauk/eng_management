#!/usr/bin/env python3
"""
Setup script for git-stats package.
"""

from setuptools import setup, find_packages

setup(
    name="git-stats",
    version="1.0.0",
    description="Git repository statistics analysis tool with interactive dashboard",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "pandas>=1.3.0",
        "streamlit>=1.28.0",
        "plotly>=5.15.0",
    ],
    entry_points={
        "console_scripts": [
            "git-stats=git_stats.cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
