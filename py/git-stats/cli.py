#!/usr/bin/env python3
"""
Command-line interface for Git Stats tool.
"""

import sys
import os

# Add the parent directory to the path so we can import git_analyzer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from git_analyzer import GitAnalyzer


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m git_stats.cli <repository_paths...> [options]")
        print("\nOptions:")
        print("  --json <file>     Export results to JSON file")
        print("  --csv <file>      Export results to CSV file")
        print("  --summary         Print summary statistics")
        print("  --since <date>    Limit analysis to commits since this date")
        print("\nExamples:")
        print("  python -m git_stats.cli /path/to/repo")
        print("  python -m git_stats.cli /path/to/repos/* --summary")
        print("  python -m git_stats.cli /path/to/repo --since '1 year ago' --summary")
        print("  python -m git_stats.cli /path/to/repo --since '2024-01-01' --json results.json")
        return 1
    
    # Parse arguments
    repositories = []
    json_file = None
    csv_file = None
    show_summary = False
    since_date = None
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--json':
            if i + 1 < len(sys.argv):
                json_file = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --json requires a filename")
                return 1
        elif arg == '--csv':
            if i + 1 < len(sys.argv):
                csv_file = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --csv requires a filename")
                return 1
        elif arg == '--summary':
            show_summary = True
            i += 1
        elif arg == '--since':
            if i + 1 < len(sys.argv):
                since_date = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --since requires a date")
                return 1
        elif arg.startswith('--'):
            print(f"Error: Unknown option {arg}")
            return 1
        else:
            repositories.append(arg)
            i += 1
    
    if not repositories:
        print("Error: No repository paths provided")
        return 1
    
    # Create analyzer
    analyzer = GitAnalyzer(repositories, since_date=since_date)
    
    if not analyzer.repositories:
        print("No valid Git repositories found.")
        return 1
    
    # Analyze repositories
    analyzer.analyze_repositories()
    
    # Export results
    if json_file:
        analyzer.export_to_json(json_file)
    
    if csv_file:
        analyzer.export_to_csv(csv_file)
    
    # Print summary
    if show_summary or (not json_file and not csv_file):
        analyzer.print_summary()
    
    return 0


if __name__ == '__main__':
    exit(main())
