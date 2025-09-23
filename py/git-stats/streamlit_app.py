#!/usr/bin/env python3
"""
Streamlit app for Git repository statistics visualization.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
import os

# Add the parent directory to the path so we can import git_analyzer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from git_analyzer import GitAnalyzer


def main():
    st.set_page_config(
        page_title="Git Stats Dashboard",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Git Repository Statistics Dashboard")
    st.markdown("Analyze commit patterns and contributor activity across your Git repositories")
    
    # Sidebar for configuration
    st.sidebar.header("Configuration")
    
    # Repository input
    repo_paths = st.sidebar.text_area(
        "Repository Paths",
        value="~/src/vision",
        help="Enter repository paths, one per line. Supports glob patterns like ~/src/*"
    ).strip().split('\n')
    
    # Expand tilde paths
    repo_paths = [os.path.expanduser(path.strip()) for path in repo_paths if path.strip()]
    
    # Since date input
    since_date = st.sidebar.text_input(
        "Since Date",
        value="1 year ago",
        help="Limit analysis to commits since this date (e.g., '1 year ago', '2024-01-01')"
    )
    
    # Analyze button
    if st.sidebar.button("🔍 Analyze Repositories", type="primary"):
        with st.spinner("Analyzing repositories..."):
            try:
                # Create analyzer and run analysis
                analyzer = GitAnalyzer(repo_paths, since_date=since_date)
                analyzer.analyze_repositories()
                
                # Store results in session state
                st.session_state.analyzer = analyzer
                st.session_state.analysis_complete = True
                
                st.sidebar.success(f"✅ Analyzed {len(analyzer.df)} commits")
                
            except Exception as e:
                st.sidebar.error(f"❌ Error: {str(e)}")
                st.session_state.analysis_complete = False
    
    # Check if analysis is complete
    if not st.session_state.get('analysis_complete', False):
        st.info("👈 Configure your repositories in the sidebar and click 'Analyze Repositories' to get started")
        return
    
    analyzer = st.session_state.analyzer
    
    # Check if analyzer and df exist
    if analyzer is None or analyzer.df is None:
        st.error("❌ Analysis failed. Please check your repository paths and try again.")
        return
    
    df = analyzer.df
    
    if df.empty:
        st.warning("No data found for the specified repositories and date range.")
        return
    
    # Main dashboard
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Commits", f"{len(df):,}")
    
    with col2:
        st.metric("Total Lines Added", f"{df['lines_added'].sum():,}")
    
    with col3:
        st.metric("Total Lines Deleted", f"{df['lines_deleted'].sum():,}")
    
    with col4:
        net_lines = df['lines_added'].sum() - df['lines_deleted'].sum()
        st.metric("Net Lines Changed", f"{net_lines:,}")
    
    st.markdown("---")
    
    # Get weekly data
    weekly_data = analyzer.get_weekly_dataframe()
    
    if weekly_data.empty:
        st.warning("No weekly data available.")
        return
    
    # Convert week_start to datetime for plotting
    weekly_data['week_start'] = pd.to_datetime(weekly_data['week_start'])
    
    # Create tabs for different visualizations
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Weekly Commits", "👥 Contributors", "📊 Raw Data", "📋 Summary"])
    
    with tab1:
        st.header("Weekly Commits by Contributor")
        
        # Create stacked bar chart
        fig = px.bar(
            weekly_data,
            x='week_start',
            y='commits',
            color='contributor',
            title="Commits per Week by Contributor",
            labels={'week_start': 'Week', 'commits': 'Number of Commits', 'contributor': 'Contributor'},
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_layout(
            xaxis_title="Week",
            yaxis_title="Commits",
            legend_title="Contributor",
            height=500,
            showlegend=True
        )
        
        # Rotate x-axis labels
        fig.update_xaxes(tickangle=45)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Add summary statistics
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Most Active Weeks")
            weekly_totals = weekly_data.groupby('week_start')['commits'].sum().sort_values(ascending=False)
            st.dataframe(weekly_totals.head(10), use_container_width=True)
        
        with col2:
            st.subheader("Weekly Activity Distribution")
            st.bar_chart(weekly_totals.tail(10))
    
    with tab2:
        st.header("Contributor Analysis")
        
        # Get contributor summary
        contributor_summary = analyzer.get_contributor_summary()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Top Contributors by Commits")
            fig_contrib = px.bar(
                contributor_summary.head(10),
                x='commit_hash',
                y='author',
                orientation='h',
                title="Top 10 Contributors by Commits",
                labels={'commit_hash': 'Commits', 'author': 'Contributor'}
            )
            fig_contrib.update_layout(height=400)
            st.plotly_chart(fig_contrib, use_container_width=True)
        
        with col2:
            st.subheader("Lines of Code by Contributor")
            fig_lines = px.bar(
                contributor_summary.head(10),
                x='lines_added',
                y='author',
                orientation='h',
                title="Top 10 Contributors by Lines Added",
                labels={'lines_added': 'Lines Added', 'author': 'Contributor'},
                color='lines_added',
                color_continuous_scale='Blues'
            )
            fig_lines.update_layout(height=400)
            st.plotly_chart(fig_lines, use_container_width=True)
        
        # Contributor details table
        st.subheader("Detailed Contributor Statistics")
        st.dataframe(contributor_summary, use_container_width=True)
    
    with tab3:
        st.header("Raw Data")
        
        # Data filters
        col1, col2 = st.columns(2)
        
        with col1:
            selected_contributors = st.multiselect(
                "Filter by Contributors",
                options=df['author'].unique(),
                default=df['author'].unique()
            )
        
        with col2:
            date_range = st.date_input(
                "Date Range",
                value=(df['date'].min().date(), df['date'].max().date()),
                min_value=df['date'].min().date(),
                max_value=df['date'].max().date()
            )
        
        # Filter data
        filtered_df = df[
            (df['author'].isin(selected_contributors)) &
            (df['date'].dt.date >= date_range[0]) &
            (df['date'].dt.date <= date_range[1])
        ]
        
        st.subheader(f"Filtered Data ({len(filtered_df)} commits)")
        st.dataframe(filtered_df, use_container_width=True)
        
        # Download button
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"git_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    with tab4:
        st.header("Analysis Summary")
        
        # Print the same summary as the CLI
        analyzer.print_summary()
        
        # Additional insights
        st.subheader("📊 Additional Insights")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Average Commits per Week", f"{len(df) / weekly_data['week_start'].nunique():.1f}")
            st.metric("Most Active Day", df['date'].dt.day_name().mode().iloc[0])
            st.metric("Average Lines per Commit", f"{df['lines_added'].mean():.1f}")
        
        with col2:
            st.metric("Total Contributors", df['author'].nunique())
            st.metric("Date Range", f"{(df['date'].max() - df['date'].min()).days} days")
            st.metric("Commits per Day", f"{len(df) / (df['date'].max() - df['date'].min()).days:.1f}")


if __name__ == "__main__":
    main()
