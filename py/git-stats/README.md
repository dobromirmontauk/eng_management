# Git Stats Tool

A Python tool for analyzing Git repositories and generating statistics about commits and lines of code by week and contributor.

## Features

- **Multi-repository support**: Analyze multiple Git repositories at once
- **Glob pattern support**: Use filesystem glob patterns to discover repositories
- **Weekly aggregation**: Group statistics by week and contributor
- **Multiple output formats**: Export to JSON, CSV, or view summary in terminal
- **Comprehensive statistics**: Track commits, lines added, and lines deleted

## Installation

No external Python dependencies are required. The tool uses only Python standard library modules.

**Prerequisites:**
- Python 3.6 or higher
- Git installed on your system

## Usage

### Command Line Interface

```bash
# Basic usage - analyze a single repository
python3 py/git-stats/cli.py /path/to/repository

# Analyze multiple repositories using glob patterns
python3 py/git-stats/cli.py /path/to/repos/*

# Export results to JSON and CSV
python3 py/git-stats/cli.py /path/to/repo --json results.json --csv results.csv

# Show summary statistics
python3 py/git-stats/cli.py /path/to/repo --summary

# Limit analysis to recent commits
python3 py/git-stats/cli.py /path/to/repo --since "1 year ago" --summary
```

### Programmatic Usage

```python
from git_stats import GitAnalyzer

# Create analyzer with repository paths
analyzer = GitAnalyzer(['/path/to/repo1', '/path/to/repo2'])

# Analyze repositories
analyzer.analyze_repositories()

# Get weekly statistics
weekly_stats = analyzer.get_weekly_stats()

# Export results
analyzer.export_to_json('results.json')
analyzer.export_to_csv('results.csv')

# Print summary
analyzer.print_summary()
```

## Output Formats

### JSON Format
```json
[
  {
    "week_start": "2024-01-01",
    "contributor": "John Doe",
    "commits": 5,
    "lines_added": 150,
    "lines_deleted": 25
  }
]
```

### CSV Format
```csv
Week Start,Contributor,Commits,Lines Added,Lines Deleted
2024-01-01,John Doe,5,150,25
```

### Summary Output
The tool provides a comprehensive summary including:
- Total commits, lines added, and lines deleted
- Top contributors by commits
- Weekly breakdown of activity

## Repository Discovery

The tool supports glob patterns for discovering repositories:

```bash
# Analyze all repositories in a directory
python -m git_stats.cli /path/to/repos/*

# Analyze repositories matching a pattern
python -m git_stats.cli /path/to/*-project

# Mix of specific paths and patterns
python -m git_stats.cli /specific/repo /path/to/repos/*
```

## Statistics Collected

For each commit, the tool collects:
- **Author**: Git commit author
- **Date**: Commit date
- **Commit Hash**: Unique commit identifier
- **Lines Added**: Number of lines added in the commit
- **Lines Deleted**: Number of lines deleted in the commit

Statistics are then aggregated by:
- **Week**: Starting from Monday of each week
- **Contributor**: Git commit author

## Examples

### Analyze a single repository
```bash
python3 py/git-stats/cli.py ~/my-project --summary
```

### Analyze multiple repositories and export results
```bash
python3 py/git-stats/cli.py ~/projects/* --json weekly_stats.json --csv weekly_stats.csv
```

### Analyze repositories with specific pattern
```bash
python3 py/git-stats/cli.py ~/work/*-service --summary
```

### Analyze recent activity only
```bash
python3 py/git-stats/cli.py ~/my-project --since "6 months ago" --summary
```

## Error Handling

The tool handles various error conditions gracefully:
- Non-existent directories are skipped with warnings
- Non-Git directories are skipped with warnings
- Invalid commit data is handled and logged
- Git command failures are reported but don't stop the analysis

## Performance Considerations

- Large repositories with many commits may take time to analyze
- The tool processes commits sequentially for accuracy
- Consider using specific date ranges for very large repositories (future enhancement)

## Future Enhancements

Potential improvements for future versions:
- Date range filtering
- Branch-specific analysis
- File type filtering
- Interactive web dashboard
- Integration with CI/CD pipelines
