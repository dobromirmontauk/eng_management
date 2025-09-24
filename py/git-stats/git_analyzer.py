#!/usr/bin/env python3
"""
Git Repository Analyzer

This module provides functionality to analyze Git repositories and generate
statistics about commits and lines of code by week and contributor.
"""

import os
import subprocess
import glob
from datetime import datetime, timedelta
from collections import defaultdict, namedtuple
from typing import List, Dict, Tuple, Optional
import json
import csv
import pandas as pd


CommitStats = namedtuple('CommitStats', ['author', 'date', 'commit_hash', 'lines_added', 'lines_deleted'])


class GitAnalyzer:
    """Analyzes Git repositories for commit and LoC statistics."""
    
    def __init__(self, repo_paths: List[str], since_date: Optional[str] = None):
        """
        Initialize the Git analyzer.
        
        Args:
            repo_paths: List of repository paths (can include glob patterns)
            since_date: Optional date string to limit analysis (e.g., '2024-01-01', '1 year ago')
        """
        self.repo_paths = repo_paths
        self.since_date = since_date
        self.repositories = self._discover_repositories()
        self.stats = []
        self.df = None
    
    def _discover_repositories(self) -> List[str]:
        """
        Discover Git repositories from the provided paths.
        
        Returns:
            List of valid Git repository paths
        """
        repositories = []
        
        for path_pattern in self.repo_paths:
            # Expand glob patterns
            expanded_paths = glob.glob(path_pattern)
            
            for path in expanded_paths:
                if os.path.isdir(path):
                    # Check if it's a Git repository
                    git_dir = os.path.join(path, '.git')
                    if os.path.exists(git_dir):
                        repositories.append(os.path.abspath(path))
                    else:
                        print(f"Warning: {path} is not a Git repository, skipping...")
                else:
                    print(f"Warning: {path} is not a directory, skipping...")
        
        print(f"Found {len(repositories)} Git repositories:")
        for repo in repositories:
            print(f"  - {repo}")
        
        return repositories
    
    def _run_git_command(self, repo_path: str, command: List[str]) -> str:
        """
        Run a Git command in the specified repository.
        
        Args:
            repo_path: Path to the Git repository
            command: Git command as a list of strings
            
        Returns:
            Command output as string
        """
        try:
            result = subprocess.run(
                ['git'] + command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error running git command in {repo_path}: {e}")
            return ""
        except FileNotFoundError:
            print("Error: Git command not found. Please ensure Git is installed.")
            return ""
    
    def _get_commit_stats(self, repo_path: str) -> List[CommitStats]:
        """
        Get commit statistics for a repository.
        
        Args:
            repo_path: Path to the Git repository
            
        Returns:
            List of CommitStats objects
        """
        # Build git log command with optional since date
        git_cmd = ['log', '--pretty=format:%H|%an|%ad', '--date=iso']
        if self.since_date:
            git_cmd.extend(['--since', self.since_date])
        
        # Get commits with author, date, and hash
        commit_log = self._run_git_command(repo_path, git_cmd)
        
        if not commit_log:
            return []
        
        commit_stats = []
        
        for line in commit_log.split('\n'):
            if not line.strip():
                continue
                
            parts = line.split('|')
            if len(parts) >= 3:
                commit_hash = parts[0]
                author = parts[1]
                date_str = parts[2]
                
                # Parse date
                try:
                    # Handle different date formats with timezone info
                    if '+' in date_str or date_str.count('-') > 2:
                        # Date with timezone offset (e.g., "2017-04-25 15:38:25 -0700")
                        # Remove timezone info and parse
                        date_parts = date_str.split(' ')
                        if len(date_parts) >= 3:
                            date_time_part = ' '.join(date_parts[:2])  # "2017-04-25 15:38:25"
                            commit_date = datetime.strptime(date_time_part, '%Y-%m-%d %H:%M:%S')
                        else:
                            commit_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        # Standard date format
                        commit_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    print(f"Warning: Could not parse date '{date_str}' for commit {commit_hash}")
                    continue
                
                # Get lines added/deleted for this commit
                lines_added, lines_deleted = self._get_commit_lines(repo_path, commit_hash)
                
                commit_stats.append(CommitStats(
                    author=author,
                    date=commit_date,
                    commit_hash=commit_hash,
                    lines_added=lines_added,
                    lines_deleted=lines_deleted
                ))
        
        return commit_stats
    
    def _get_commit_lines(self, repo_path: str, commit_hash: str) -> Tuple[int, int]:
        """
        Get lines added and deleted for a specific commit.
        
        Args:
            repo_path: Path to the Git repository
            commit_hash: Commit hash
            
        Returns:
            Tuple of (lines_added, lines_deleted)
        """
        # Get diff stats for the commit
        diff_stats = self._run_git_command(
            repo_path,
            ['show', '--stat', '--format=', commit_hash]
        )
        
        lines_added = 0
        lines_deleted = 0
        
        if diff_stats:
            # Parse the diff stats output
            for line in diff_stats.split('\n'):
                if 'insertion' in line and 'deletion' in line:
                    # Extract numbers from lines like " 2 files changed, 10 insertions(+), 5 deletions(-)"
                    parts = line.split(',')
                    for part in parts:
                        if 'insertion' in part:
                            try:
                                lines_added = int(''.join(filter(str.isdigit, part)))
                            except ValueError:
                                pass
                        elif 'deletion' in part:
                            try:
                                lines_deleted = int(''.join(filter(str.isdigit, part)))
                            except ValueError:
                                pass
                elif 'insertion' in line and 'deletion' not in line:
                    # Only insertions
                    try:
                        lines_added = int(''.join(filter(str.isdigit, line)))
                    except ValueError:
                        pass
                elif 'deletion' in line and 'insertion' not in line:
                    # Only deletions
                    try:
                        lines_deleted = int(''.join(filter(str.isdigit, line)))
                    except ValueError:
                        pass
        
        return lines_added, lines_deleted
    
    def analyze_repositories(self) -> None:
        """Analyze all discovered repositories and collect statistics."""
        print("Analyzing repositories...")
        
        for repo_path in self.repositories:
            print(f"Analyzing {repo_path}...")
            repo_stats = self._get_commit_stats(repo_path)
            self.stats.extend(repo_stats)
        
        print(f"Collected {len(self.stats)} commits across all repositories")
        
        # Create DataFrame from commit stats
        if self.stats:
            self._create_dataframe()
    
    def _create_dataframe(self) -> None:
        """Create pandas DataFrame from commit statistics."""
        # Create DataFrame with raw commit data
        commits_data = []
        for commit in self.stats:
            commits_data.append({
                'commit_hash': commit.commit_hash,
                'author': commit.author,
                'date': commit.date,
                'lines_added': commit.lines_added,
                'lines_deleted': commit.lines_deleted
            })
        
        self.df = pd.DataFrame(commits_data)
        
        # Remove duplicate commits (in case Git log returns duplicates)
        self.df = self.df.drop_duplicates(subset=['commit_hash'])
        
        # Add derived columns
        # Calculate week start (Monday) - normalize to date only to avoid timezone issues
        self.df['week_start'] = self.df['date'].apply(
            lambda x: (x - timedelta(days=x.weekday())).date()
        )
        self.df['net_lines'] = self.df['lines_added'] - self.df['lines_deleted']
    
    def get_weekly_dataframe(self) -> pd.DataFrame:
        """
        Get weekly aggregated DataFrame.
        
        Returns:
            DataFrame with weekly aggregated data by contributor
        """
        return self.get_grouped_dataframe('week')
    
    def get_grouped_dataframe(self, group_by: str = 'week') -> pd.DataFrame:
        """
        Get aggregated DataFrame grouped by specified time period.
        
        Args:
            group_by: Grouping period ('day', 'week', 'month')
            
        Returns:
            DataFrame with aggregated data by contributor and time period
        """
        if self.df is None:
            return pd.DataFrame()
        
        # Create grouping column based on the specified period
        if group_by == 'day':
            self.df['period_start'] = self.df['date'].dt.date
        elif group_by == 'week':
            self.df['period_start'] = self.df['date'].apply(
                lambda x: (x - timedelta(days=x.weekday())).date()
            )
        elif group_by == 'month':
            self.df['period_start'] = self.df['date'].apply(
                lambda x: x.replace(day=1).date()
            )
        else:
            raise ValueError(f"Invalid group_by option: {group_by}. Must be 'day', 'week', or 'month'")
        
        # Aggregate by period and contributor using DataFrame operations
        grouped_data = self.df.groupby(['period_start', 'author']).agg({
            'commit_hash': 'count',  # Count commits
            'lines_added': 'sum',
            'lines_deleted': 'sum'
        }).reset_index()
        
        # Rename columns
        grouped_data.columns = ['period_start', 'contributor', 'commits', 'lines_added', 'lines_deleted']
        
        return grouped_data.sort_values(['period_start', 'contributor']).reset_index(drop=True)
    
    def export_to_json(self, output_file: str) -> None:
        """
        Export weekly statistics to JSON file.
        
        Args:
            output_file: Output file path
        """
        weekly_data = self.get_weekly_dataframe()
        if weekly_data.empty:
            print("No data to export. Run analyze_repositories() first.")
            return
        
        # Format for JSON export
        weekly_data['week_start'] = weekly_data['week_start'].astype(str)
        data = weekly_data.to_dict('records')
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Exported {len(data)} weekly statistics to {output_file}")
    
    def export_to_csv(self, output_file: str) -> None:
        """
        Export weekly statistics to CSV file.
        
        Args:
            output_file: Output file path
        """
        weekly_data = self.get_weekly_dataframe()
        if weekly_data.empty:
            print("No data to export. Run analyze_repositories() first.")
            return
        
        # Format for CSV export
        weekly_data.columns = ['Week Start', 'Contributor', 'Commits', 'Lines Added', 'Lines Deleted']
        weekly_data['Week Start'] = weekly_data['Week Start'].astype(str)
        
        weekly_data.to_csv(output_file, index=False)
        
        print(f"Exported {len(weekly_data)} weekly statistics to {output_file}")
    
    def print_summary(self) -> None:
        """Print a summary of the analysis."""
        if self.df is None:
            print("No statistics available.")
            return
        
        print("\n" + "="*80)
        print("GIT REPOSITORY ANALYSIS SUMMARY")
        print("="*80)
        
        # Overall statistics from raw data
        total_commits = len(self.df)
        total_lines_added = self.df['lines_added'].sum()
        total_lines_deleted = self.df['lines_deleted'].sum()
        
        print(f"Total commits analyzed: {total_commits}")
        print(f"Total lines added: {total_lines_added:,}")
        print(f"Total lines deleted: {total_lines_deleted:,}")
        print(f"Net lines changed: {total_lines_added - total_lines_deleted:,}")
        
        # Top contributors using DataFrame operations
        contributor_stats = self.df.groupby('author').agg({
            'commit_hash': 'count',
            'lines_added': 'sum',
            'lines_deleted': 'sum'
        }).sort_values('commit_hash', ascending=False)
        
        print(f"\nTop contributors by commits:")
        for i, (contributor, row) in enumerate(contributor_stats.head(10).iterrows(), 1):
            print(f"  {i:2d}. {contributor}: {row['commit_hash']} commits, "
                  f"{row['lines_added']:,} lines added, {row['lines_deleted']:,} lines deleted")
        
        # Weekly breakdown - print DataFrame directly
        print(f"\nWeekly breakdown (last 10 weeks):")
        weekly_data = self.get_weekly_dataframe()
        if not weekly_data.empty:
            # Get the actual last 10 weeks from the raw data
            recent_weeks = self.df['week_start'].unique()
            recent_weeks = sorted(recent_weeks, reverse=True)[:10]
            
            # Filter to only show data from these 10 weeks
            recent_data = weekly_data[weekly_data['period_start'].isin(recent_weeks)]
            
            # Format the DataFrame for better display
            display_data = recent_data.copy()
            display_data['period_start'] = display_data['period_start'].astype(str)
            display_data = display_data.sort_values(['period_start', 'commits'], ascending=[False, False])
            
            # Limit to top 20 rows to keep output manageable
            print(display_data.head(20).to_string(index=False))
            if len(display_data) > 20:
                print(f"\n... and {len(display_data) - 20} more rows")
        else:
            print("No weekly data available.")
    
    def get_dataframe(self) -> pd.DataFrame:
        """
        Get the raw commits DataFrame.
        
        Returns:
            DataFrame with commit-level data
        """
        return self.df.copy() if self.df is not None else pd.DataFrame()
    
    def get_contributor_summary(self) -> pd.DataFrame:
        """
        Get a summary DataFrame of contributors.
        
        Returns:
            DataFrame with contributor-level aggregated data
        """
        if self.df is None:
            return pd.DataFrame()
        
        return self.df.groupby('author').agg({
            'commit_hash': 'count',
            'lines_added': 'sum',
            'lines_deleted': 'sum'
        }).sort_values('commit_hash', ascending=False).reset_index()


